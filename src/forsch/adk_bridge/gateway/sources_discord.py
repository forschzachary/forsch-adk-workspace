"""Discord source adapter: discord.Message -> CanonicalMessage (pure; no network)."""
from __future__ import annotations

from forsch.adk_bridge.gateway.message import CanonicalMessage


def discord_to_canonical(message, channel_map: dict[str, str], dm_fallback: str | None = None) -> CanonicalMessage:
    """Normalize a discord.Message, mirroring the bridge's original _resolve_agent:
    - DM (no guild)        -> dm_fallback agent
    - mapped guild channel -> channel_map[name]
    - UNMAPPED guild channel -> None (NO reply). dm_fallback applies ONLY to DMs, never to
      unmapped channels (the regression this fixes).
    Keying mirrors the bridge: sender=discord:<author id>, session_id=<agent|dm>:<channel id>."""
    is_dm = getattr(message, "guild", None) is None
    if is_dm:
        target = dm_fallback
    else:
        target = channel_map.get(message.channel.name.lower())
    prefix = target or "dm"
    return CanonicalMessage(
        source="discord",
        sender=f"discord:{message.author.id}",
        text=message.content,
        target=target,
        session_id=f"{prefix}:{message.channel.id}",
        raw=message,
    )
