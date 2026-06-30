"""Single source of truth for the NATIVE ScreeningRoom bots.

These are the agents the Forsch Factory does NOT generate (huberto, screening_ops, curator). They
are defined ONCE here and read by BOTH:
  • the runtime — ``discord_main.build_specs`` filters this list by which tokens are set, and
  • the live graph — ``graph_manifest.native_graph`` derives the map's nodes/edges from it.

Because both read the same list, the running bots and the map cannot diverge: add a bot here and it
appears in both; delete it and it vanishes from both. The references to ``make_*_agent`` / ``*_toolset``
are light (the personas import google.adk/a2a only *inside* their functions), so importing this module
from the graph builder does NOT pull the Discord/ADK runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from forsch.adk_bridge.cat_persona import huberto_toolset, make_huberto_agent
from forsch.adk_bridge.curator_persona import curator_toolset, make_curator_agent
from forsch.adk_bridge.friend_memory import friend_context
from forsch.adk_bridge.ops_persona import make_ops_agent, ops_toolset


@dataclass(frozen=True)
class NativeBot:
    agent_id: str            # graph node id suffix: "huberto", "screening-ops", "curator"
    name: str                # agent + display name: "huberto", "screening_ops", "screening_curator"
    bot_name: str            # discord client name: "huberto_cat", "screening_ops", "screening_curator"
    persona_module: str      # the persona file (artifact), e.g. "cat_persona"
    make_agent: Callable     # the ADK agent factory
    toolset: Callable        # the agent's own tools (functions) — single source, light import
    bundle_key: str
    bundle_name: str
    bundle_desc: str
    token_env: str           # gates whether the bot actually launches
    expected_id_env: str
    expected_id_default: str
    dm: bool = False
    mention_only: bool = False
    channel_name: Optional[str] = None      # "#team-social", "#screening-tv"
    channel_env: Optional[str] = None        # "OPS_CHANNEL_ID"
    channel_default: Optional[str] = None    # the fallback channel id
    loader: Optional[str] = None
    context_provider: Optional[Callable] = None
    optional: bool = False
    a2a_specialist: Optional[str] = None     # the a2a_delegation SPECIALISTS key (this bot is delegated-TO)
    delegates: bool = False                  # this bot consults the A2A specialists (huberto does)


NATIVE_BOTS: list[NativeBot] = [
    NativeBot(
        agent_id="huberto", name="huberto", bot_name="huberto_cat",
        persona_module="cat_persona", make_agent=make_huberto_agent, toolset=huberto_toolset,
        bundle_key="sr1_concierge", bundle_name="sr1_concierge",
        bundle_desc="huberto's friend-facing toolkit: what's-on, library, requests, onboarding, access, knowledge.",
        token_env="HUBERTO_DISCORD_BOT_TOKEN",
        expected_id_env="HUBERTO_EXPECTED_BOT_ID", expected_id_default="1499544375204773969",
        dm=True, channel_name="DM", context_provider=friend_context, delegates=True,
    ),
    NativeBot(
        agent_id="screening-ops", name="screening_ops", bot_name="screening_ops",
        persona_module="ops_persona", make_agent=make_ops_agent, toolset=ops_toolset,
        bundle_key="screening_media_pipeline", bundle_name="screening_media_pipeline",
        bundle_desc="the media pipeline: account audit, queue health/counts, retries, title diagnosis, storage.",
        token_env="COMPANION_LEAD_DISCORD_BOT_TOKEN",
        expected_id_env="COMPANION_LEAD_EXPECTED_BOT_ID", expected_id_default="1512599235910963371",
        mention_only=True, channel_name="#team-social",
        channel_env="OPS_CHANNEL_ID", channel_default="1511377396668825662",
        loader="\U0001F4CB *checking the board…*", a2a_specialist="screening_ops",
    ),
    NativeBot(
        agent_id="curator", name="screening_curator", bot_name="screening_curator",
        persona_module="curator_persona", make_agent=make_curator_agent, toolset=curator_toolset,
        bundle_key="sr1_curation", bundle_name="sr1_curation",
        bundle_desc="SR-1 programming: now/guide/schedule/reprogram, bumps, playlists, events, suggest-to-main.",
        token_env="CURATOR_DISCORD_BOT_TOKEN",
        expected_id_env="CURATOR_EXPECTED_BOT_ID", expected_id_default="",
        channel_name="#screening-tv", channel_env="TV_CHANNEL_ID", channel_default="1511377396668825662",
        loader="\U0001F3AC *curating the lineup…*", optional=True, a2a_specialist="screening_curator",
    ),
]
