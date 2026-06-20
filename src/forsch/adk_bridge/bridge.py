"""ADK Discord Bridge — one bot, five agents, channel routing.

Routes Discord messages to the right ADK agent via Runner,
streams responses back. No custom agent loop — ADK owns the runtime.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import discord
import yaml
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner, RunConfig
from google.adk.sessions import DatabaseSessionService
from google.genai import types

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
        self._flush_interval = config.get("streaming", {}).get("flush_interval_sec", 0.5)
        self._max_chars = config.get("streaming", {}).get("max_message_chars", 1900)
        self._log = logging.getLogger("adk_bridge")

    async def on_ready(self) -> None:
        self._log.info("bridge online as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        # Ignore own messages and other bots
        if message.author == self.user or message.author.bot:
            return

        # Determine target agent
        agent_name = self._resolve_agent(message)
        if agent_name is None:
            return  # no agent for this channel — silent

        agent = self._agents.get(agent_name)
        if agent is None:
            self._log.warning("agent %s not loaded", agent_name)
            return

        # Build ADK content
        content = types.Content(
            parts=[types.Part.from_text(text=message.content)],
            role="user",
        )

        # Session IDs: one per (user, agent) pair
        user_id = f"discord:{message.author.id}"
        session_id = f"{agent_name}:{message.channel.id}"
        session = await self._session_service.get_session(
            app_name=agent_name,
            user_id=user_id,
            session_id=session_id,
        )
        if session is None:
            await self._session_service.create_session(
                app_name=agent_name,
                user_id=user_id,
                session_id=session_id,
            )

        # Build runner per message (lightweight — Runner is stateless,
        # session_service handles persistence)
        runner = Runner(
            agent=agent,
            app_name=agent_name,
            session_service=self._session_service,
            artifact_service=InMemoryArtifactService(),
            memory_service=InMemoryMemoryService(),
            auto_create_session=False,
        )

        StreamingMode = RunConfig.model_fields["streaming_mode"].annotation
        run_config = RunConfig(streaming_mode=StreamingMode.SSE)

        buffer = StreamBuffer(
            message.channel,
            flush_interval=self._flush_interval,
            max_chars=self._max_chars,
        )

        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
                run_config=run_config,
            ):
                # Extract text from event content
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            buffer.feed(part.text)

                # Flush on sentence break or timer
                if buffer.should_flush():
                    await buffer.flush()

                # Stop on final response
                if event.is_final_response():
                    await buffer.flush_final()
                    break

            # Safety net: flush anything left
            await buffer.flush_final()

        except Exception:
            self._log.exception("agent run failed for %s/%s", agent_name, user_id)
            await message.channel.send("(something went wrong — ops agent will see the log)")

    def _resolve_agent(self, message: discord.Message) -> Optional[str]:
        """Resolve which agent handles this message."""
        # DM → fallback
        if message.guild is None:
            return self._dm_fallback

        # Guild channel → channel map
        channel_name = message.channel.name.lower()
        return self._channel_map.get(channel_name)


# ── main entrypoint ────────────────────────────────────────────────────────

async def main(config_path: str = "bridge_config.yaml") -> None:
    """Start the bridge."""
    config = _load_config(config_path)

    # Logging
    log_cfg = config.get("logging", {})
    logging.basicConfig(
        level=getattr(logging, log_cfg.get("level", "INFO")),
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_cfg.get("file", "/opt/data/logs/adk-bridge.log")),
            logging.StreamHandler(sys.stderr),
        ],
    )
    log = logging.getLogger("adk_bridge")

    # Session service (aiosqlite required for async SQLite)
    session_db = config["session"]["db_path"]
    db_url = f"sqlite+aiosqlite:///{session_db}"
    session_service = DatabaseSessionService(db_url=db_url)

    # Import agents
    agents: dict[str, object] = {}
    for name, spec in config["agents"].items():
        if name == "dm_fallback":
            continue
        agents[name] = _import_agent(spec["agent_package"], spec["agent_attr"])
        log.info("loaded agent %s from %s.%s", name, spec["agent_package"], spec["agent_attr"])

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
