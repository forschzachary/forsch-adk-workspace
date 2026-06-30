"""Per-user sliding-window rate limits on the expensive ScreeningRoom actions.

A small in-memory limiter: each ``(user_id, action)`` keeps a deque of recent call timestamps; a call
is allowed only if fewer than ``limit`` of them fall inside the trailing ``window`` seconds. This caps
abuse of the actions that spend real resources or hit the live stack:

  provision_access   3 / day     (creating a real Jellyfin account)
  reset_access       5 / hour    (rotating a password)
  request_movie     10 / hour    (kicking off a real download)
  retry_failed       5 / 10 min  (re-poking the pipeline)

In-memory is deliberate: there's one ``discord_main`` process, so a dict is enough and has no I/O on
the hot path. (If this ever scales to multiple processes, swap the store for a file-with-locks/Redis —
the ``check_rate_limit`` signature stays the same.) An unknown action is unlimited (allowed), so a new
tool isn't silently throttled before it's configured.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

# action -> (max_calls, window_seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "provision_access": (3, 24 * 60 * 60),   # 3 per day
    "reset_access": (5, 60 * 60),            # 5 per hour
    "request_movie": (10, 60 * 60),          # 10 per hour
    "retry_failed": (5, 10 * 60),            # 5 per 10 minutes
}

_calls: dict[tuple[str, str], deque] = defaultdict(deque)
_lock = threading.Lock()


def _human_window(seconds: int) -> str:
    if seconds % (24 * 60 * 60) == 0:
        n = seconds // (24 * 60 * 60)
        return "day" if n == 1 else f"{n} days"
    if seconds % (60 * 60) == 0:
        n = seconds // (60 * 60)
        return "hour" if n == 1 else f"{n} hours"
    if seconds % 60 == 0:
        n = seconds // 60
        return "minute" if n == 1 else f"{n} minutes"
    return f"{seconds}s"


def check_rate_limit(user_id: str, action: str, now: float | None = None) -> dict:
    """Record + check a call of ``action`` by ``user_id`` against its sliding window.

    Returns {ok: True, remaining: N} when allowed (and counts the call), or
    {ok: False, retry_after: secs, reason: str} when the window is full (the call is NOT counted).
    An action with no configured limit is always allowed (ok=True, remaining=-1)."""
    limit = LIMITS.get(action)
    if limit is None:
        return {"ok": True, "remaining": -1}
    max_calls, window = limit
    now = time.time() if now is None else now
    cutoff = now - window
    key = (str(user_id), action)
    with _lock:
        dq = _calls[key]
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= max_calls:
            retry_after = int(dq[0] + window - now) + 1
            return {
                "ok": False,
                "retry_after": retry_after,
                "reason": (
                    f"rate limit: {max_calls} {action} per {_human_window(window)} — "
                    f"try again in ~{_retry_phrase(retry_after)}."
                ),
            }
        dq.append(now)
        return {"ok": True, "remaining": max_calls - len(dq)}


def _retry_phrase(seconds: int) -> str:
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def reset_all() -> None:
    """Clear all recorded calls — for tests only (the process never needs this at runtime)."""
    with _lock:
        _calls.clear()
