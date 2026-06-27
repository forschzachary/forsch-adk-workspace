"""LLM tool wrappers for Shelby reminders.

These are the constrained functions the LLM agent calls. All args are
Pydantic-validated; the agent cannot smuggle arbitrary data past the
schema. Returns JSON string receipts — never raw dicts.
"""

from __future__ import annotations

import json
from typing import Optional

from . import remindctl


def add_reminder_tool(
    title: str,
    list_name: str = "Reminders",
    due: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    """Add a reminder via the LLM tool interface.

    Validates all args through Pydantic before hitting remindctl.
    Returns a JSON string receipt — never claims sync.
    """
    result = remindctl.add_reminder(title=title, list_name=list_name, due=due, note=note)
    return json.dumps(result, default=str)


def list_reminders_tool(
    list_name: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """List reminders with optional filters. Returns JSON string."""
    result = remindctl.list_reminders(list_name=list_name, since=since, until=until, status=status)
    return json.dumps(result, default=str)


def check_reminder_tool(reminder_id: int) -> str:
    """Mark a reminder as completed. Returns JSON string receipt."""
    result = remindctl.check_reminder(reminder_id=reminder_id)
    return json.dumps(result, default=str)
