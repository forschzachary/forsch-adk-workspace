"""Run the ScreeningRoom Discord bots — the native ADK Discord bot component.

Loads bot tokens + gateway creds from the gitignored ``.adk-local.env``, builds each persona
agent and a persistent SQLite session service, verifies each identity fail-closed, and serves
them concurrently. Person-facing cat runs on Huberto; the internal lead runs on companion-lead.

Run:  python -m forsch.adk_bridge.discord_main   (with FORSCH_ADK_WORKSPACE set, or from the workspace)

Env (gitignored .adk-local.env):
  LITELLM_BASE_URL, LITELLM_HERMES_KEY                 — gateway (cat agent)
  HUBERTO_DISCORD_BOT_TOKEN  (+ HUBERTO_EXPECTED_BOT_ID, default 1499544375204773969)
  COMPANION_LEAD_DISCORD_BOT_TOKEN (+ COMPANION_LEAD_EXPECTED_BOT_ID, default 1512599235910963371)
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

HUBERTO_DEFAULT_ID = "1499544375204773969"
COMPANION_LEAD_DEFAULT_ID = "1512599235910963371"


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

    specs = []
    cat_token = os.environ.get("HUBERTO_DISCORD_BOT_TOKEN")
    if cat_token:
        specs.append(BotSpec(
            name="huberto_cat", token=cat_token,
            expected_bot_id=os.environ.get("HUBERTO_EXPECTED_BOT_ID", HUBERTO_DEFAULT_ID),
            agent=make_cat_agent(), dm=True,
        ))
    lead_token = os.environ.get("COMPANION_LEAD_DISCORD_BOT_TOKEN")
    if lead_token:
        # internal lead: channel-only (no DMs). Its agent gets the ops/curator brains later;
        # for now it shares the cat agent so the identity + serving prove out.
        specs.append(BotSpec(
            name="companion_lead", token=lead_token,
            expected_bot_id=os.environ.get("COMPANION_LEAD_EXPECTED_BOT_ID", COMPANION_LEAD_DEFAULT_ID),
            agent=make_cat_agent(), dm=False, channels=["team-social"], loader="📋 *checking the board…*",
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

    from forsch.adk_bridge.discord_bot import run_bots

    db = ws / ".forsch" / "discord_sessions.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    session_service = SqliteSessionService(db_path=str(db))

    specs = build_specs()
    if not specs:
        raise SystemExit(
            "no bot tokens — set HUBERTO_DISCORD_BOT_TOKEN (+ optionally COMPANION_LEAD_DISCORD_BOT_TOKEN) "
            "in .adk-local.env"
        )
    log.info("starting %d Discord bot(s): %s", len(specs), ", ".join(s.name for s in specs))
    asyncio.run(run_bots(specs, session_service))


if __name__ == "__main__":
    main()
