"""Tests for Shelby reminders -- remindctl, tools, Apple sync, honest receipts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

_tmp_dir = tempfile.mkdtemp()
_tmp_db = Path(_tmp_dir) / "test_reminders.db"

import forsch.adk_components.shelby.store as store_mod
store_mod.DB_PATH = _tmp_db

from forsch.adk_components.shelby import remindctl
from forsch.adk_components.shelby.apple_sync import AppleRemindersSync, SyncResult
from forsch.adk_components.shelby.tools import (
    add_reminder_tool,
    check_reminder_tool,
    list_reminders_tool,
)


@pytest.fixture(autouse=True)
def _fresh_db():
    store_mod.DB_PATH = _tmp_db
    _tmp_db.unlink(missing_ok=True)
    # init_db() falls back to inline DDL when no schema file is present.
    store_mod.init_db()
    yield
    _tmp_db.unlink(missing_ok=True)


class TestAddReminder:
    def test_returns_honest_receipt(self):
        result = remindctl.add_reminder("Take out trash", due="2026-06-27")
        assert result["ok"] is True
        r = result["receipt"]
        assert r["title"] == "Take out trash"
        assert r["list"] == "Reminders"
        assert r["due"] == "2026-06-27"
        assert r["synced"] is False
        assert "not yet synced" in r["status"]
        assert "saved locally" in r["status"]

    def test_honest_receipt_never_says_done(self):
        result = remindctl.add_reminder("Milk")
        r = result["receipt"]
        assert r["status"] != "done"
        assert r["status"] != "synced"

    def test_custom_list_name(self):
        result = remindctl.add_reminder("Work task", list_name="Work")
        assert result["receipt"]["list"] == "Work"

    def test_with_note(self):
        result = remindctl.add_reminder("Call dentist", note="Ask about Tuesday")
        assert result["receipt"]["note"] == "Ask about Tuesday"


class TestListReminders:
    def test_list_all(self):
        remindctl.add_reminder("A")
        remindctl.add_reminder("B")
        result = remindctl.list_reminders()
        assert result["ok"] is True
        assert result["count"] == 2

    def test_filter_by_list(self):
        remindctl.add_reminder("Work", list_name="Work")
        remindctl.add_reminder("Home", list_name="Home")
        result = remindctl.list_reminders(list_name="Work")
        assert result["count"] == 1
        assert result["records"][0]["title"] == "Work"

    def test_filter_pending(self):
        r1 = remindctl.add_reminder("Task 1")
        r2 = remindctl.add_reminder("Task 2")
        remindctl.check_reminder(r1["receipt"]["id"])
        result = remindctl.list_reminders(status="pending")
        assert result["count"] == 1
        assert result["records"][0]["title"] == "Task 2"

    def test_filter_completed(self):
        r1 = remindctl.add_reminder("Done task")
        remindctl.check_reminder(r1["receipt"]["id"])
        result = remindctl.list_reminders(status="completed")
        assert result["count"] == 1


class TestCheckReminder:
    def test_marks_done(self):
        result = remindctl.add_reminder("Clean garage")
        rid = result["receipt"]["id"]
        check = remindctl.check_reminder(rid)
        assert check["ok"] is True
        r = check["receipt"]
        assert r["synced"] is False
        assert "completed" in r["status"].lower()
        assert "not yet synced" in r["status"]

    def test_not_found(self):
        result = remindctl.check_reminder(99999)
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_invalid_id_rejected(self):
        with pytest.raises(Exception):
            remindctl.CheckArgs(reminder_id=0)
        with pytest.raises(Exception):
            remindctl.CheckArgs(reminder_id=-1)


class TestPydanticValidation:
    def test_empty_title_rejected(self):
        with pytest.raises(Exception):
            remindctl.ReminderArgs(title="")

    def test_whitespace_title_rejected(self):
        with pytest.raises(Exception):
            remindctl.ReminderArgs(title="   ")

    def test_empty_list_rejected(self):
        with pytest.raises(Exception):
            remindctl.ReminderArgs(title="Task", list_name="")


class TestToolWrappers:
    def test_add_tool_returns_json(self):
        raw = add_reminder_tool("Buy eggs", due="2026-06-30")
        data = json.loads(raw)
        assert data["ok"] is True
        assert data["receipt"]["title"] == "Buy eggs"

    def test_list_tool_returns_json(self):
        add_reminder_tool("A")
        raw = list_reminders_tool()
        data = json.loads(raw)
        assert data["count"] >= 1

    def test_check_tool_returns_json(self):
        add_reminder_tool("To check")
        items = json.loads(list_reminders_tool())
        rid = items["records"][0]["id"]
        raw = check_reminder_tool(rid)
        data = json.loads(raw)
        assert data["ok"] is True
        assert "not yet synced" in data["receipt"]["status"]


class TestAppleSyncAdapter:
    @pytest.mark.skip(reason="Apple sync not yet implemented -- interface only")
    def test_sync_reminder_not_implemented(self):
        class DummySync(AppleRemindersSync):
            def sync_reminder(self, reminder_id):
                return SyncResult(synced=False, device="none", error="not implemented")
            def sync_all_pending(self):
                return []
            def is_available(self):
                return False
        sync = DummySync()
        result = sync.sync_reminder(1)
        assert result.synced is False

    def test_sync_result_model(self):
        sr = SyncResult(synced=False, device="iPhone", error=None)
        assert sr.synced is False
        assert sr.device == "iPhone"
        assert sr.error is None
