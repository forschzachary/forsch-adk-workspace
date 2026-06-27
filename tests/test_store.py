"""Tests for the Shelby SQLite store, migration, and API endpoints."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Patch DB_PATH before importing store so tests use a temp database
_tmp_dir = tempfile.mkdtemp()
_tmp_db = Path(_tmp_dir) / "test_shelby.db"

import forsch.adk_components.shelby.store as store_mod
store_mod.DB_PATH = _tmp_db

from forsch.adk_components.shelby.store import (
    add_chore,
    add_reminder,
    check_chore,
    get_chores,
    get_groceries,
    get_reminders,
    init_db,
    log_groceries,
)


@pytest.fixture(autouse=True)
def _fresh_db():
    """Create a fresh temp DB for each test."""
    # Ensure DB_PATH is always our temp db (migration test may have changed it)
    store_mod.DB_PATH = _tmp_db
    _tmp_db.unlink(missing_ok=True)
    # Also patch the schema path to use the real schema
    schema = Path("/root/.hermes/workspace/adk/data/shelby_schema.sql")
    if schema.exists():
        store_mod.SCHEMA_PATH = schema
    init_db()
    yield
    _tmp_db.unlink(missing_ok=True)


# ── Store tests ────────────────────────────────────────────────────────────


class TestInitDB:
    def test_init_idempotent(self):
        r1 = init_db()
        assert r1["ok"] is True
        r2 = init_db()
        assert r2["ok"] is True
        # Table should still exist
        conn = store_mod.get_db()
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "groceries" in tables
        assert "reminders" in tables
        assert "chores" in tables


class TestGroceries:
    def test_log_and_query(self):
        result = log_groceries(["milk", "eggs"], store_name="Costco", date="2026-06-25")
        assert result["ok"] is True
        assert result["count"] == 2
        assert result["logged"][0]["name"] == "milk"
        assert result["logged"][0]["store"] == "Costco"

        q = get_groceries(since="2026-06-25", until="2026-06-25")
        assert q["ok"] is True
        assert q["count"] == 2

    def test_log_dict_items(self):
        items = [{"name": "bread", "quantity": 2, "unit": "loaves"}]
        result = log_groceries(items)
        assert result["ok"] is True
        assert result["logged"][0]["quantity"] == 2.0
        assert result["logged"][0]["unit"] == "loaves"

    def test_log_empty(self):
        result = log_groceries([])
        assert result["ok"] is False

    def test_query_name_filter(self):
        log_groceries(["milk", "eggs", "oat milk"])
        q = get_groceries(name="milk")
        assert q["count"] == 2  # milk + oat milk

    def test_query_limit(self):
        log_groceries(["a", "b", "c", "d"])
        q = get_groceries(limit=2)
        assert q["count"] == 2

    def test_query_limit_zero(self):
        log_groceries(["a", "b"])
        q = get_groceries(limit=0)
        assert q["count"] == 0


class TestReminders:
    def test_add_and_query(self):
        result = add_reminder("Take out trash", due="2026-06-27")
        assert result["ok"] is True
        assert result["receipt"]["title"] == "Take out trash"
        assert result["receipt"]["synced"] == 0

        q = get_reminders()
        assert q["ok"] is True
        assert q["count"] == 1
        assert q["records"][0]["title"] == "Take out trash"

    def test_add_empty_title(self):
        result = add_reminder("")
        assert result["ok"] is False

    def test_query_list_name(self):
        add_reminder("Task A", list_name="Work")
        add_reminder("Task B", list_name="Home")
        q = get_reminders(list_name="Work")
        assert q["count"] == 1
        assert q["records"][0]["title"] == "Task A"

    def test_query_synced(self):
        add_reminder("Local only")
        q = get_reminders(synced=False)
        assert q["count"] == 1
        q = get_reminders(synced=True)
        assert q["count"] == 0


class TestChores:
    def test_add_and_query(self):
        result = add_chore("Mow lawn", assignee="Zach", cadence_days=7, due="2026-06-30")
        assert result["ok"] is True
        assert result["chore"]["title"] == "Mow lawn"
        assert result["chore"]["cadence_days"] == 7

        q = get_chores()
        assert q["count"] == 1

    def test_add_empty_title(self):
        result = add_chore("")
        assert result["ok"] is False

    def test_check_chore(self):
        result = add_chore("Vacuum", cadence_days=3)
        chore_id = result["chore"]["id"]
        check = check_chore(chore_id)
        assert check["ok"] is True
        assert check["chore"]["last_done"] is not None
        # Due should advance by 3 days
        assert check["chore"]["due"] is not None

    def test_check_chore_not_found(self):
        result = check_chore(9999)
        assert result["ok"] is False

    def test_query_assignee(self):
        add_chore("A", assignee="Zach")
        add_chore("B", assignee="Partner")
        q = get_chores(assignee="Zach")
        assert q["count"] == 1


# ── Migration tests ────────────────────────────────────────────────────────


class TestMigration:
    def test_migration_idempotent(self, tmp_path):
        """Simulate migration: write JSONL, migrate, re-migrate = no dupes."""
        household_dir = tmp_path / "household"
        household_dir.mkdir()
        groceries_file = household_dir / "groceries.jsonl"
        groceries_file.write_text(
            '{"name":"test item","date":"2026-01-01","logged_at":"2026-01-01T00:00:00Z"}\n'
        )

        # First migration
        import forsch.adk_components.shelby.store as s
        s.DB_PATH = tmp_path / "test.db"
        s.init_db()
        conn = s.get_db()

        existing = {r["logged_at"] for r in conn.execute("SELECT logged_at FROM groceries").fetchall()}
        records = []
        with open(groceries_file) as fh:
            import json
            for line in fh:
                if line.strip():
                    records.append(json.loads(line))

        for rec in records:
            if rec["logged_at"] not in existing:
                conn.execute(
                    "INSERT INTO groceries (name, quantity, unit, store, date, category, note, logged_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (rec.get("name",""), rec.get("quantity"), rec.get("unit"), rec.get("store"),
                     rec.get("date",""), rec.get("category"), rec.get("note"), rec["logged_at"]),
                )
                existing.add(rec["logged_at"])
        conn.commit()

        count1 = conn.execute("SELECT COUNT(*) FROM groceries").fetchone()[0]
        assert count1 == 1

        # Second migration — should skip
        for rec in records:
            if rec["logged_at"] not in existing:
                conn.execute(
                    "INSERT INTO groceries (name, date, logged_at) VALUES (?, ?, ?)",
                    (rec["name"], rec["date"], rec["logged_at"]),
                )
        conn.commit()
        count2 = conn.execute("SELECT COUNT(*) FROM groceries").fetchone()[0]
        assert count2 == 1  # No duplicate

        conn.close()


# ── API tests ──────────────────────────────────────────────────────────────


class TestAPI:
    @pytest.fixture
    def client(self):
        from forsch.adk_components.shelby.api import app
        return TestClient(app)

    def test_get_groceries_empty(self, client):
        r = client.get("/api/groceries")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_log_and_get_groceries(self, client):
        r = client.post("/api/groceries", json={
            "items": ["milk", "eggs"],
            "store": "Costco",
            "date": "2026-06-25",
        })
        assert r.status_code == 200
        assert r.json()["count"] == 2

        r = client.get("/api/groceries?since=2026-06-25&until=2026-06-25")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_add_and_get_reminder(self, client):
        r = client.post("/api/reminders", json={"title": "Test", "due": "2026-06-30"})
        assert r.status_code == 200
        assert r.json()["receipt"]["title"] == "Test"

        r = client.get("/api/reminders")
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_add_and_get_chore(self, client):
        r = client.post("/api/chores", json={"title": "Clean", "assignee": "Zach"})
        assert r.status_code == 200
        chore_id = r.json()["chore"]["id"]

        r = client.get("/api/chores")
        assert r.status_code == 200
        assert r.json()["count"] == 1

        r = client.post(f"/api/chores/{chore_id}/check")
        assert r.status_code == 200
        assert r.json()["chore"]["last_done"] is not None

    def test_check_chore_not_found(self, client):
        r = client.post("/api/chores/9999/check")
        assert r.status_code == 404
