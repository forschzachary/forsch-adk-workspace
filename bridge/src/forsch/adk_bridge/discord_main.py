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
    """Build a BotSpec for every native bot whose token is set.

    Single source of truth: iterates ``native_bots.NATIVE_BOTS`` (the SAME registry the live graph
    reads via graph_manifest), filtering by which Discord tokens are present. So adding/removing a bot
    in NATIVE_BOTS changes BOTH the running fleet and the map — they cannot diverge.
    """
    from forsch.adk_bridge.discord_bot import BotSpec
    from forsch.adk_bridge.native_bots import NATIVE_BOTS

    specs = []
    for bot in NATIVE_BOTS:
        token = os.environ.get(bot.token_env)
        if not token:
            continue
        # Identity guard fails closed: a bot whose expected id can't be resolved must not boot.
        expected_id = os.environ.get(bot.expected_id_env, bot.expected_id_default)
        if not expected_id:
            raise SystemExit(
                f"{bot.token_env} is set but {bot.expected_id_env} is not — set the bot id "
                "(from the Discord dev portal) so the identity guard can verify it."
            )
        kwargs = dict(name=bot.bot_name, token=token, expected_bot_id=expected_id,
                      agent=bot.make_agent(), dm=bot.dm)
        if bot.mention_only:
            kwargs["mention_only"] = True
        if bot.context_provider is not None:
            kwargs["context_provider"] = bot.context_provider
        if bot.loader:
            kwargs["loader"] = bot.loader
        if not bot.dm and bot.channel_env:
            kwargs["channels"] = [os.environ.get(bot.channel_env, bot.channel_default)]
        specs.append(BotSpec(**kwargs))
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
    if has_huberto:
        from forsch.adk_bridge.a2a_delegation import SPECIALISTS

        log.info("exposing %d specialist(s) over A2A for huberto to delegate to: %s",
                 len(SPECIALISTS), ", ".join(f"{n}:{s['port']}" for n, s in SPECIALISTS.items()))

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
            from forsch.adk_bridge.a2a_delegation import serve_specialists

            coros.append(serve_specialists())
        await asyncio.gather(*coros)

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
