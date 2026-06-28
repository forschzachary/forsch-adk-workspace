"""PULL trigger for Team Rooms: poll Gameplan for new comments and hand each to the
core. Chosen over a webhook because the bridge box is Tailscale-only (no public
inbound) — all traffic here is outbound box→public (read comments, post replies).

`poll_once` is the testable unit (cursor in, handle each, cursor out). `run_poller`
is the long-running loop. `SqliteLedger` persists seen-ids + the cursor across restarts.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3

from forsch.adk_bridge.teamrooms.core import handle_comment, _default_run

log = logging.getLogger("teamrooms.poller")


class SqliteLedger:
    """Persistent idempotency ledger + poll cursor (one small sqlite file)."""

    def __init__(self, db_path):
        self._db = sqlite3.connect(db_path)
        self._db.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY)")
        self._db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
        self._db.commit()

    def seen(self, cid):
        return self._db.execute("SELECT 1 FROM seen WHERE id=?", (cid,)).fetchone() is not None

    def mark(self, cid):
        self._db.execute("INSERT OR IGNORE INTO seen (id) VALUES (?)", (cid,))
        self._db.commit()

    def get_cursor(self, default=None):
        row = self._db.execute("SELECT v FROM kv WHERE k='cursor'").fetchone()
        return row[0] if row else default

    def set_cursor(self, value):
        self._db.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('cursor', ?)", (value,))
        self._db.commit()


async def poll_once(client, runtime, config, ledger, bot_email, *, run_fn=_default_run):
    """One poll cycle. Fetch comments after the cursor, handle each, advance the cursor."""
    cursor = ledger.get_cursor(config.get("start_cursor"))
    comments = client.list_comments_since(cursor)
    results = []
    for c in comments:
        res = await handle_comment(
            c, client=client, runtime=runtime, config=config,
            ledger=ledger, bot_email=bot_email, run_fn=run_fn,
        )
        results.append(res)
        if c.get("creation"):
            ledger.set_cursor(c["creation"])  # monotonic — comments come asc by creation
    return {"polled": len(comments), "results": results}


async def run_poller(config, *, runtime, client, bot_email, ledger=None, stop_event=None):
    """Long-running PULL loop. Background-task-friendly (cancellable via stop_event)."""
    ledger = ledger or SqliteLedger(config["ledger_db"])
    interval = config.get("poll_interval_seconds", 10)
    log.info("teamrooms poller starting (interval=%ss, bot=%s)", interval, bot_email)
    while not (stop_event and stop_event.is_set()):
        try:
            summary = await poll_once(client, runtime, config, ledger, bot_email)
            if summary["polled"]:
                log.info("teamrooms poll handled %s comment(s)", summary["polled"])
        except Exception:
            log.exception("teamrooms poll cycle failed")
        await asyncio.sleep(interval)
