#!/usr/bin/env python3
"""Migrate existing JSONL household data to the Shelby SQLite database.

Idempotent: skips records whose logged_at/created_at already exist.
Backs up JSONL files before migration.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "components" / "src"))

from forsch.adk_components.shelby.store import get_db, init_db


HOUSEHOLD_DIR = Path("/root/.hermes/workspace/adk/data/household")
BACKUP_DIR = HOUSEHOLD_DIR / "backup"


def backup_jsonl(filename: str) -> Path | None:
    """Copy a JSONL file to backup/ with a timestamp. Returns dest or None."""
    src = HOUSEHOLD_DIR / filename
    if not src.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"{filename}.{ts}.bak"
    shutil.copy2(src, dest)
    return dest


def read_jsonl(filename: str) -> list[dict]:
    """Read a JSONL file, return list of dicts."""
    path = HOUSEHOLD_DIR / filename
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def migrate_groceries(conn) -> int:
    """Migrate groceries.jsonl → groceries table. Returns count of new rows."""
    existing = {r["logged_at"] for r in conn.execute("SELECT logged_at FROM groceries").fetchall()}
    records = read_jsonl("groceries.jsonl")
    new_count = 0
    for rec in records:
        logged_at = rec.get("logged_at", "")
        if logged_at in existing:
            continue
        conn.execute(
            "INSERT INTO groceries (name, quantity, unit, store, date, category, note, logged_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rec.get("name", ""), rec.get("quantity"), rec.get("unit"), rec.get("store"),
             rec.get("date", ""), rec.get("category"), rec.get("note"), logged_at),
        )
        existing.add(logged_at)
        new_count += 1
    conn.commit()
    return new_count


def migrate_reminders(conn) -> int:
    """Migrate reminders.jsonl → reminders table. Returns count of new rows."""
    existing = {r["created_at"] for r in conn.execute("SELECT created_at FROM reminders").fetchall()}
    records = read_jsonl("reminders.jsonl")
    new_count = 0
    for rec in records:
        created_at = rec.get("created_at", "")
        if created_at in existing:
            continue
        conn.execute(
            "INSERT INTO reminders (title, list_name, due, note, synced, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rec.get("title", ""), rec.get("list", "Reminders"), rec.get("due"),
             rec.get("note"), 1 if rec.get("synced") else 0, created_at),
        )
        existing.add(created_at)
        new_count += 1
    conn.commit()
    return new_count


def main() -> None:
    print("Initializing database...")
    result = init_db()
    print(f"  init_db: {result}")

    conn = get_db()

    print("Backing up JSONL files...")
    for fn in ("groceries.jsonl", "reminders.jsonl"):
        dest = backup_jsonl(fn)
        if dest:
            print(f"  backed up {fn} → {dest}")
        else:
            print(f"  {fn} not found, skipping backup")

    print("Migrating groceries...")
    g = migrate_groceries(conn)
    print(f"  {g} new grocery rows inserted")

    print("Migrating reminders...")
    r = migrate_reminders(conn)
    print(f"  {r} new reminder rows inserted")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
