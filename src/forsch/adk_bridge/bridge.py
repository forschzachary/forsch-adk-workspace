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


def _build_crm_assignee_map(config: dict) -> dict[str, str]:
    """Build CRM assignee -> agent map from config."""
    return {
        str(assignee).lower(): str(agent)
        for assignee, agent in config.get("crm", {}).get("assignees", {}).items()
    }


def _resolve_crm_agent(payload: dict, assignee_map: dict[str, str]) -> Optional[str]:
    """Resolve a CRM task payload to an agent name."""
    for key in ("assigned_to", "assignee", "owner"):
        value = payload.get(key)
        if value is None:
            continue
        agent_name = assignee_map.get(str(value).lower())
        if agent_name:
            return agent_name
    return None


def _format_crm_task_message(payload: dict) -> str:
    """Turn the incoming CRM task shape into a single ADK user message."""
    lines = ["You were assigned this CRM task from Frappe CRM."]
    fields = (
        ("task_id", "Task ID"),
        ("name", "Task ID"),
        ("title", "Title"),
        ("description", "Description"),
        ("assigned_to", "Assigned to"),
        ("reference_doctype", "Reference doctype"),
        ("reference_docname", "Reference docname"),
    )
    seen_labels: set[str] = set()
    for key, label in fields:
        if label in seen_labels:
            continue
        value = payload.get(key)
        if value in (None, ""):
            continue
        lines.append(f"{label}: {value}")
        seen_labels.add(label)
    return "\n".join(lines)


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
    """Accumulates ADK text for non-Discord callers such as CRM webhooks."""

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
        self._crm_assignee_map = _build_crm_assignee_map(config)
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

    async def handle_crm_task_assigned(self, payload: dict) -> dict:
        """Route an outbound CRM task assignment into the targeted ADK agent."""
        from forsch.adk_bridge.gateway.sources_crm import crm_to_canonical  # deferred: avoids import cycle
        canonical = crm_to_canonical(payload, self._crm_assignee_map)
        agent_name = gateway_resolve_agent(canonical, self._agents.keys(), {
            **self._config, "source_defaults": self._source_defaults,
        })
        if agent_name is None:
            return {"ok": False, "error": "unmapped_assignee"}

        agent = self._agents.get(agent_name)
        if agent is None:
            self._log.warning("CRM routed to unloaded agent %s", agent_name)
            return {"ok": False, "error": "agent_not_loaded", "agent": agent_name}

        task_id = payload.get("task_id") or payload.get("name") or "unknown"
        buffer = TextBuffer()
        try:
            await asyncio.wait_for(
                self._run_agent_text(
                    agent_name=agent_name,
                    agent=agent,
                    user_id="crm:frappe",
                    session_id=f"crm:{agent_name}:{task_id}",
                    text=_format_crm_task_message(payload),
                    buffer=buffer,
                ),
                timeout=self._run_timeout,
            )
        except asyncio.TimeoutError:
            self._log.warning("CRM run timed out for %s task %s", agent_name, task_id)
            return {"ok": False, "error": "run_timeout", "agent": agent_name, "task_id": task_id}
        return {"ok": True, "agent": agent_name, "task_id": task_id, "response": buffer.text}

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

        Delegates to run.stream_agent so the Discord/CRM path shares ONE run loop
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


async def _read_http_request(
    reader: asyncio.StreamReader,
    max_body_bytes: int = 65536,
    timeout_sec: float = 5.0,
) -> tuple[str, str, dict[str, str], bytes]:
    """Read one small HTTP request. This is intentionally webhook-only."""
    header_bytes = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout_sec)
    if len(header_bytes) > 8192:
        raise ValueError("request_headers_too_large")
    header_text = header_bytes.decode("iso-8859-1")
    request_line, *header_lines = header_text.split("\r\n")
    method, path, _version = request_line.split(" ", 2)
    headers: dict[str, str] = {}
    for line in header_lines:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.lower()] = value.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length > max_body_bytes:
        raise ValueError("request_body_too_large")
    body = await asyncio.wait_for(reader.readexactly(content_length), timeout_sec) if content_length else b""
    return method, path, headers, body


def _crm_request_authorized(headers: dict[str, str], crm_cfg: dict) -> bool:
    """Validate the shared-secret auth for CRM webhooks. Fails CLOSED: if no
    secret is configured (or its env var is unset) the request is rejected, so a
    misconfigured deploy can never expose an open task-injection endpoint that
    spends model budget and runs agent side-effects."""
    secret_env = crm_cfg.get("secret_env")
    if not secret_env:
        return False
    expected = os.environ.get(secret_env)
    if not expected:
        return False
    provided = headers.get("x-crm-bridge-secret") or headers.get("authorization", "").removeprefix(
        "Bearer "
    )
    return hmac.compare_digest(provided, expected)


def _decode_crm_payload(body: bytes) -> dict:
    """Decode and validate the CRM webhook payload."""
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    return payload


async def _write_http_response(
    writer: asyncio.StreamWriter,
    status: int,
    payload: dict,
) -> None:
    reason = {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        404: "Not Found",
        500: "Internal Server Error",
    }[status]
    body = json.dumps(payload).encode("utf-8")
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    writer.write(headers + body)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _handle_crm_http(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    client: ADKBridgeClient,
) -> None:
    log = logging.getLogger("adk_bridge")
    crm_cfg = client._config.get("crm", {})
    try:
        method, path, headers, body = await _read_http_request(
            reader,
            max_body_bytes=int(crm_cfg.get("max_body_bytes", 65536)),
            timeout_sec=float(crm_cfg.get("timeout_sec", 5.0)),
        )
        if method != "POST" or urlsplit(path).path != "/crm/task-assigned":
            await _write_http_response(writer, 404, {"ok": False, "error": "not_found"})
            return
        if not _crm_request_authorized(headers, crm_cfg):
            await _write_http_response(writer, 401, {"ok": False, "error": "unauthorized"})
            return
        payload = _decode_crm_payload(body)
        result = await client.handle_crm_task_assigned(payload)
        await _write_http_response(writer, 200 if result.get("ok") else 400, result)
    except ValueError as exc:
        await _write_http_response(writer, 400, {"ok": False, "error": str(exc)})
    except Exception:
        log.exception("CRM webhook failed")
        await _write_http_response(writer, 500, {"ok": False, "error": "internal_error"})


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

    # Session service + agent registry (shared with the Chainlit/CRM surfaces
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

    crm_cfg = config.get("crm", {})
    if crm_cfg.get("enabled", False):
        host = crm_cfg.get("host", "127.0.0.1")
        port = int(crm_cfg.get("port", 8765))
        server = await asyncio.start_server(
            lambda reader, writer: _handle_crm_http(reader, writer, client),
            host,
            port,
        )
        log.info("CRM webhook endpoint listening on http://%s:%s/crm/task-assigned", host, port)
        async with server:
            await asyncio.gather(client.start(token), server.serve_forever())
    else:
        await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
