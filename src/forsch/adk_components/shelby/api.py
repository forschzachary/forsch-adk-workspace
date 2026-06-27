"""FastAPI endpoints for Shelby — zero-token, no-auth REST API.

Run with: uvicorn forsch.adk_components.shelby.api:app --host 0.0.0.0 --port 8900
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .store import (
    add_chore,
    check_chore,
    get_chores,
    get_groceries,
    init_db,
    log_groceries,
)
from . import remindctl

app = FastAPI(title="Shelby", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


# ── Request / Response models ──────────────────────────────────────────────


class GroceryItem(BaseModel):
    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    store: Optional[str] = None
    date: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None


class GroceryLogRequest(BaseModel):
    items: list[GroceryItem | str]
    store: Optional[str] = None
    date: Optional[str] = None


class ReminderRequest(BaseModel):
    title: str
    list_name: str = "Reminders"
    due: Optional[str] = None
    note: Optional[str] = None


class ChoreRequest(BaseModel):
    title: str
    assignee: Optional[str] = None
    cadence_days: Optional[int] = None
    due: Optional[str] = None
    note: Optional[str] = None


# ── Grocery endpoints ──────────────────────────────────────────────────────


@app.get("/api/groceries")
def api_get_groceries(
    since: Optional[str] = None,
    until: Optional[str] = None,
    name: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    result = get_groceries(since=since, until=until, name=name, limit=limit)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result


@app.post("/api/groceries")
def api_log_groceries(body: GroceryLogRequest) -> dict[str, Any]:
    items = [i.model_dump() if isinstance(i, GroceryItem) else i for i in body.items]
    result = log_groceries(items, store_name=body.store, date=body.date)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error", "bad request"))
    return result


# ── Reminder endpoints ─────────────────────────────────────────────────────


@app.get("/api/reminders")
def api_get_reminders(
    list_name: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    result = remindctl.list_reminders(list_name=list_name, since=since, until=until, status=status)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result


@app.post("/api/reminders")
def api_add_reminder(body: ReminderRequest) -> dict[str, Any]:
    result = remindctl.add_reminder(title=body.title, list_name=body.list_name, due=body.due, note=body.note)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error", "bad request"))
    return result



@app.post("/api/reminders/{reminder_id}/check")
def api_check_reminder(reminder_id: int) -> dict[str, Any]:
    result = remindctl.check_reminder(reminder_id=reminder_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result.get("error", "not found"))
    return result


# ── Chore endpoints ────────────────────────────────────────────────────────


@app.get("/api/chores")
def api_get_chores(
    assignee: Optional[str] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    result = get_chores(assignee=assignee, due_before=due_before, due_after=due_after, limit=limit)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return result


@app.post("/api/chores")
def api_add_chore(body: ChoreRequest) -> dict[str, Any]:
    result = add_chore(title=body.title, assignee=body.assignee, cadence_days=body.cadence_days, due=body.due, note=body.note)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error", "bad request"))
    return result


@app.post("/api/chores/{chore_id}/check")
def api_check_chore(chore_id: int) -> dict[str, Any]:
    result = check_chore(chore_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result.get("error", "not found"))
    return result
