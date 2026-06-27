"""Deterministic reminders core with honest receipts.

All args validated by Pydantic. Receipts ALWAYS say 'saved locally' and
NEVER imply iPhone sync. This is the single source of truth for reminder
mutations — store.py handles SQLite, remindctl handles business logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class ReminderArgs(BaseModel):
    """Validated input for adding a reminder."""
    title: str
    list_name: str = "Reminders"
    due: Optional[str] = None
    note: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_must_be_nonempty(cls, v: str) -> str:
        clean = (v or "").strip()
        if not clean:
            raise ValueError("title cannot be empty")
        return clean

    @field_validator("list_name")
    @classmethod
    def list_name_must_be_nonempty(cls, v: str) -> str:
        clean = (v or "").strip()
        if not clean:
            raise ValueError("list_name cannot be empty")
        return clean


class ListFilterArgs(BaseModel):
    """Validated input for listing reminders."""
    list_name: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    status: Optional[str] = None  # 'pending', 'completed', or None for all


class CheckArgs(BaseModel):
    """Validated input for marking a reminder done."""
    reminder_id: int

    @field_validator("reminder_id")
    @classmethod
    def id_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("reminder_id must be positive")
        return v


HONEST_STATUS = "saved locally — not yet synced to Apple Reminders"
DONE_STATUS = "completed locally — not yet synced to Apple Reminders"


def _honest_receipt(row: dict[str, Any], *, done: bool = False) -> dict[str, Any]:
    """Build an honest receipt from a DB row. Never claims sync."""
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "list": row.get("list_name"),
        "due": row.get("due"),
        "note": row.get("note"),
        "synced": False,
        "status": DONE_STATUS if done else HONEST_STATUS,
    }


def add_reminder(
    title: str,
    list_name: str = "Reminders",
    due: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Add a reminder with Pydantic-validated args. Returns honest receipt."""
    args = ReminderArgs(title=title, list_name=list_name, due=due, note=note)
    from .store import get_db

    try:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO reminders (title, list_name, due, note, synced, created_at) "
            "VALUES (:title, :list_name, :due, :note, 0, :created_at)",
            {
                "title": args.title,
                "list_name": args.list_name,
                "due": args.due,
                "note": args.note,
                "created_at": now,
            },
        )
        row_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (row_id,)).fetchone()
        conn.close()
        if not row:
            return {"ok": False, "error": "insert failed", "receipt": None}
        receipt = _honest_receipt(dict(row))
        return {"ok": True, "receipt": receipt}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "receipt": None}


def list_reminders(
    list_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """List reminders with optional filters. Returns list of dicts."""
    args = ListFilterArgs(list_name=list_name, since=since, until=until, status=status)
    from .store import get_db

    try:
        conn = get_db()
        where: list[str] = []
        params: dict[str, Any] = {}

        if args.list_name is not None:
            where.append("list_name = :list_name")
            params["list_name"] = args.list_name
        if args.since is not None:
            where.append("created_at >= :since")
            params["since"] = args.since
        if args.until is not None:
            where.append("created_at <= :until")
            params["until"] = args.until
        if args.status == "completed":
            where.append("completed_at IS NOT NULL")
        elif args.status == "pending":
            where.append("completed_at IS NULL")

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        sql = f"SELECT * FROM reminders{where_sql} ORDER BY created_at"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        records = [dict(r) for r in rows]
        return {"ok": True, "count": len(records), "records": records}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "count": 0, "records": []}


def check_reminder(reminder_id: int) -> dict[str, Any]:
    """Mark a reminder as completed. Returns honest receipt."""
    args = CheckArgs(reminder_id=reminder_id)
    from .store import get_db

    try:
        conn = get_db()
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (args.reminder_id,)).fetchone()
        if not row:
            conn.close()
            return {"ok": False, "error": f"reminder {args.reminder_id} not found", "receipt": None}
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE reminders SET completed_at = :now WHERE id = :id",
            {"now": now, "id": args.reminder_id},
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM reminders WHERE id = ?", (args.reminder_id,)).fetchone()
        conn.close()
        receipt = _honest_receipt(dict(updated), done=True)
        return {"ok": True, "receipt": receipt}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "receipt": None}
