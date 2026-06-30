"""Run the ScreeningRoom Discord bots — the native ADK Discord bot component.

Loads bot tokens + gateway creds from the gitignored ``.adk-local.env``, builds each persona
agent and a persistent SQLite session service, verifies each identity fail-closed, and serves
them concurrently. Person-facing cat runs on Huberto; the internal lead runs on companion-lead.

Run:  python -m forsch.adk_bridge.discord_main   (with FORSCH_ADK_WORKSPACE set, or from the workspace)

Env (gitignored .adk-local.env):
  LITELLM_BASE_URL, LITELLM_HERMES_KEY                 — gateway (cat agent)
  HUBERTO_DISCORD_BOT_TOKEN  (+ HUBERTO_EXPECTED_BOT_ID, default 1499544375204773969)
  COMPANION_LEAD_DISCORD_BOT_TOKEN (+ COMPANION_LEAD_EXPECTED_BOT_ID, default 1512599235910963371)
  CURATOR_DISCORD_BOT_TOKEN (+ CURATOR_EXPECTED_BOT_ID, TV_CHANNEL_ID)  — OPTIONAL third bot
                                                       (SR-1 curator); unset → runs on two bots.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

HUBERTO_DEFAULT_ID = "1499544375204773969"
COMPANION_LEAD_DEFAULT_ID = "1512599235910963371"
CURATOR_DEFAULT_ID = ""  # no registered curator bot id yet — supply via CURATOR_EXPECTED_BOT_ID
TV_CHANNEL_DEFAULT_ID = "1511377396668825662"  # falls back to team-social until #screening-tv exists


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.replace("export ", "").strip(), val.strip().strip('"').strip("'"))


def _workspace() -> Path:
    env = os.environ.get("FORSCH_ADK_WORKSPACE")
    if env:
        return Path(env)
    # bridge/src/forsch/adk_bridge/discord_main.py -> parents[4] == workspace root
    return Path(__file__).resolve().parents[4]


def build_specs():
    from forsch.adk_bridge.cat_persona import make_cat_agent
    from forsch.adk_bridge.discord_bot import BotSpec
    from forsch.adk_bridge.friend_memory import friend_context

    specs = []
    cat_token = os.environ.get("HUBERTO_DISCORD_BOT_TOKEN")
    if cat_token:
        specs.append(BotSpec(
            name="huberto_cat", token=cat_token,
            expected_bot_id=os.environ.get("HUBERTO_EXPECTED_BOT_ID", HUBERTO_DEFAULT_ID),
            agent=make_cat_agent(), dm=True, context_provider=friend_context,
        ))
    lead_token = os.environ.get("COMPANION_LEAD_DISCORD_BOT_TOKEN")
    if lead_token:
        from forsch.adk_bridge.ops_persona import make_ops_agent

        # internal ops lead on companion-lead: channel-only (no DMs), in the team-social channel, and
        # mention-only so it answers only when @-ed rather than on every line of team chatter.
        specs.append(BotSpec(
            name="screening_ops", token=lead_token,
            expected_bot_id=os.environ.get("COMPANION_LEAD_EXPECTED_BOT_ID", COMPANION_LEAD_DEFAULT_ID),
            agent=make_ops_agent(), dm=False, mention_only=True,
            channels=[os.environ.get("OPS_CHANNEL_ID", "1511377396668825662")],
            loader="📋 *checking the board…*",
        ))

    # OPTIONAL third bot — the SR-1 curator. Only runs if CURATOR_DISCORD_BOT_TOKEN is set; with the
    # token unset the system runs unchanged on the two bots above. Needs CURATOR_EXPECTED_BOT_ID too
    # (the identity guard fails closed without it); fail loudly rather than booting as the wrong bot.
    curator_token = os.environ.get("CURATOR_DISCORD_BOT_TOKEN")
    if curator_token:
        from forsch.adk_bridge.curator_persona import make_curator_agent

        curator_id = os.environ.get("CURATOR_EXPECTED_BOT_ID", CURATOR_DEFAULT_ID)
        if not curator_id:
            raise SystemExit(
                "CURATOR_DISCORD_BOT_TOKEN is set but CURATOR_EXPECTED_BOT_ID is not — set the "
                "curator's bot id (from the Discord dev portal) so the identity guard can verify it."
            )
        # SR-1 curator on its own channel (#screening-tv via TV_CHANNEL_ID); channel-only, no DMs.
        specs.append(BotSpec(
            name="screening_curator", token=curator_token,
            expected_bot_id=curator_id,
            agent=make_curator_agent(), dm=False,
            channels=[os.environ.get("TV_CHANNEL_ID", TV_CHANNEL_DEFAULT_ID)],
            loader="🎬 *curating the lineup…*",
        ))
    return specs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    log = logging.getLogger("adk_bridge.discord_main")

    ws = _workspace()
    _load_env(ws / ".adk-local.env")

    if not os.environ.get("LITELLM_BASE_URL"):
        raise SystemExit("no gateway configured — add LITELLM_BASE_URL + a key to .adk-local.env")

    from google.adk.sessions.sqlite_session_service import SqliteSessionService

    from forsch.adk_bridge.discord_bot import get_bot, run_bots
    from forsch.adk_bridge.request_watcher import watch_requests

    db = ws / ".forsch" / "discord_sessions.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    session_service = SqliteSessionService(db_path=str(db))

    specs = build_specs()
    if not specs:
        raise SystemExit(
            "no bot tokens — set HUBERTO_DISCORD_BOT_TOKEN (+ optionally COMPANION_LEAD_DISCORD_BOT_TOKEN "
            "and/or CURATOR_DISCORD_BOT_TOKEN) in .adk-local.env"
        )
    log.info("starting %d Discord bot(s): %s", len(specs), ", ".join(s.name for s in specs))

    has_huberto = any(s.name == "huberto_cat" for s in specs)

    async def _serve() -> None:
        # run_bots registers each client in discord_bot._bots_by_name (before client.start()), so a
        # single scheduler tick after gather starts, get_bot('huberto_cat') resolves. watch_requests
        # then awaits the client's wait_until_ready() before doing any work.
        async def _watch() -> None:
            await asyncio.sleep(0)  # let run_bots register its clients first
            bot = get_bot("huberto_cat")
            if bot is None:
                log.warning("huberto_cat not registered — proactive watcher not started")
                return
            await watch_requests(bot)

        coros = [run_bots(specs, session_service)]
        if has_huberto:
            coros.append(_watch())
        await asyncio.gather(*coros)

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
