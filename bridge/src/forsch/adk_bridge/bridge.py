"""ADK Discord Bridge — one bot, five agents, channel routing.

Routes Discord messages to the right ADK agent via Runner,
streams responses back. No custom agent loop — ADK owns the runtime.
"""

from __future__ import annotations

import asyncio
import hmac
import importlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import discord
import yaml
from google.adk.sessions import DatabaseSessionService

from forsch.adk_bridge.gateway.router import resolve_agent as gateway_resolve_agent, build_source_defaults
from forsch.adk_bridge.gateway.sources_discord import discord_to_canonical
from forsch.adk_bridge.run import stream_agent


# ── config loading ──────────────────────────────────────────────────────────

def _load_config(path: str | Path = "bridge_config.yaml") -> dict:
    """Load bridge config from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def _import_agent(package: str, attr: str):
    """Import an agent from a package path like 'forsch.agent_ops.agent'."""
    mod = importlib.import_module(package)
    return getattr(mod, attr)


# ── channel routing ────────────────────────────────────────────────────────

def _build_channel_map(config: dict) -> dict[str, str]:
    """Build channel_name → agent_name map from config."""
    channel_map: dict[str, str] = {}
    for name, spec in config["agents"].items():
        if name == "dm_fallback":
            continue
        for channel in spec.get("channels", []):
            channel_map[channel.lower().lstrip("#")] = name
    return channel_map


# ── streaming adapter ──────────────────────────────────────────────────────

class StreamBuffer:
    """Accumulates text deltas from ADK events and flushes to Discord."""

    def __init__(self, channel, flush_interval: float = 0.5, max_chars: int = 1900):
        self._channel = channel
        self._flush_interval = flush_interval
        self._max_chars = max_chars
        self._buffer: str = ""
        self._last_flush: float = 0.0
        self._sent_chunks: list[str] = []

    def feed(self, text: str) -> None:
        """Add text delta to buffer."""
        self._buffer += text

    def should_flush(self) -> bool:
        """True if buffer should be sent now."""
        if not self._buffer:
            return False
        # Sentence break
        if self._buffer.rstrip().endswith((".", "!", "?", "\n")):
            return True
        # Time-based
        if time.monotonic() - self._last_flush >= self._flush_interval:
            return True
        # Size-based
        if len(self._buffer) >= self._max_chars:
            return True
        return False

    async def flush(self) -> None:
        """Send buffer to Discord if non-empty."""
        if not self._buffer.strip():
            self._buffer = ""
            return
        chunk = self._buffer[: self._max_chars].strip()
        self._buffer = self._buffer[self._max_chars :]
        await self._channel.send(chunk)
        self._sent_chunks.append(chunk)
        self._last_flush = time.monotonic()

    async def flush_final(self) -> None:
        """Send any remaining buffer content."""
        while self._buffer.strip():
            await self.flush()


class TextBuffer:
    """Accumulates ADK text for non-Discord callers."""

    def __init__(self) -> None:
        self.text = ""

    def feed(self, text: str) -> None:
        self.text += text

    def should_flush(self) -> bool:
        return False

    async def flush(self) -> None:
        return None

    async def flush_final(self) -> None:
        return None


# ── Discord client ─────────────────────────────────────────────────────────

class ADKBridgeClient(discord.Client):
    """Discord client that routes messages to ADK agents."""

    def __init__(
        self,
        config: dict,
        agents: dict[str, object],
        channel_map: dict[str, str],
        session_service: DatabaseSessionService,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._config = config
        self._agents = agents
        self._channel_map = channel_map
        self._session_service = session_service
        self._dm_fallback = config["agents"]["dm_fallback"]
        self._source_defaults = build_source_defaults(config)
        self._flush_interval = config.get("streaming", {}).get("flush_interval_sec", 0.5)
        self._max_chars = config.get("streaming", {}).get("max_message_chars", 1900)
        self._run_timeout = float(config.get("run_timeout_sec", 180))
        self._log = logging.getLogger("adk_bridge")

    async def on_ready(self) -> None:
        self._log.info("bridge online as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return

        canonical = discord_to_canonical(message, self._channel_map, self._dm_fallback)
        agent_name = gateway_resolve_agent(canonical, self._agents.keys(), {
            **self._config, "source_defaults": self._source_defaults,
        })
        if agent_name is None:
            return  # no agent for this channel — silent (unchanged behavior)

        agent = self._agents.get(agent_name)
        if agent is None:
            self._log.warning("agent %s not loaded", agent_name)
            return

        buffer = StreamBuffer(
            message.channel,
            flush_interval=self._flush_interval,
            max_chars=self._max_chars,
        )
        try:
            await asyncio.wait_for(
                self._run_agent_text(
                    agent_name=agent_name,
                    agent=agent,
                    user_id=canonical.sender,
                    session_id=f"{agent_name}:{message.channel.id}",
                    text=message.content,
                    buffer=buffer,
                ),
                timeout=self._run_timeout,
            )
        except Exception:
            self._log.exception("agent run failed for %s", agent_name)
            await message.channel.send("(something went wrong — ops agent will see the log)")


    async def _run_agent_text(
        self,
        agent_name: str,
        agent: object,
        user_id: str,
        session_id: str,
        text: str,
        buffer: StreamBuffer | TextBuffer,
    ) -> None:
        """Run one text message through ADK and stream into the supplied buffer.

        Delegates to run.stream_agent so the Discord path shares ONE run loop
        with the Chainlit surface — including thought-part filtering and the
        final-aggregate dedup (a streaming run re-sends the full text in the final
        event; stream_agent skips it, so replies are never doubled)."""
        async for chunk in stream_agent(
            agent, agent_name, self._session_service, user_id, session_id, text
        ):
            buffer.feed(chunk)
            if buffer.should_flush():
                await buffer.flush()
        await buffer.flush_final()


# ── main entrypoint ────────────────────────────────────────────────────────

async def main(config_path: str = "bridge_config.yaml") -> None:
    """Start the bridge."""
    config = _load_config(config_path)

    # Logging — stderr always (docker logs); a file handler only if its dir is
    # writable (a container without that path just uses stdout/stderr).
    log_cfg = config.get("logging", {})
    handlers = [logging.StreamHandler(sys.stderr)]
    log_file = log_cfg.get("file")
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
            handlers.insert(0, logging.FileHandler(log_file))
        except OSError:
            pass
    logging.basicConfig(
        level=getattr(logging, log_cfg.get("level", "INFO")),
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=handlers,
    )
    log = logging.getLogger("adk_bridge")

    # Session service + agent registry (shared with the Chainlit surface
    # via runtime.get_runtime() so all surfaces load agents the same way once).
    from forsch.adk_bridge.runtime import get_runtime

    runtime = get_runtime()
    session_service = runtime.session_service
    agents: dict[str, object] = runtime.agents
    for name in agents:
        log.info("loaded agent %s", name)

    # Channel map
    channel_map = _build_channel_map(config)
    log.info("channel map: %d channels → %d agents", len(channel_map), len(agents))

    # Discord token
    token_env = config["discord"]["token_env"]
    token = os.environ.get(token_env)
    if not token:
        log.error("missing token: set %s", token_env)
        sys.exit(1)

    # Build and run client
    intents = discord.Intents.default()
    intents.message_content = True

    client = ADKBridgeClient(
        config=config,
        agents=agents,
        channel_map=channel_map,
        session_service=session_service,
        intents=intents,
    )
    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
