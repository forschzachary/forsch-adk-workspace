"""A first-class, native ADK Discord bot — one bot identity per ADK agent.

A reusable factory component: give it a bot token + the agent it speaks for, and it runs a
discord.py client that (a) verifies its identity fail-closed at boot, (b) answers DMs + its mapped
guild channels, and (c) streams the agent's reply through ADK's Runner (the same
``run.stream_agent`` the rest of the bridge uses) behind a themeable loader message.

``run_bots()`` runs several identities concurrently — the multi-bot model the single
``ADKBridgeClient`` lacked (e.g. a person-facing cat on Huberto + an internal lead on
companion-lead). The bot appears unified: it never says "asking ops", it just shows its loader
("🐾 scratching the post…") then edits in the reply.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import discord

from forsch.adk_bridge.discord_identity import verify_identity
from forsch.adk_bridge.run import stream_agent

_LOG = logging.getLogger("adk_bridge.discord_bot")
_MAX_CHARS = 1900


@dataclass
class BotSpec:
    """One Discord identity bound to one ADK agent."""

    name: str                                   # ADK app_name + log label
    token: str                                  # the bot token (from gitignored env)
    agent: object                               # the ADK agent this identity speaks for
    expected_bot_id: str | None = None          # identity guard; the bot refuses to boot otherwise
    channels: list[str] = field(default_factory=list)  # guild channel names it answers in (bare)
    dm: bool = True                             # answer direct messages
    loader: str = "🐾 *scratching the post…*"    # shown while the agent thinks, then edited to the reply


class ADKDiscordBot(discord.Client):
    """A discord.py client that serves exactly one ADK agent (DMs + its channels)."""

    def __init__(self, spec: BotSpec, session_service, **kwargs):
        super().__init__(**kwargs)
        self.spec = spec
        self._session_service = session_service
        self._channels = {c.lower().lstrip("#") for c in spec.channels}

    async def on_ready(self) -> None:
        _LOG.info("%s online as %s (id %s)", self.spec.name, self.user, getattr(self.user, "id", "?"))

    def _handles(self, message: discord.Message) -> bool:
        if message.guild is None:
            return self.spec.dm
        return message.channel.name.lower().lstrip("#") in self._channels

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return
        if not self._handles(message):
            return
        loader = None
        try:
            loader = await message.channel.send(self.spec.loader)
            reply = await self._run(message)
            await loader.edit(content=reply or "…")
        except Exception:
            _LOG.exception("%s run failed", self.spec.name)
            if loader is not None:
                try:
                    await loader.edit(content="(a hairball — something went wrong)")
                except Exception:
                    pass

    async def _run(self, message: discord.Message) -> str:
        user_id = f"discord:{message.author.id}"
        session_id = f"{self.spec.name}:{message.channel.id}"
        chunks: list[str] = []
        async for token in stream_agent(self.spec.agent, self.spec.name, self._session_service,
                                        user_id, session_id, message.content):
            chunks.append(token)
        return "".join(chunks)[:_MAX_CHARS]


def _intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True   # privileged — enable in the Discord dev portal
    intents.dm_messages = True
    return intents


async def run_bots(specs: list[BotSpec], session_service) -> None:
    """Verify each identity (fail-closed), then run all bot clients concurrently."""
    starts = []
    for spec in specs:
        result = verify_identity(spec.token, spec.expected_bot_id)
        if not result.ok:
            raise SystemExit(
                f"identity guard failed for {spec.name}: {result.reason} (actual={result.actual_id})"
            )
        _LOG.info("%s identity ok — bot id %s", spec.name, result.actual_id)
        client = ADKDiscordBot(spec, session_service, intents=_intents())
        starts.append(client.start(spec.token))
    await asyncio.gather(*starts)
