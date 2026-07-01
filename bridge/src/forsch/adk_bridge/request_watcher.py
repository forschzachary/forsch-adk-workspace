"""Proactive notifications — Huberto tells a friend the moment their movie lands (Phase 5).

A background loop, run alongside the bots in one process. Every ``POLL_INTERVAL_SECS`` it walks each
friend's open watches (recorded by ``add_watched_request`` after a ``request_movie``); for each one it
asks the library whether the title is watchable yet (``search_library`` → "available"). When it is, it
DMs the friend once — "🎬 **<title>** is ready to watch!" — and flips ``notified`` so a restart never
re-sends. It also drains the Phase-4 pending-DM queue (credential DMs that were blocked by a 403) here,
and auto-clears watches that have gone stale.

This is intentionally a single-process loop (it shares the bot's event loop); the ``notified`` and
``pending_dm`` flags persist in each friend's JSON record, so on restart the loop simply resumes — no
duplicate DM. A separate systemd poller is a later option if this ever needs to outlive the bot.

Side effects (a real outbound DM) go through ``bot.send_dm``; pass a mock/dry-run sender in tests.
"""
from __future__ import annotations

import asyncio
import logging

from forsch.adk_bridge import friend_memory as fm
from forsch.adk_bridge.screening_room_tools import search_library

_LOG = logging.getLogger("adk_bridge.request_watcher")

POLL_INTERVAL_SECS = 300  # 5 min; jittered slightly to avoid hammering the stack on a fixed beat
READY_TEMPLATE = "🎬 **{title}** is ready to watch! pop into the screening room whenever you like."


def _is_available(title: str) -> bool:
    """Whether the library reports a title as watchable now. Reuses the same 'available' signal the
    rest of Huberto's tools rely on (search_library prints a status column; 'available' = ready)."""
    try:
        out = search_library(title)
    except Exception:
        _LOG.exception("watcher: search_library failed for %r", title)
        return False
    return "available" in (out or "").lower()


async def _drain_pending_dms(bot) -> int:
    """Re-attempt Phase-4 credential DMs that were blocked by a 403. Returns how many landed."""
    delivered = 0
    for discord_id in fm.all_friend_ids():
        pending = fm.get_pending_dm(discord_id)
        if not pending:
            continue
        content = (pending or {}).get("content") or ""
        if not content:
            continue  # a route-blocked marker with no payload yet (nothing to deliver)
        if await bot.send_dm(discord_id, content):
            fm.mark_dm_delivered(discord_id)
            delivered += 1
            _LOG.info("watcher: delivered queued DM to %s", discord_id)
    return delivered


async def _check_watches(bot) -> int:
    """Notify friends whose watched titles have become available. Returns how many DMs were sent."""
    sent = 0
    for discord_id in fm.all_friend_ids():
        for watch in fm.get_watched_requests(discord_id):
            title = watch.get("title") or ""
            tmdb_id = watch.get("tmdb_id") or ""
            if not title:
                continue
            if fm.is_watch_stale(watch):
                fm.clear_watched_request(discord_id, title, tmdb_id)
                _LOG.info("watcher: cleared stale watch %r for %s", title, discord_id)
                continue
            if not _is_available(title):
                continue
            # Mark BEFORE awaiting the send so a crash mid-send can't cause a double DM on the next
            # pass; if the send fails we re-arm so it retries.
            fm.mark_watched_request_notified(discord_id, title, tmdb_id)
            if await bot.send_dm(discord_id, READY_TEMPLATE.format(title=title)):
                sent += 1
                _LOG.info("watcher: notified %s that %r is ready", discord_id, title)
            else:
                # route still closed — undo so we try again next pass instead of silently swallowing
                rearmed = fm.rearm_watched_request(discord_id, title, tmdb_id)
                if rearmed.get("ok"):
                    _LOG.info("watcher: DM to %s blocked, re-armed watch %r", discord_id, title)
                else:
                    # notified=True is still on disk — this friend will NEVER get the
                    # "ready" DM until an operator intervenes. Make it loud.
                    _LOG.error("watcher: DM to %s blocked AND re-arm failed for %r — "
                               "notification may be permanently suppressed", discord_id, title)
    return sent


async def watch_requests(bot, poll_interval: float = POLL_INTERVAL_SECS,
                         iterations: int | None = None) -> None:
    """The watcher loop. Waits for the bot to be online, then polls every `poll_interval` seconds.

    `iterations` bounds the loop (used by tests); None runs forever. `bot` only needs an async
    `send_dm(user_id, content)` — a mock works, so the loop is fully testable without Discord."""
    import random

    wait_ready = getattr(bot, "wait_until_ready", None)
    if wait_ready is not None:
        try:
            await wait_ready()
        except Exception:
            _LOG.exception("watcher: wait_until_ready failed; starting anyway")
    _LOG.info("request watcher started (poll every %ss)", poll_interval)

    n = 0
    while iterations is None or n < iterations:
        try:
            sent = await _check_watches(bot)
            drained = await _drain_pending_dms(bot)
            if sent or drained:
                _LOG.info("watcher pass: %d ready-DM(s), %d queued-DM(s) delivered", sent, drained)
        except Exception:
            _LOG.exception("watcher pass failed; will retry next interval")
        n += 1
        if iterations is not None and n >= iterations:
            break
        # jitter ±10% so multiple titles don't all poll on the same fixed beat
        await asyncio.sleep(poll_interval * (0.9 + 0.2 * random.random()))
