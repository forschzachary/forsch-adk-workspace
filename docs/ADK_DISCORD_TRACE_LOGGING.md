# ADK Discord Trace Logging

## Purpose

Send ADK runtime trace events to a private Discord channel so VPS debugging is visible without polluting user-facing agent threads.

This is for operational trace events, not user chat:

- inbound message accepted
- route selected
- agent run started/completed
- model/tool call started/completed
- tool error or policy block
- bridge delivery error

## Recommendation

Use a Discord webhook for trace delivery, but do not put webhook calls directly inside agent business logic.

Instead:

1. Add a shared tracing utility in `forsch-adk-components`.
2. Attach ADK lifecycle callbacks to generated agents.
3. Let tools emit trace events through the shared utility when useful.
4. Keep the Discord bridge user-facing and clean.
5. Rate-limit and redact traces before sending them to Discord.

## Why Not Put Webhook Calls Everywhere

The raw pattern works, but it will rot fast:

- synchronous HTTP inside callbacks can slow agent turns
- tool functions become noisy and hard to test
- webhook secrets spread across agents
- Discord rate limits can break runtime flow
- prompts/tool args may leak private data into logs

So the right shape is: agent/tool code emits structured trace events; one shared sink decides whether and how to send them.

## Proposed Files

```text
components/src/forsch/adk_components/tracing/
├── __init__.py
├── discord.py          # Discord webhook sink
├── events.py           # TraceEvent model + redaction
└── callbacks.py        # ADK callback factories
```

Optional per-agent config later:

```yaml
tracing:
  enabled: true
  sink: discord_webhook
  webhook_env: DISCORD_ADK_TRACE_WEBHOOK
  redact: true
  sample_tool_successes: true
```

## Shared Event Model

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


TraceKind = Literal[
    "message.received",
    "route.selected",
    "agent.started",
    "agent.completed",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "bridge.failed",
]


class TraceEvent(BaseModel):
    kind: TraceKind
    agent: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    message: str
    fields: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

## Discord Sink

Use an async sink with timeout and fail-closed behavior. Tracing must never break an agent run.

```python
from __future__ import annotations

import os
import re

import httpx

from .events import TraceEvent

_SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.I),
    re.compile(r"(api[_-]?key|token|secret|password)=([^\s]+)", re.I),
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


async def send_discord_trace(event: TraceEvent) -> None:
    webhook = os.environ.get("DISCORD_ADK_TRACE_WEBHOOK")
    if not webhook:
        return

    content = format_event(event)
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(webhook, json={"content": content})
        except Exception:
            return


def format_event(event: TraceEvent) -> str:
    fields = " ".join(f"`{k}={redact(str(v))}`" for k, v in event.fields.items())
    head = f"**ADK trace** `{event.kind}`"
    agent = f" `{event.agent}`" if event.agent else ""
    return f"{head}{agent}\n{redact(event.message)}\n{fields}"[:1900]
```

For heavier traffic, replace direct sends with an `asyncio.Queue` worker so callback paths only enqueue events.

## ADK Callback Pattern

ADK Python documents callback parameter names strictly. Do not rename them to `ctx` or similar.

Use documented callback parameters:

- `before_agent_callback(callback_context)`
- `after_agent_callback(callback_context)`
- `before_tool_callback(tool, args, tool_context)`
- `after_tool_callback(tool, args, tool_context, tool_response)`

Example factory:

```python
from __future__ import annotations

import asyncio

from .discord import send_discord_trace
from .events import TraceEvent


def fire_and_forget(event: TraceEvent) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(send_discord_trace(event))


def before_agent_callback(callback_context):
    agent_name = getattr(getattr(callback_context, "agent", None), "name", None)
    fire_and_forget(TraceEvent(
        kind="agent.started",
        agent=agent_name,
        message=f"agent started: {agent_name}",
    ))
    return None


def after_agent_callback(callback_context):
    agent_name = getattr(getattr(callback_context, "agent", None), "name", None)
    fire_and_forget(TraceEvent(
        kind="agent.completed",
        agent=agent_name,
        message=f"agent completed: {agent_name}",
    ))
    return None


def before_tool_callback(tool, args, tool_context):
    fire_and_forget(TraceEvent(
        kind="tool.started",
        agent=getattr(tool_context, "agent_name", None),
        message=f"tool started: {getattr(tool, 'name', repr(tool))}",
        fields={"args": args},
    ))
    return None


def after_tool_callback(tool, args, tool_context, tool_response):
    fire_and_forget(TraceEvent(
        kind="tool.completed",
        agent=getattr(tool_context, "agent_name", None),
        message=f"tool completed: {getattr(tool, 'name', repr(tool))}",
    ))
    return None
```

Generated agents can then include callback references when enabled by spec.

## Agent Factory Integration

Add this to `agent_specs/agents.yaml` defaults:

```yaml
defaults:
  tracing:
    enabled: true
    webhook_env: DISCORD_ADK_TRACE_WEBHOOK
    include_tool_args: false
    include_tool_successes: true
```

Per agent:

```yaml
agents:
  ops:
    tracing:
      enabled: true
      include_tool_args: false
```

Generated `agent.py` should import callbacks only when tracing is enabled:

```python
from forsch.adk_components.tracing.callbacks import (
    after_agent_callback,
    after_tool_callback,
    before_agent_callback,
    before_tool_callback,
)

root_agent = Agent(
    name="ops_agent",
    model=ops_model,
    description="Infrastructure and operations lead for Forsch.",
    instruction=instruction,
    tools=[get_crm_health_snapshot],
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)
```

Before committing this exact constructor shape, verify against the installed ADK version because callback attachment can differ across agent classes.

## Bridge Integration

The bridge should trace I/O boundaries too:

- route resolved: channel -> agent
- ADK run started
- final response sent
- exception logged

Do this in bridge code, not in agent code, because bridge events are transport-level.

Example event:

```python
TraceEvent(
    kind="route.selected",
    agent=agent_name,
    user_id=user_id,
    session_id=session_id,
    message=f"Discord channel routed to {agent_name}",
    fields={"channel": message.channel.id},
)
```

## Security Rules

- Store webhook URL only in env: `DISCORD_ADK_TRACE_WEBHOOK`.
- Do not commit webhook URLs.
- Do not send full prompts by default.
- Do not send raw tool responses by default.
- Redact bearer tokens, API keys, passwords, cookies, and OAuth codes.
- Keep the trace channel private.
- Add rate limiting before high-volume tool traces.

## Operational Setup

1. Create a private Discord channel, e.g. `#agent-traces`.
2. Create a Discord webhook for that channel.
3. Set env var for the ADK bridge/service:

```bash
export DISCORD_ADK_TRACE_WEBHOOK='https://discord.com/api/webhooks/...'
```

4. Restart the ADK bridge/service.
5. Trigger one agent turn.
6. Confirm trace events arrive in the channel.

## Current Design Change

Add tracing as a shared component and generated agent feature. Do not hand-wire webhook posts into each tool or each agent.

The factory should own whether an agent has tracing enabled; components should own how tracing works; bridge should own transport-level trace events.
