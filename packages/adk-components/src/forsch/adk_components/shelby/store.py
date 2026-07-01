"""SQLite store for Shelby household data.

All mutations return the inserted/affected row as a dict so callers can read
back what was stored. Queries return lists of dicts. Errors surface as
``{"ok": False, "error": ...}`` — tools never raise into the agent.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    """Resolve the repo's data/ dir without hardcoding a box path.

    Prefer FORSCH_ADK_WORKSPACE (the repo root, set in every runtime context);
    fall back to the repo root derived from this file's location (used in CI /
    tests, where the env var is unset). No filesystem probe at import time — a
    module-level ``.exists()`` on an inaccessible path (e.g. /root on a CI
    runner) raises PermissionError during test collection.
    """
    root = os.environ.get("FORSCH_ADK_WORKSPACE")
    base = Path(root) if root else Path(__file__).resolve().parents[6]
    return base / "data"


DB_PATH = _data_dir() / "shelby.db"
SCHEMA_PATH = _data_dir() / "shelby_schema.sql"


def get_db() -> sqlite3.Connection:
    """Return a SQLite connection to the Shelby database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> dict[str, Any]:
    """Create tables if they don't exist. Idempotent."""
    try:
        conn = get_db()
        if SCHEMA_PATH.exists():
            conn.executescript(SCHEMA_PATH.read_text())
        else:
            # Inline fallback
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS groceries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    quantity REAL,
                    unit TEXT,
                    store TEXT,
                    date TEXT NOT NULL,
                    category TEXT,
                    note TEXT,
                    logged_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    list_name TEXT DEFAULT 'Reminders',
                    due TEXT,
                    note TEXT,
                    synced INTEGER DEFAULT 0,
                    completed_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    assignee TEXT,
                    cadence_days INTEGER,
                    last_done TEXT,
                    due TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
        conn.close()
        return {"ok": True, "message": "database initialized"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def log_groceries(
    items: list[Any],
    store_name: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Insert grocery items into the SQLite database.

    ``items`` may be plain strings or dicts. Returns the inserted rows.
    """
    try:
        if not items:
            return {"ok": False, "error": "no items to log", "logged": [], "count": 0}
        from datetime import date as _date

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
                    "store": item.get("store") or store_name,
                    "date": item.get("date") or default_date,
                    "category": item.get("category"),
                    "note": item.get("note"),
                    "logged_at": logged_at,
                }
            )
        if not records:
            return {"ok": False, "error": "no named items to log", "logged": [], "count": 0}

        conn = get_db()
        inserted: list[dict[str, Any]] = []
        for rec in records:
            cur = conn.execute(
                "INSERT INTO groceries (name, quantity, unit, store, date, category, note, logged_at) "
                "VALUES (:name, :quantity, :unit, :store, :date, :category, :note, :logged_at)",
                rec,
            )
            rec["id"] = cur.lastrowid
            inserted.append(rec)
        conn.commit()
        conn.close()
        return {"ok": True, "logged": inserted, "count": len(inserted)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "logged": [], "count": 0}


def get_groceries(
    since: str | None = None,
    until: str | None = None,
    name: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Query groceries with optional date/name filters."""
    try:
        conn = get_db()
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if since is not None:
            where_clauses.append("date >= :since")
            params["since"] = since
        if until is not None:
            where_clauses.append("date <= :until")
            params["until"] = until
        if name is not None:
            where_clauses.append("lower(name) LIKE :name")
            params["name"] = f"%{name.lower()}%"
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"SELECT * FROM groceries{where_sql} ORDER BY date, logged_at"
        if limit is not None and limit >= 0:
            sql += f" LIMIT {limit}" if limit else " LIMIT 0"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        records = [dict(r) for r in rows]
        return {"ok": True, "count": len(records), "records": records}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "count": 0, "records": []}


def add_reminder(
    title: str,
    list_name: str = "Reminders",
    due: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Insert a reminder and return an honest read-back receipt."""
    try:
        clean_title = (title or "").strip()
        if not clean_title:
            return {"ok": False, "error": "reminder needs a title", "receipt": None}
        created_at = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO reminders (title, list_name, due, note, synced, created_at) "
            "VALUES (:title, :list_name, :due, :note, 0, :created_at)",
            {"title": clean_title, "list_name": list_name or "Reminders", "due": due, "note": note, "created_at": created_at},
        )
        row_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (row_id,)).fetchone()
        conn.close()
        receipt = dict(row) if row else {}
        receipt["status"] = "logged locally — not yet synced to Apple Reminders"
        return {"ok": True, "receipt": receipt}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "receipt": None}


def get_reminders(
    list_name: str | None = None,
    due_before: str | None = None,
    synced: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Query reminders with optional filters."""
    try:
        conn = get_db()
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if list_name is not None:
            where_clauses.append("list_name = :list_name")
            params["list_name"] = list_name
        if due_before is not None:
            where_clauses.append("due IS NOT NULL AND due <= :due_before")
            params["due_before"] = due_before
        if synced is not None:
            where_clauses.append("synced = :synced")
            params["synced"] = 1 if synced else 0
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"SELECT * FROM reminders{where_sql} ORDER BY created_at"
        if limit is not None and limit >= 0:
            sql += f" LIMIT {limit}" if limit else " LIMIT 0"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        records = [dict(r) for r in rows]
        return {"ok": True, "count": len(records), "records": records}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "count": 0, "records": []}


def add_chore(
    title: str,
    assignee: str | None = None,
    cadence_days: int | None = None,
    due: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Insert a chore and return the created row."""
    try:
        clean_title = (title or "").strip()
        if not clean_title:
            return {"ok": False, "error": "chore needs a title", "chore": None}
        created_at = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO chores (title, assignee, cadence_days, last_done, due, note, created_at) "
            "VALUES (:title, :assignee, :cadence_days, NULL, :due, :note, :created_at)",
            {"title": clean_title, "assignee": assignee, "cadence_days": cadence_days, "due": due, "note": note, "created_at": created_at},
        )
        row_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM chores WHERE id = ?", (row_id,)).fetchone()
        conn.close()
        return {"ok": True, "chore": dict(row) if row else {}}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "chore": None}


def get_chores(
    assignee: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Query chores with optional filters."""
    try:
        conn = get_db()
        where_clauses: list[str] = []
        params: dict[str, Any] = {}
        if assignee is not None:
            where_clauses.append("assignee = :assignee")
            params["assignee"] = assignee
        if due_before is not None:
            where_clauses.append("due IS NOT NULL AND due <= :due_before")
            params["due_before"] = due_before
        if due_after is not None:
            where_clauses.append("due IS NOT NULL AND due >= :due_after")
            params["due_after"] = due_after
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"SELECT * FROM chores{where_sql} ORDER BY created_at"
        if limit is not None and limit >= 0:
            sql += f" LIMIT {limit}" if limit else " LIMIT 0"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        records = [dict(r) for r in rows]
        return {"ok": True, "count": len(records), "records": records}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "count": 0, "records": []}


def check_chore(chore_id: int) -> dict[str, Any]:
    """Mark a chore as done — updates last_done to now and advances due if cadence is set."""
    try:
        conn = get_db()
        now = datetime.now(timezone.utc).isoformat()
        row = conn.execute("SELECT * FROM chores WHERE id = ?", (chore_id,)).fetchone()
        if not row:
            conn.close()
            return {"ok": False, "error": f"chore {chore_id} not found"}
        row_dict = dict(row)
        cadence = row_dict.get("cadence_days")
        new_due = None
        if cadence:
            from datetime import timedelta

            base = datetime.now(timezone.utc).date()
            new_due = (base + timedelta(days=cadence)).isoformat()
        conn.execute(
            "UPDATE chores SET last_done = :now, due = :due WHERE id = :id",
            {"now": now, "due": new_due, "id": chore_id},
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM chores WHERE id = ?", (chore_id,)).fetchone()
        conn.close()
        return {"ok": True, "chore": dict(updated) if updated else {}}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def check_reminder(reminder_id: int) -> dict[str, Any]:
    """Mark a reminder as completed -- updates completed_at to now."""
    try:
        conn = get_db()
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        if not row:
            conn.close()
            return {"ok": False, "error": f"reminder {reminder_id} not found"}
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE reminders SET completed_at = :now WHERE id = :id",
            {"now": now, "id": reminder_id},
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        conn.close()
        return {"ok": True, "reminder": dict(updated) if updated else {}}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
