"""@receipt — honest-readback decorator for state-mutating tools.

---
keywords: [receipt, honest, save-locally, sync-pending, claim, readback, verification]
intention: "Saves you from agents lying about 'I reminded you' / 'I saved it' / 'I sent the email' when the write was local-only. Forces every state-mutating tool to return a structured receipt the agent MUST read back to the user."
function: "Decorator that wraps a write tool, forcing structured receipts with synced: <truth>."
depends_on: []
used_by: [add_reminder, log_groceries, log_grocery_email_receipt]
example: "@receipt(claim='synced to iPhone'); def add_reminder(...): ..."
---
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable


def receipt(*, claim: str, what: str = "write"):
    """Decorator forcing a structured honest-receipt return value.

    The wrapped function must return a dict with at minimum {"ok": bool}.
    The decorator:
      - Adds "claim" (what the agent would say if it worked) and "synced" (the truth)
      - Adds "receipted_at" timestamp
      - Re-raises if the tool returned None (programmer error)

    Usage:
        @receipt(claim="synced to iPhone", what="reminder")
        def add_reminder(title, list_name, due):
            ...  # returns {"ok": True, "saved": {...}}
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> dict[str, Any]:
            result = func(*args, **kwargs)
            if result is None:
                raise RuntimeError(
                    f"@receipt: {func.__name__} returned None — should return a dict "
                    f"with at least {{'ok': bool}}."
                )
            if not isinstance(result, dict):
                raise RuntimeError(
                    f"@receipt: {func.__name__} returned {type(result).__name__}, "
                    f"expected dict."
                )
            result.setdefault("claim", claim)
            result.setdefault("synced", False)
            result.setdefault("what", what)
            result.setdefault("receipted_at", time.time())
            return result
        return wrapper
    return decorator
