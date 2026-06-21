"""Household management kit — shared tools for personal/household agents.

v1 surface (Shelby): track groceries over time, read the log back for trend
reasoning, and record reminders locally with an honest read-back receipt.

Storage is append-only JSONL under the household data dir, resolved from
``FORSCH_HOUSEHOLD_DATA`` if set, else ``$FORSCH_ADK_WORKSPACE/data/household``.
No hardcoded paths (a stale path is a silent landmine). Tools never raise into
the caller; they return ``{"ok": False, "error": ...}`` instead.

Reminders are recorded LOCALLY for now — there is no Apple Reminders sync from
this Linux box yet, so every receipt reports ``synced: False`` truthfully. Do
not let an agent claim a reminder reached a phone until a real sync exists.
"""

from __future__ import annotations

import json
import os
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GROCERIES_LOG = "groceries.jsonl"
REMINDERS_LOG = "reminders.jsonl"


def log_groceries(
    items: list[Any],
    store: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Append grocery items to the running log.

    ``items`` may be plain strings (just a name) or dicts with any of
    ``name, quantity, unit, store, date, category, note``. A top-level
    ``store``/``date`` fills in any item that omits its own. ``date`` defaults
    to today (ISO ``YYYY-MM-DD``). Returns the normalized records that were
    logged so the agent can read them straight back.
    """
    try:
        if not items:
            return {"ok": False, "error": "no items to log", "logged": [], "count": 0}
        default_date = date or _date.today().isoformat()
        logged_at = datetime.now(timezone.utc).isoformat()
        records: list[dict[str, Any]] = []
        for raw in items:
            item = {"name": raw} if isinstance(raw, str) else dict(raw or {})
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            records.append(
                {
                    "name": name,
                    "quantity": item.get("quantity"),
                    "unit": item.get("unit"),
                    "store": item.get("store") or store,
                    "date": item.get("date") or default_date,
                    "category": item.get("category"),
                    "note": item.get("note"),
                    "logged_at": logged_at,
                }
            )
        if not records:
            return {"ok": False, "error": "no named items to log", "logged": [], "count": 0}
        _append(GROCERIES_LOG, records)
        return {"ok": True, "logged": records, "count": len(records)}
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {"ok": False, "error": str(exc), "logged": [], "count": 0}


def get_grocery_log(
    since: str | None = None,
    until: str | None = None,
    name: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return logged grocery records for the agent to reason over.

    Optional ``since``/``until`` are inclusive ISO date bounds on each record's
    ``date``; ``name`` is a case-insensitive substring match; ``limit`` keeps
    only the most recent N. Records come back oldest-first. This returns raw
    rows — trend reasoning is the agent's job, not a baked-in analytics engine.
    """
    try:
        records = _read(GROCERIES_LOG)
        if since is not None:
            records = [r for r in records if (r.get("date") or "") >= since]
        if until is not None:
            records = [r for r in records if (r.get("date") or "") <= until]
        if name is not None:
            needle = name.lower()
            records = [r for r in records if needle in str(r.get("name", "")).lower()]
        records.sort(key=lambda r: (r.get("date") or "", r.get("logged_at") or ""))
        if limit is not None and limit >= 0:
            records = records[-limit:]
        return {"ok": True, "count": len(records), "records": records}
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {"ok": False, "error": str(exc), "count": 0, "records": []}


def add_reminder(
    title: str,
    list_name: str = "Reminders",
    due: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Record a reminder locally and return an honest read-back receipt.

    There is no Apple Reminders sync from this box yet, so ``synced`` is always
    ``False`` and the receipt says so plainly. The agent must read this receipt
    back verbatim and never claim the reminder reached a phone.
    """
    try:
        clean_title = (title or "").strip()
        if not clean_title:
            return {"ok": False, "error": "reminder needs a title", "receipt": None}
        receipt = {
            "title": clean_title,
            "list": list_name or "Reminders",
            "due": due,
            "note": note,
            "synced": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "logged locally — not yet synced to Apple Reminders",
        }
        _append(REMINDERS_LOG, [receipt])
        return {"ok": True, "receipt": receipt}
    except Exception as exc:  # noqa: BLE001 - tools return structured failures.
        return {"ok": False, "error": str(exc), "receipt": None}


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


def _append(filename: str, records: list[dict[str, Any]]) -> None:
    path = _household_dir() / filename
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(filename: str) -> list[dict[str, Any]]:
    path = _household_dir() / filename
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
