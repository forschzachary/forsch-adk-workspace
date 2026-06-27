"""Grocery-email intake tools for Shelby's assistant.

These tools intentionally do not expose general mailbox search. They model a
small, grocery-specific path:

1. Shelby explicitly adds trusted receipt senders to a whitelist.
2. Email/receipt intake only logs groceries when the sender is whitelisted.
3. Stored provenance is minimal metadata, not email body text.

The Gmail/Authsome fetch layer can call these tools after OAuth lands; the
agent-facing contract stays grocery-scoped.
"""

from __future__ import annotations

import json
import os
from datetime import date as _date
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .household import log_groceries

GROCERY_EMAIL_SENDERS = "grocery_email_senders.json"
GROCERY_EMAIL_RECEIPTS_LOG = "grocery_email_receipts.jsonl"


def add_grocery_email_sender(
    sender: str,
    store: str | None = None,
    label: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Add or update one exact sender address for grocery receipt intake.

    Use this only after Shelby explicitly asks to trust that sender. The input
    may be a bare email address or a display form like ``Store <a@b.com>``.
    """
    try:
        normalized = _normalize_sender(sender)
        if not normalized:
            return {"ok": False, "error": "sender must be a valid email address", "sender": None}

        data = _read_sender_store()
        now = _now()
        existing = data.get(normalized)
        record = {
            "sender": normalized,
            "store": _clean(store) if store is not None else (existing or {}).get("store"),
            "label": _clean(label) if label is not None else (existing or {}).get("label"),
            "note": _clean(note) if note is not None else (existing or {}).get("note"),
            "added_at": (existing or {}).get("added_at") or now,
            "updated_at": now,
        }
        data[normalized] = record
        _write_sender_store(data)
        return {"ok": True, "added": existing is None, "sender": record}
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {"ok": False, "error": str(exc), "sender": None}


def remove_grocery_email_sender(sender: str) -> dict[str, Any]:
    """Remove one exact sender address from Shelby's grocery whitelist."""
    try:
        normalized = _normalize_sender(sender)
        if not normalized:
            return {"ok": False, "error": "sender must be a valid email address", "removed": False}

        data = _read_sender_store()
        removed = data.pop(normalized, None)
        _write_sender_store(data)
        return {"ok": True, "removed": removed is not None, "sender": normalized}
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {"ok": False, "error": str(exc), "removed": False}


def list_grocery_email_senders() -> dict[str, Any]:
    """Return Shelby's exact sender whitelist for grocery email intake."""
    try:
        senders = sorted(_read_sender_store().values(), key=lambda r: r["sender"])
        return {"ok": True, "count": len(senders), "senders": senders}
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {"ok": False, "error": str(exc), "count": 0, "senders": []}


def is_grocery_email_sender_allowed(sender: str) -> dict[str, Any]:
    """Check whether an email sender is allowed for grocery receipt intake."""
    try:
        normalized = _normalize_sender(sender)
        if not normalized:
            return {"ok": False, "allowed": False, "error": "sender must be a valid email address"}
        record = _read_sender_store().get(normalized)
        return {"ok": True, "allowed": record is not None, "sender": normalized, "match": record}
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {"ok": False, "allowed": False, "error": str(exc)}


def log_grocery_email_receipt(
    sender: str,
    subject: str,
    items: list[Any],
    store: str | None = None,
    date: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Log groceries extracted from a whitelisted grocery receipt email.

    This tool does not fetch email and does not store body text. A caller should
    pass only normalized receipt items after reading an allowed message.
    """
    try:
        allowed = is_grocery_email_sender_allowed(sender)
        if not allowed.get("ok") or not allowed.get("allowed"):
            return {
                "ok": False,
                "allowed": False,
                "error": "sender is not on Shelby's grocery email whitelist",
                "sender": allowed.get("sender"),
                "logged": [],
                "receipt": None,
            }

        match = allowed["match"] or {}
        receipt_store = _clean(store) or match.get("store")
        receipt_date = date or _date.today().isoformat()
        grocery_result = log_groceries(items, store=receipt_store, date=receipt_date)
        if not grocery_result.get("ok"):
            return {
                "ok": False,
                "allowed": True,
                "error": grocery_result.get("error", "could not log groceries"),
                "sender": allowed["sender"],
                "logged": [],
                "receipt": None,
            }

        receipt = {
            "sender": allowed["sender"],
            "subject": _clean(subject),
            "store": receipt_store,
            "date": receipt_date,
            "message_id": _clean(message_id),
            "item_count": grocery_result["count"],
            "logged_item_names": [r["name"] for r in grocery_result["logged"]],
            "logged_at": _now(),
        }
        _append_receipt(receipt)
        return {
            "ok": True,
            "allowed": True,
            "sender": allowed["sender"],
            "logged": grocery_result["logged"],
            "receipt": receipt,
        }
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {
            "ok": False,
            "allowed": False,
            "error": str(exc),
            "sender": None,
            "logged": [],
            "receipt": None,
        }


def _normalize_sender(sender: str) -> str | None:
    _, address = parseaddr(sender or "")
    address = address.strip().lower()
    if not address or "@" not in address:
        return None
    local, domain = address.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        return None
    return address


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _household_dir() -> Path:
    override = os.environ.get("FORSCH_HOUSEHOLD_DATA")
    if override:
        base = Path(override).expanduser()
    else:
        root = os.environ.get("FORSCH_ADK_WORKSPACE")
        if not root:
            raise RuntimeError(
                "Neither FORSCH_HOUSEHOLD_DATA nor FORSCH_ADK_WORKSPACE is set; "
                "refusing to guess where household data lives"
            )
        base = Path(root).expanduser() / "data" / "household"
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def _read_sender_store() -> dict[str, dict[str, Any]]:
    path = _household_dir() / GROCERY_EMAIL_SENDERS
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    records = raw.get("senders", []) if isinstance(raw, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        normalized = _normalize_sender(str(record.get("sender", "")))
        if normalized:
            result[normalized] = {**record, "sender": normalized}
    return result


def _write_sender_store(data: dict[str, dict[str, Any]]) -> None:
    path = _household_dir() / GROCERY_EMAIL_SENDERS
    ordered = [data[key] for key in sorted(data)]
    payload = {"senders": ordered}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_receipt(record: dict[str, Any]) -> None:
    path = _household_dir() / GROCERY_EMAIL_RECEIPTS_LOG
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
