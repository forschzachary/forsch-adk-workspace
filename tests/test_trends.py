"""Tests for the Shelby chore-trend engine."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

# Patch DB_PATH before importing store so tests use a temp database
_tmp_dir = None
_tmp_db = None

import forsch.adk_components.shelby.store as store_mod


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path):
    """Create a fresh temp DB for each test with a known set of chores."""
    global _tmp_dir, _tmp_db
    _tmp_db = tmp_path / "test_trends.db"
    store_mod.DB_PATH = _tmp_db

    # Use inline schema so tests don't depend on remote file
    conn = store_mod.get_db()
    conn.executescript(
        """
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
    yield
    store_mod.DB_PATH = Path("/opt/data/shelby.db")


def _insert_chore(
    conn: sqlite3.Connection,
    title: str,
    assignee: str | None = None,
    cadence_days: int | None = None,
    last_done: str | None = None,
    due: str | None = None,
    created_at: str = "2026-01-01T00:00:00Z",
) -> int:
    """Insert a chore and return its id."""
    cur = conn.execute(
        "INSERT INTO chores (title, assignee, cadence_days, last_done, due, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, NULL, ?)",
        (title, assignee, cadence_days, last_done, due, created_at),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def chores_today():
    """Insert a representative set of chores relative to 'today' (2026-06-26)."""
    today = date(2026, 6, 26)
    conn = store_mod.get_db()
    chores = {}

    # Overdue: due 5 days ago, never done
    chores["overdue"] = _insert_chore(
        conn, "Clean garage", assignee="Zach",
        due=(today - timedelta(days=5)).isoformat(),
        cadence_days=14,
    )

    # Due soon: due tomorrow
    chores["due_soon"] = _insert_chore(
        conn, "Vacuum living room", assignee="Shelby",
        due=(today + timedelta(days=1)).isoformat(),
    )

    # On-cadence: last_done 3 days ago, cadence is 7
    chores["on_cadence"] = _insert_chore(
        conn, "Mow lawn", assignee="Zach",
        cadence_days=7,
        last_done=(today - timedelta(days=3)).isoformat(),
        due=(today + timedelta(days=4)).isoformat(),
    )

    # Off-cadence: last_done 20 days ago, cadence is 7
    chores["off_cadence"] = _insert_chore(
        conn, "Deep clean kitchen", assignee="Shelby",
        cadence_days=7,
        last_done=(today - timedelta(days=20)).isoformat(),
        due=(today - timedelta(days=6)).isoformat(),
    )

    # Never-done chore with cadence
    chores["never_done"] = _insert_chore(
        conn, "Replace air filter", assignee="Zach",
        cadence_days=30,
    )

    # No-due chore (shouldn't appear in overdue/due_soon)
    chores["no_due"] = _insert_chore(
        conn, "Organize closet", assignee="Shelby",
    )

    # Completed recently (not overdue)
    chores["completed"] = _insert_chore(
        conn, "Take out trash", assignee="Zach",
        due=(today - timedelta(days=2)).isoformat(),
        last_done=(today - timedelta(days=1)).isoformat(),
    )

    conn.close()
    return chores


class TestGetOverdueChores:
    def test_returns_overdue_items(self, chores_today):
        from forsch.adk_components.shelby.trends import get_overdue_chores
        overdue = get_overdue_chores(as_of="2026-06-26")
        titles = [c["title"] for c in overdue]
        assert "Clean garage" in titles
        assert "Deep clean kitchen" in titles

    def test_excludes_completed(self, chores_today):
        from forsch.adk_components.shelby.trends import get_overdue_chores
        overdue = get_overdue_chores(as_of="2026-06-26")
        titles = [c["title"] for c in overdue]
        # Take out trash was completed yesterday, due 2 days ago -- NOT overdue
        assert "Take out trash" not in titles

    def test_days_overdue_calculation(self, chores_today):
        from forsch.adk_components.shelby.trends import get_overdue_chores
        overdue = get_overdue_chores(as_of="2026-06-26")
        garage = [c for c in overdue if c["title"] == "Clean garage"][0]
        assert garage["days_overdue"] == 5

    def test_includes_required_fields(self, chores_today):
        from forsch.adk_components.shelby.trends import get_overdue_chores
        overdue = get_overdue_chores(as_of="2026-06-26")
        for c in overdue:
            assert "id" in c
            assert "title" in c
            assert "assignee" in c
            assert "due" in c
            assert "days_overdue" in c
            assert "cadence_days" in c

    def test_sorted_by_days_overdue_desc(self, chores_today):
        from forsch.adk_components.shelby.trends import get_overdue_chores
        overdue = get_overdue_chores(as_of="2026-06-26")
        days = [c["days_overdue"] for c in overdue]
        assert days == sorted(days, reverse=True)


class TestGetDueSoonChores:
    def test_returns_due_soon_items(self, chores_today):
        from forsch.adk_components.shelby.trends import get_due_soon_chores
        due_soon = get_due_soon_chores(within_days=3, as_of="2026-06-26")
        titles = [c["title"] for c in due_soon]
        # Vacuum is due tomorrow (1 day away)
        assert "Vacuum living room" in titles

    def test_excludes_overdue(self, chores_today):
        from forsch.adk_components.shelby.trends import get_due_soon_chores
        due_soon = get_due_soon_chores(within_days=3, as_of="2026-06-26")
        titles = [c["title"] for c in due_soon]
        assert "Clean garage" not in titles  # 5 days overdue, not "due soon"

    def test_excludes_far_future(self, chores_today):
        from forsch.adk_components.shelby.trends import get_due_soon_chores
        due_soon = get_due_soon_chores(within_days=3, as_of="2026-06-26")
        titles = [c["title"] for c in due_soon]
        # Mow lawn due in 4 days -- outside 3-day window
        assert "Mow lawn" not in titles

    def test_days_until_due(self, chores_today):
        from forsch.adk_components.shelby.trends import get_due_soon_chores
        due_soon = get_due_soon_chores(within_days=3, as_of="2026-06-26")
        vacuum = [c for c in due_soon if c["title"] == "Vacuum living room"][0]
        assert vacuum["days_until_due"] == 1

    def test_sorted_by_days_until_due_asc(self, chores_today):
        from forsch.adk_components.shelby.trends import get_due_soon_chores
        due_soon = get_due_soon_chores(within_days=7, as_of="2026-06-26")
        days = [c["days_until_due"] for c in due_soon]
        assert days == sorted(days)


class TestGetCadenceStats:
    def test_identifies_on_cadence(self, chores_today):
        from forsch.adk_components.shelby.trends import get_cadence_stats
        stats = get_cadence_stats(as_of="2026-06-26")
        mow = [c for c in stats["chores"] if c["title"] == "Mow lawn"][0]
        assert mow["on_cadence"] is True
        assert mow["status"] == "on_cadence"

    def test_identifies_off_cadence(self, chores_today):
        from forsch.adk_components.shelby.trends import get_cadence_stats
        stats = get_cadence_stats(as_of="2026-06-26")
        kitchen = [c for c in stats["chores"] if c["title"] == "Deep clean kitchen"][0]
        assert kitchen["on_cadence"] is False
        assert kitchen["status"] == "off_cadence"
        assert kitchen["missed_cycles"] >= 1

    def test_identifies_never_done(self, chores_today):
        from forsch.adk_components.shelby.trends import get_cadence_stats
        stats = get_cadence_stats(as_of="2026-06-26")
        air = [c for c in stats["chores"] if c["title"] == "Replace air filter"][0]
        assert air["status"] == "never_done"
        assert air["on_cadence"] is False

    def test_missed_cycles_count(self, chores_today):
        from forsch.adk_components.shelby.trends import get_cadence_stats
        stats = get_cadence_stats(as_of="2026-06-26")
        kitchen = [c for c in stats["chores"] if c["title"] == "Deep clean kitchen"][0]
        # last_done 20 days ago, cadence 7: 20//7 = 2 full cycles, minus 1 = 1 missed
        assert kitchen["missed_cycles"] >= 1

    def test_summary_counts(self, chores_today):
        from forsch.adk_components.shelby.trends import get_cadence_stats
        stats = get_cadence_stats(as_of="2026-06-26")
        assert stats["summary"]["total"] >= 3  # mow, kitchen, air filter have cadence
        assert stats["summary"]["on_cadence"] >= 1  # at least mow lawn

    def test_excludes_non_cadence_chores(self, chores_today):
        from forsch.adk_components.shelby.trends import get_cadence_stats
        stats = get_cadence_stats(as_of="2026-06-26")
        titles = [c["title"] for c in stats["chores"]]
        # Vacuum and Organize closet have no cadence_days
        assert "Vacuum living room" not in titles
        assert "Organize closet" not in titles


class TestGetAssigneeSplit:
    def test_groups_by_assignee(self, chores_today):
        from forsch.adk_components.shelby.trends import get_assignee_split
        split = get_assignee_split(as_of="2026-06-26")
        assert "Zach" in split
        assert "Shelby" in split
        assert split["Zach"]["total"] >= 3  # garage, mow, air, trash
        assert split["Shelby"]["total"] >= 2  # vacuum, kitchen, closet

    def test_overdue_counts(self, chores_today):
        from forsch.adk_components.shelby.trends import get_assignee_split
        split = get_assignee_split(as_of="2026-06-26")
        assert split["Zach"]["overdue"] >= 1  # garage
        assert split["Shelby"]["overdue"] >= 1  # kitchen

    def test_due_soon_counts(self, chores_today):
        from forsch.adk_components.shelby.trends import get_assignee_split
        split = get_assignee_split(as_of="2026-06-26")
        assert split["Shelby"]["due_soon"] >= 1  # vacuum

    def test_unassigned_grouping(self, chores_today):
        from forsch.adk_components.shelby.trends import get_assignee_split
        # Add an unassigned chore
        conn = store_mod.get_db()
        _insert_chore(conn, "Mystery chore", assignee=None, due="2026-06-27")
        conn.close()
        split = get_assignee_split(as_of="2026-06-26")
        assert "unassigned" in split
        assert split["unassigned"]["total"] >= 1


class TestGetChoreSummary:
    def test_combines_all_analyses(self, chores_today):
        from forsch.adk_components.shelby.trends import get_chore_summary
        summary = get_chore_summary(as_of="2026-06-26")
        assert "overdue" in summary
        assert "due_soon" in summary
        assert "cadence_stats" in summary
        assert "assignee_split" in summary
        assert "total_chores" in summary
        assert "completion_rate" in summary

    def test_total_chores_count(self, chores_today):
        from forsch.adk_components.shelby.trends import get_chore_summary
        summary = get_chore_summary(as_of="2026-06-26")
        # We inserted 7 chores
        assert summary["total_chores"] == 7

    def test_completion_rate(self, chores_today):
        from forsch.adk_components.shelby.trends import get_chore_summary
        summary = get_chore_summary(as_of="2026-06-26")
        # 1 of 7 chores completed in last 30 days (Take out trash)
        assert summary["completion_rate"] > 0
        assert summary["completion_rate"] <= 100


class TestCompletionRate:
    def test_all_completed(self):
        from forsch.adk_components.shelby.trends import get_chore_summary
        conn = store_mod.get_db()
        today = date(2026, 6, 26)
        for i in range(3):
            _insert_chore(
                conn, f"Chore {i}",
                last_done=(today - timedelta(days=i)).isoformat(),
                due=(today - timedelta(days=i + 1)).isoformat(),
            )
        conn.close()
        summary = get_chore_summary(as_of="2026-06-26")
        assert summary["completion_rate"] == 100.0

    def test_none_completed(self):
        from forsch.adk_components.shelby.trends import get_chore_summary
        conn = store_mod.get_db()
        for i in range(3):
            _insert_chore(conn, f"Chore {i}", due="2026-07-01")
        conn.close()
        summary = get_chore_summary(as_of="2026-06-26")
        assert summary["completion_rate"] == 0.0


class TestEmptyChores:
    def test_overdue_empty(self):
        from forsch.adk_components.shelby.trends import get_overdue_chores
        assert get_overdue_chores(as_of="2026-06-26") == []

    def test_due_soon_empty(self):
        from forsch.adk_components.shelby.trends import get_due_soon_chores
        assert get_due_soon_chores(as_of="2026-06-26") == []

    def test_cadence_stats_empty(self):
        from forsch.adk_components.shelby.trends import get_cadence_stats
        stats = get_cadence_stats(as_of="2026-06-26")
        assert stats["chores"] == []
        assert stats["summary"]["total"] == 0

    def test_assignee_split_empty(self):
        from forsch.adk_components.shelby.trends import get_assignee_split
        assert get_assignee_split(as_of="2026-06-26") == {}

    def test_summary_empty(self):
        from forsch.adk_components.shelby.trends import get_chore_summary
        summary = get_chore_summary(as_of="2026-06-26")
        assert summary["total_chores"] == 0
        assert summary["completion_rate"] == 0.0
