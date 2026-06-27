"""Pydantic models for Shelby SQLite rows."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class GroceryRow(BaseModel):
    id: Optional[int] = None
    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    store: Optional[str] = None
    date: str
    category: Optional[str] = None
    note: Optional[str] = None
    logged_at: str


class ReminderRow(BaseModel):
    id: Optional[int] = None
    title: str
    list_name: str = "Reminders"
    due: Optional[str] = None
    note: Optional[str] = None
    synced: bool = False
    created_at: str


class ChoreRow(BaseModel):
    id: Optional[int] = None
    title: str
    assignee: Optional[str] = None
    cadence_days: Optional[int] = None
    last_done: Optional[str] = None
    due: Optional[str] = None
    note: Optional[str] = None
    created_at: str
