"""Deterministic chore-trend engine for Shelby.

Pure-Python math over the chores table -- no LLM in the calculation path.
The agent narrates, the engine computes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .store import get_db


def _today(as_of: str | None = None) -> date:
    """Parse as_of string or return today's date."""
    if as_of:
        return date.fromisoformat(as_of[:10])
    return date.today()


def _parse_date(val: str | None) -> date | None:
    """Extract a date from an ISO datetime or date string."""
    if not val:
        return None
    return date.fromisoformat(val[:10])


def _days_between(a: date, b: date) -> int:
    """Absolute days between two dates."""
    return abs((b - a).days)


def get_overdue_chores(as_of: str | None = None) -> list[dict[str, Any]]:
    """Return chores where due < as_of and not yet completed.

    A chore is considered incomplete when:
    - last_done is NULL, or
    - last_done (date portion) < due

    Each result includes: id, title, assignee, due, days_overdue, cadence_days.
    """
    ref = _today(as_of)
    conn = get_db()
    rows = conn.execute("SELECT * FROM chores WHERE due IS NOT NULL").fetchall()
    conn.close()

    overdue: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        due = _parse_date(r["due"])
        if due is None or due >= ref:
            continue
        last_done = _parse_date(r.get("last_done"))
        # Incomplete if never done, or done before the current due
        if last_done is not None and last_done >= due:
            continue
        overdue.append({
            "id": r["id"],
            "title": r["title"],
            "assignee": r["assignee"],
            "due": r["due"],
            "days_overdue": _days_between(due, ref),
            "cadence_days": r.get("cadence_days"),
        })
    overdue.sort(key=lambda x: -x["days_overdue"])
    return overdue


def get_due_soon_chores(within_days: int = 3, as_of: str | None = None) -> list[dict[str, Any]]:
    """Return chores where due is within within_days of as_of (inclusive).

    Each result includes: id, title, assignee, due, days_until_due.
    """
    ref = _today(as_of)
    cutoff = ref + timedelta(days=within_days)
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chores WHERE due IS NOT NULL AND due >= :ref AND due <= :cutoff",
        {"ref": ref.isoformat(), "cutoff": cutoff.isoformat()},
    ).fetchall()
    conn.close()

    due_soon: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        due = _parse_date(r["due"])
        if due is None:
            continue
        due_soon.append({
            "id": r["id"],
            "title": r["title"],
            "assignee": r["assignee"],
            "due": r["due"],
            "days_until_due": _days_between(ref, due),
        })
    due_soon.sort(key=lambda x: x["days_until_due"])
    return due_soon


def get_cadence_stats(as_of: str | None = None) -> dict[str, Any]:
    """Compute cadence analysis for all chores with cadence_days set.

    Per-chore:
    - on_cadence: last_done + cadence_days >= as_of
    - missed_cycles: how many cadence cycles missed since last_done
    - avg_days_between: average days between completions (based on cadence)

    Returns {"chores": [...], "summary": {on_cadence, missed, total}}.
    """
    ref = _today(as_of)
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chores WHERE cadence_days IS NOT NULL AND cadence_days > 0"
    ).fetchall()
    conn.close()

    chores: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        last_done = _parse_date(r.get("last_done"))
        cadence = r["cadence_days"]

        if last_done is None:
            chores.append({
                "id": r["id"],
                "title": r["title"],
                "assignee": r["assignee"],
                "cadence_days": cadence,
                "on_cadence": False,
                "missed_cycles": 0,
                "avg_days_between": None,
                "status": "never_done",
            })
            continue

        days_since_done = _days_between(last_done, ref)
        on_cadence = days_since_done <= cadence
        missed_cycles = max(0, (days_since_done // cadence) - 1) if days_since_done > cadence else 0

        chores.append({
            "id": r["id"],
            "title": r["title"],
            "assignee": r["assignee"],
            "cadence_days": cadence,
            "on_cadence": on_cadence,
            "missed_cycles": missed_cycles,
            "avg_days_between": cadence,
            "status": "on_cadence" if on_cadence else "off_cadence",
        })

    total = len(chores)
    on_cadence_count = sum(1 for c in chores if c["on_cadence"])
    missed_count = sum(c["missed_cycles"] for c in chores)

    return {
        "chores": chores,
        "summary": {
            "total": total,
            "on_cadence": on_cadence_count,
            "missed": missed_count,
        },
    }


def get_assignee_split(as_of: str | None = None) -> dict[str, dict[str, Any]]:
    """Group chores by assignee with overdue/due-soon counts.

    Returns {assignee: {total, overdue, due_soon}}.
    Unassigned chores go under "unassigned".
    """
    overdue = get_overdue_chores(as_of)
    due_soon = get_due_soon_chores(as_of=as_of)

    conn = get_db()
    rows = conn.execute("SELECT * FROM chores").fetchall()
    conn.close()

    split: dict[str, dict[str, Any]] = {}
    for row in rows:
        r = dict(row)
        assignee = r.get("assignee") or "unassigned"
        if assignee not in split:
            split[assignee] = {"total": 0, "overdue": 0, "due_soon": 0}
        split[assignee]["total"] += 1

    overdue_ids = {c["id"] for c in overdue}
    due_soon_ids = {c["id"] for c in due_soon}

    for row in rows:
        r = dict(row)
        assignee = r.get("assignee") or "unassigned"
        if r["id"] in overdue_ids:
            split[assignee]["overdue"] += 1
        if r["id"] in due_soon_ids:
            split[assignee]["due_soon"] += 1

    return split


def get_chore_summary(as_of: str | None = None) -> dict[str, Any]:
    """Combine all trend analyses into one summary.

    Returns overdue, due_soon, cadence_stats, assignee_split,
    total_chores, and completion_rate (completed in last 30 days).
    """
    ref = _today(as_of)
    overdue = get_overdue_chores(as_of)
    due_soon = get_due_soon_chores(as_of=as_of)
    cadence_stats = get_cadence_stats(as_of)
    assignee_split = get_assignee_split(as_of)

    conn = get_db()
    rows = conn.execute("SELECT * FROM chores").fetchall()
    total_chores = len(rows)

    thirty_days_ago = (ref - timedelta(days=30)).isoformat()
    completed_count = 0
    for row in rows:
        r = dict(row)
        last_done = _parse_date(r.get("last_done"))
        if last_done and last_done >= _parse_date(thirty_days_ago):
            completed_count += 1

    completion_rate = round(completed_count / total_chores * 100, 1) if total_chores > 0 else 0.0

    conn.close()

    return {
        "overdue": overdue,
        "due_soon": due_soon,
        "cadence_stats": cadence_stats,
        "assignee_split": assignee_split,
        "total_chores": total_chores,
        "completion_rate": completion_rate,
    }
