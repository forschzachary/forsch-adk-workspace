"""Wire the Team Rooms poller into the bridge's FastAPI startup — gated so it only
runs when explicitly enabled AND fully configured (creds + base + bot user). The
gate is a pure function (tested); the startup glue is a thin one-liner.

Live hook (in http.py):
    @app.on_event("startup")
    async def _teamrooms():
        from forsch.adk_bridge.teamrooms.wiring import maybe_start_poller
        maybe_start_poller()
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("teamrooms.wiring")


def poller_gate(config, env):
    """Return ``(ok, reason)`` — whether the poller should start, given the bridge
    config dict and an env mapping. Pure (no I/O) so it's trivially unit-tested."""
    tr = config.get("teamrooms") or {}
    if not tr.get("enabled"):
        return False, "disabled"
    if not (env.get("GAMEPLAN_BOT_KEY") and env.get("GAMEPLAN_BOT_SECRET")):
        return False, "missing_creds"
    if not tr.get("bot_user"):
        return False, "missing_bot_user"
    if not (tr.get("base_url") or env.get("GAMEPLAN_BASE_URL")):
        return False, "missing_base_url"
    return True, "ok"


def maybe_start_poller():
    """Start the Team Rooms poller as a background task iff the gate passes. Safe no-op
    otherwise (logs the reason). Called from the FastAPI startup event."""
    from forsch.adk_bridge.runtime import get_runtime
    from forsch.adk_bridge.teamrooms.client import GameplanClient
    from forsch.adk_bridge.teamrooms.poller import SqliteLedger, run_poller

    runtime = get_runtime()
    ok, reason = poller_gate(runtime.config, os.environ)
    if not ok:
        log.info("teamrooms poller not started: %s", reason)
        return None

    tr = runtime.config["teamrooms"]
    client = GameplanClient(
        base_url=tr.get("base_url") or os.environ["GAMEPLAN_BASE_URL"],
        api_key=os.environ["GAMEPLAN_BOT_KEY"],
        api_secret=os.environ["GAMEPLAN_BOT_SECRET"],
    )
    ledger = SqliteLedger(tr.get("ledger_db", "data/teamrooms_ledger.db"))
    task = asyncio.create_task(
        run_poller(tr, runtime=runtime, client=client, bot_email=tr["bot_user"], ledger=ledger)
    )
    log.info("teamrooms poller started (bot=%s, interval=%ss)", tr["bot_user"], tr.get("poll_interval_seconds", 10))
    return task
