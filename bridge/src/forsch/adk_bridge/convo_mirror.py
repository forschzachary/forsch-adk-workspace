"""Mirror friend↔Huberto DM conversations into a Discord thread Zach can watch, and surface errors.

Huberto talks to friends in DMs inside the friends' own servers; Zach can't see those. This mirrors
each exchange into a per-friend thread in an OPS-owned channel (#companion-mirror in the HubertAI
guild) so Zach has a live window into every conversation — especially early on — and pushes errors
to an alert channel (#alerting) with an @-ping.

The friend-facing bot (Huberto) is NOT in the ops guild, so it can't post there; the OPS bot (which
is) does the posting. Huberto's handler reaches the ops client via the discord_bot registry
(get_bot) and hands it the exchange. Everything here is BEST-EFFORT: a mirror/alert failure is logged
and swallowed, never affecting the friend's actual turn.

Config (env; defaults are the verified HubertAI channels):
  MIRROR_FRIEND_CONVOS     '0' to disable entirely (default on)
  MIRROR_CHANNEL_ID        parent text channel for per-friend threads  (default #companion-mirror)
  MIRROR_ALERT_CHANNEL_ID  channel for error alerts                    (default #alerting)
  MIRROR_POSTER_BOT        registry name of the posting bot            (default 'screening_ops')
  SR_ADMIN_DISCORD_IDS     who to @-ping on an error (first id)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import discord

_LOG = logging.getLogger("adk_bridge.convo_mirror")
_THREAD_LOCK = asyncio.Lock()  # serialize thread lookup/creation so one friend can't spawn two threads

DEFAULT_MIRROR_CHANNEL = "1504879978678976523"   # #companion-mirror (HubertAI)
DEFAULT_ALERT_CHANNEL = "1494875996837384393"    # #alerting (HubertAI)
DEFAULT_POSTER_BOT = "screening_ops"
_MAX = 1800  # leave headroom under Discord's 2000-char limit for the prefix


def enabled() -> bool:
    return os.environ.get("MIRROR_FRIEND_CONVOS", "1").lower() not in ("0", "false", "no", "")


def poster_bot_name() -> str:
    return os.environ.get("MIRROR_POSTER_BOT", DEFAULT_POSTER_BOT)


def _channel_id(env: str, default: str) -> int | None:
    try:
        return int(os.environ.get(env, default))
    except (TypeError, ValueError):
        return None


def _admin_id() -> str | None:
    for s in os.environ.get("SR_ADMIN_DISCORD_IDS", "").split(","):
        if s.strip():
            return s.strip()
    return None


# ── per-friend thread cache (discord_id -> thread_id), so threads persist across restarts ──
def _map_path() -> Path:
    ws = Path(os.environ.get("FORSCH_ADK_WORKSPACE", str(Path.home() / "Dev" / "forsch-adk-workspace")))
    d = ws / "data" / "mirror"
    d.mkdir(parents=True, exist_ok=True)
    return d / "threads.json"


def _load_map() -> dict:
    p = _map_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_map(m: dict) -> None:
    p = _map_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, indent=2))
    tmp.replace(p)


async def _get_thread(poster: discord.Client, friend_id: str, friend_name: str) -> "discord.Thread | None":
    """A live (un-archived) mirror thread for this friend, reused from cache or freshly created.

    Serialized by _THREAD_LOCK so two near-simultaneous first messages from the same friend can't
    each create a thread (they'd clobber each other's map entry, leaving an orphan)."""
    async with _THREAD_LOCK:
        m = _load_map()
        rec = m.get(str(friend_id))
        if rec and rec.get("thread_id"):
            try:
                th = poster.get_channel(int(rec["thread_id"])) or await poster.fetch_channel(int(rec["thread_id"]))
                if isinstance(th, discord.Thread):
                    if th.archived:
                        try:
                            await th.edit(archived=False)
                        except discord.HTTPException:
                            pass
                    return th
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # cached thread is gone/inaccessible — fall through and recreate

        channel_id = _channel_id("MIRROR_CHANNEL_ID", DEFAULT_MIRROR_CHANNEL)
        if channel_id is None:
            return None
        parent = poster.get_channel(channel_id) or await poster.fetch_channel(channel_id)
        name = f"{friend_name} · {friend_id}"[:100]
        th = await parent.create_thread(name=name, type=discord.ChannelType.public_thread)
        m[str(friend_id)] = {"thread_id": str(th.id), "name": friend_name}
        _save_map(m)
        try:
            await th.send(f"🧵 conversation with **{friend_name}** (`{friend_id}`) — mirrored for observability.")
        except discord.HTTPException:
            pass
        return th


async def mirror_exchange(poster, friend_id: str, friend_name: str, inbound: str, outbound: str | None) -> None:
    """Post one friend↔Huberto exchange (📥 inbound, 📤 outbound) into the friend's mirror thread."""
    if not enabled() or poster is None:
        return
    name = friend_name or str(friend_id)
    try:
        th = await _get_thread(poster, str(friend_id), name)
        if th is None:
            return
        if inbound:
            await th.send(f"📥 **{name}:** {inbound}"[:_MAX])
        if outbound:
            await th.send(f"📤 **huberto:** {outbound}"[:_MAX])
    except Exception:
        _LOG.exception("convo_mirror: failed to mirror exchange for %s", friend_id)


async def surface_error(poster, friend_id: str, friend_name: str, summary: str, detail: str = "") -> None:
    """Push an error from a friend's conversation to #alerting (@-ping the admin) + the friend thread."""
    if poster is None:
        return
    name = friend_name or str(friend_id)
    ping = f"<@{_admin_id()}> " if _admin_id() else ""
    try:
        alert_id = _channel_id("MIRROR_ALERT_CHANNEL_ID", DEFAULT_ALERT_CHANNEL)
        if alert_id is not None:
            alert = poster.get_channel(alert_id) or await poster.fetch_channel(alert_id)
            await alert.send(f"{ping}⚠️ Huberto errored talking to **{name}** (`{friend_id}`): {summary}"[:_MAX])
            if detail:
                await alert.send(f"```\n{detail[-1500:]}\n```")
    except Exception:
        _LOG.exception("convo_mirror: failed to post alert for %s", friend_id)
    try:  # also leave a marker in the friend's own thread, for context
        th = await _get_thread(poster, str(friend_id), name)
        if th is not None:
            await th.send(f"⚠️ (error handling this turn: {summary})"[:_MAX])
    except Exception:
        pass
