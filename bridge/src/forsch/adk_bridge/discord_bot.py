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
import os
from dataclasses import dataclass, field

import discord

from forsch.adk_bridge.discord_identity import verify_identity
from forsch.adk_bridge.run import stream_agent

_LOG = logging.getLogger("adk_bridge.discord_bot")
_MAX_CHARS = 1900

# Registry of live bot clients by spec name, populated in run_bots(). Lets the background
# request_watcher (Phase 5) reach the running Huberto client to send an outbound DM, without a
# circular import or passing the client around. Empty until run_bots() starts.
_bots_by_name: dict[str, "ADKDiscordBot"] = {}


def get_bot(name: str) -> "ADKDiscordBot | None":
    """The running bot client for a spec name (e.g. 'huberto_cat'), or None if not started yet."""
    return _bots_by_name.get(name)


@dataclass
class BotSpec:
    """One Discord identity bound to one ADK agent."""

    name: str                                   # ADK app_name + log label
    token: str                                  # the bot token (from gitignored env)
    agent: object                               # the ADK agent this identity speaks for
    expected_bot_id: str | None = None          # identity guard; the bot refuses to boot otherwise
    channels: list[str] = field(default_factory=list)  # guild channel names it answers in (bare)
    dm: bool = True                             # answer direct messages
    mention_only: bool = False                  # in a guild channel, only answer when @-mentioned (DMs unaffected)
    loader: str = "🐾 *scratching the post…*"    # shown while the agent thinks, then edited to the reply
    context_provider: object = None             # optional callable: discord_user_id(str) -> a context line to inject
    mirror: bool = False                        # mirror this bot's convos + errors to the ops observability channel


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
        channel = message.channel
        in_channel = (channel.name.lower().lstrip("#") in self._channels) or (str(channel.id) in self._channels)
        if not in_channel:
            return False
        if self.spec.mention_only:
            # Only respond to messages that actually @-mention this bot — so ops doesn't barge into
            # every line of team chatter in its channel. DMs (handled above) always bypass this.
            return self.user in getattr(message, "mentions", [])
        return True

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return
        if not self._handles(message):
            return
        loader = None
        try:
            loader = await message.channel.send(self.spec.loader)
        except discord.Forbidden:
            # DM-403: the friend hasn't accepted the bot / shares no guild, so we can't even open the
            # channel. Don't drop the turn — record it so the true state is recoverable. We have no
            # reply payload yet here (the loader is the first send), so just note the blocked route;
            # the credential-bearing case is handled by _deliver below.
            _LOG.warning("%s cannot DM %s (Forbidden) — comms route waiting",
                         self.spec.name, getattr(message.author, "id", "?"))
            self._note_blocked_dm(str(message.author.id))
            # We still RECEIVED their message — mirror it so Zach sees it even when we can't reply.
            await self._mirror(message, None)
            return
        try:
            reply = await self._run(message)
            await self._deliver(message, loader, reply or "…")
            await self._mirror(message, reply)
        except Exception as exc:
            _LOG.exception("%s run failed", self.spec.name)
            await self._surface_error(message, exc)
            if loader is not None:
                try:
                    await loader.edit(content="(a hairball — something went wrong)")
                except Exception:
                    pass

    async def _deliver(self, message: discord.Message, loader, reply: str) -> None:
        """Edit the reply into the loader; on a DM-403 queue it so it can be delivered automatically
        once the friend opens the route (Phase 5 dispatch), and surface the true state, never a drop."""
        try:
            await loader.edit(content=reply)
            self._note_dm_delivered(str(message.author.id))
        except discord.Forbidden:
            _LOG.warning("%s DM to %s blocked mid-turn (Forbidden) — queuing pending DM",
                         self.spec.name, getattr(message.author, "id", "?"))
            self._queue_pending_dm(str(message.author.id), reply)

    # ── DM-403 bookkeeping — delegated to friend_memory; tolerant if it isn't wired ──
    def _queue_pending_dm(self, discord_id: str, content: str) -> None:
        try:
            from forsch.adk_bridge import friend_memory as fm
            fm.queue_pending_dm(discord_id, content)
        except Exception:
            _LOG.exception("%s could not queue pending DM for %s", self.spec.name, discord_id)

    def _note_blocked_dm(self, discord_id: str) -> None:
        try:
            from forsch.adk_bridge import friend_memory as fm
            fm.queue_pending_dm(discord_id, "")
        except Exception:
            pass

    def _note_dm_delivered(self, discord_id: str) -> None:
        try:
            from forsch.adk_bridge import friend_memory as fm
            if fm.get_pending_dm(discord_id) is not None:
                fm.mark_dm_delivered(discord_id)
        except Exception:
            pass

    # ── conversation mirror + error surfacing (best-effort; never breaks the friend's turn) ──
    def _mirror_poster(self):
        """The client that posts the mirror — the ops bot, which lives in the observability guild
        Huberto isn't in. None if mirroring is off, this bot doesn't mirror, or the poster isn't up."""
        if not self.spec.mirror:
            return None
        try:
            from forsch.adk_bridge import convo_mirror
            if not convo_mirror.enabled():
                return None
            return get_bot(convo_mirror.poster_bot_name())
        except Exception:
            return None

    def _friend_label(self, message: discord.Message) -> tuple[str, str]:
        fid = str(getattr(message.author, "id", "?"))
        fname = getattr(message.author, "display_name", None) or getattr(message.author, "name", None) or fid
        return fid, fname

    async def _mirror(self, message: discord.Message, reply: str | None) -> None:
        poster = self._mirror_poster()
        if poster is None:
            return
        try:
            from forsch.adk_bridge import convo_mirror
            fid, fname = self._friend_label(message)
            await convo_mirror.mirror_exchange(poster, fid, fname, message.content, reply)
        except Exception:
            _LOG.exception("%s convo mirror failed", self.spec.name)

    async def _surface_error(self, message: discord.Message, exc: Exception) -> None:
        poster = self._mirror_poster()
        if poster is None:
            return
        try:
            import traceback
            from forsch.adk_bridge import convo_mirror
            fid, fname = self._friend_label(message)
            summary = f"{type(exc).__name__}: {exc}"[:300]
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            await convo_mirror.surface_error(poster, fid, fname, summary, detail)
        except Exception:
            _LOG.exception("%s error surfacing failed", self.spec.name)

    async def _run(self, message: discord.Message) -> str:
        user_id = f"discord:{message.author.id}"
        session_id = f"{self.spec.name}:{message.channel.id}"
        text = message.content
        if self.spec.context_provider is not None:
            try:
                ctx = self.spec.context_provider(str(message.author.id))
            except Exception:
                _LOG.exception("%s context_provider failed", self.spec.name)
                ctx = ""
            if ctx:
                text = f"{ctx}\n\n{message.content}"
        chunks: list[str] = []
        async for token in stream_agent(self.spec.agent, self.spec.name, self._session_service,
                                        user_id, session_id, text):
            chunks.append(token)
        return "".join(chunks)[:_MAX_CHARS]

    async def send_dm(self, user_id: int | str, content: str) -> bool:
        """Send an outbound DM to a user, opening the DM channel if needed. Returns True on delivery.

        The dispatch point for proactive notifications (Phase 5) and the Phase-4 pending-DM queue. On
        a blocked route (the user shares no guild / hasn't accepted the bot → Forbidden) or an unknown
        user (NotFound) it returns False rather than raising, so the caller can keep the queued state
        and retry later instead of dropping it."""
        try:
            user = self.get_user(int(user_id)) or await self.fetch_user(int(user_id))
        except (discord.NotFound, discord.HTTPException, ValueError):
            _LOG.warning("%s send_dm: could not resolve user %s", self.spec.name, user_id)
            return False
        try:
            await user.send(content[:_MAX_CHARS])
            return True
        except discord.Forbidden:
            _LOG.warning("%s send_dm to %s blocked (Forbidden) — route still closed",
                         self.spec.name, user_id)
            return False
        except discord.HTTPException:
            _LOG.exception("%s send_dm to %s failed", self.spec.name, user_id)
            return False


def _intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True   # privileged — enable in the Discord dev portal
    intents.dm_messages = True
    return intents


async def run_bots(specs: list[BotSpec], session_service) -> None:
    """Verify each identity (fail-closed), then run all bot clients concurrently."""
    # Phase 1 — verify EVERY identity before we construct, register, or start any
    # client. Interleaving the two (the old code) meant a failure on a later spec
    # left earlier bots in the registry with un-awaited start() coroutines.
    for spec in specs:
        result = verify_identity(spec.token, spec.expected_bot_id)
        if not result.ok:
            raise SystemExit(
                f"identity guard failed for {spec.name}: {result.reason} (actual={result.actual_id})"
            )
        _LOG.info("%s identity ok — bot id %s", spec.name, result.actual_id)

    # Phase 2 — construct, register, and start every verified client together.
    tasks = []
    for spec in specs:
        client = ADKDiscordBot(spec, session_service, intents=_intents())
        _bots_by_name[spec.name] = client  # registry, so the watcher can reach a live client
        tasks.append(asyncio.ensure_future(client.start(spec.token)))
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        # One client's start() failed (or we're shutting down): cancel the siblings
        # so we don't leave half-connected bots orphaned in the event loop, then propagate.
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
