"""WhitelistStore — sender/ACL whitelist with add/remove/list/check.

---
keywords: [whitelist, allowlist, acl, trusted, sender, domain, user, approval, gate]
intention: "Saves you from hand-rolling add/remove/list/check sets every time you need to gate something (senders, domains, users, file paths). Derived from JSONLStore, so persistence is free."
function: "Sender/ACL whitelist with add/remove/list/check, derived from JSONLStore."
depends_on: [jsonl_store]
used_by: [email_groceries]
example: "wl = WhitelistStore('grocery_senders.json'); wl.add('receipts@wholefoods.com')"
---
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .jsonl_store import JSONLStore


class WhitelistStore(JSONLStore):
    """ACL whitelist: add/remove/list/check a set of keys, each with optional metadata.

    Stores records as a JSON array (write_atomic), not JSONL — because whitelist
    membership is set-shaped, not append-shaped. Each record is dict[str, Any]
    with required 'key' field and optional metadata fields.

    Use WhitelistStore when you need a TRUST GATE. Reject the operation if the
    key isn't in the whitelist. Never accept broader patterns — exact match only.
    """

    def __init__(self, filename: str = "whitelist.json", *, basename_dir: str = "whitelists"):
        super().__init__(filename, basename_dir=basename_dir)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _records(self) -> list[dict[str, Any]]:
        raw = self.read()
        # Whitelist files are stored as JSONL where each line is the whole list
        # OR as a single record per key. Support both shapes.
        if len(raw) == 1 and isinstance(raw[0], dict) and "keys" in raw[0]:
            return raw[0]["keys"]
        return raw

    def _save(self, records: list[dict[str, Any]]) -> None:
        self.write_atomic(records)

    def add(self, key: str, **meta: Any) -> dict[str, Any]:
        """Add or update a key. Returns {ok, added: bool, record}."""
        key = key.strip().lower()
        if not key:
            return {"ok": False, "error": "key must be non-empty", "added": False}
        records = self._records()
        now = self._now()
        existing = next((r for r in records if r.get("key") == key), None)
        if existing:
            existing.update({k: v for k, v in meta.items() if v is not None})
            existing["updated_at"] = now
            added = False
        else:
            record = {"key": key, "added_at": now, "updated_at": now, **meta}
            records.append(record)
            added = True
        self._save(records)
        return {"ok": True, "added": added, "record": existing or records[-1]}

    def remove(self, key: str) -> dict[str, Any]:
        key = key.strip().lower()
        records = self._records()
        before = len(records)
        records = [r for r in records if r.get("key") != key]
        removed = len(records) < before
        self._save(records)
        return {"ok": True, "removed": removed, "key": key}

    def list(self) -> list[dict[str, Any]]:
        return sorted(self._records(), key=lambda r: r.get("key", ""))

    def is_allowed(self, key: str) -> bool:
        key = key.strip().lower()
        return any(r.get("key") == key for r in self._records())

    def check(self, key: str) -> dict[str, Any]:
        """Detailed check: returns match record if allowed."""
        key = key.strip().lower()
        match = next((r for r in self._records() if r.get("key") == key), None)
        return {"ok": True, "allowed": match is not None, "key": key, "match": match}

    def count(self) -> int:
        return len(self._records())
