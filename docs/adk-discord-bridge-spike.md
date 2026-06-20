# ADK Discord Bridge — Architecture Spike

**Date:** 2026-06-20
**Status:** plan, not built
**Author:** Hubert

## Goal

One Discord bot that routes messages to the right ADK agent, runs them through
ADK's native `InMemoryRunner`, and streams responses back. Five agents, one
bridge, one bot token. No custom agent loop — ADK owns the runtime.

## Architecture

```
Discord message
       │
       ▼
┌──────────────────────────────────────┐
│           Discord Bridge             │
│                                      │
│  ┌────────────┐    ┌──────────────┐  │
│  │ Channel →   │    │  ADK App     │  │
│  │ Agent map   │───▶│  (multi-     │  │
│  │             │    │   agent)     │  │
│  └────────────┘    └──────┬───────┘  │
│                           │          │
│                    ┌──────▼───────┐  │
│                    │ InMemory     │  │
│                    │ Runner       │  │
│                    │ .run_async() │  │
│                    └──────┬───────┘  │
│                           │          │
│                    ┌──────▼───────┐  │
│                    │ Session      │  │
│                    │ Service      │  │
│                    │ (SQLite)     │  │
│                    └──────────────┘  │
└──────────────────────────────────────┘
       │
       ▼
Discord response (streamed)
```

## Key ADK primitives we use (zero custom agent loop)

| Primitive | What it does | We use it for |
|-----------|-------------|---------------|
| `App(name, root_agent)` | Multi-agent container | One app per agent, or one app with sub-agents |
| `InMemoryRunner(app_name, agent, session_service)` | Full agent loop: model calls, tool execution, session state | Running every message |
| `runner.run_async(user_id, session_id, new_message)` | Async generator of `Event` objects | The core bridge call |
| `RunConfig(streaming_mode=StreamingMode.SSE)` | Tells runner to stream | Real-time Discord responses |
| `InMemorySessionService` or `SqliteSessionService` | Persists conversation state per user+agent | Memory across messages |
| `types.Content(parts=[Part(text=msg)])` | ADK's message format | Wrapping Discord text |

## Channel → Agent routing

Config file (`bridge_config.yaml`):

```yaml
agents:
  ops:
    agent_package: forsch.agent_ops.agent
    agent_attr: root_agent
    channels: ["#ops-war-room", "#infra"]
  social:
    agent_package: forsch.agent_social.agent
    agent_attr: agent
    channels: ["#social-media"]
  brand:
    agent_package: forsch.agent_brand.agent
    agent_attr: agent
    channels: ["#brand-central"]
  assistant:
    agent_package: forsch.agent_assistant.agent
    agent_attr: agent
    channels: ["#zachs-office"]
  build:
    agent_package: forsch.agent_build.agent
    agent_attr: agent
    channels: ["#build-squad"]
  # DM fallback — any DM goes to assistant
  dm_fallback: assistant
```

Bridge loads this at startup, imports each agent, creates one `InMemoryRunner`
per agent, and routes by channel name.

## Session model

Each (user_id, agent_name) pair gets its own ADK session. The runner handles
session creation, history, and tool state automatically. We use SQLite session
service so conversations survive bridge restarts:

```python
from google.adk.sessions import SqliteSessionService

session_service = SqliteSessionService(db_path="data/adk_sessions.db")
runner = InMemoryRunner(
    app_name="ops",
    agent=ops_agent,
    session_service=session_service,
)
```

## Message flow (per inbound Discord message)

```
1. Discord on_message(guild, channel, author, content)
2. Look up agent by channel name → config
3. If DM: use dm_fallback agent
4. Build ADK Content:
   content = Content(parts=[Part.from_text(text=message)])
5. Call runner.run_async(
     user_id=f"discord:{author.id}",
     session_id=f"{channel.id}",  # one session per channel
     new_message=content,
     run_config=RunConfig(streaming_mode=StreamingMode.SSE),
   )
6. Iterate async events:
   - Event.content.parts → text chunks → stream to Discord
   - Event.actions → tool calls (log, don't surface raw)
   - Event.is_final() → done, send any remaining text
7. Discord rate-limit: batch text chunks, send every ~500ms or on sentence break
```

## Streaming to Discord

ADK's SSE events carry partial text in `event.content.parts`. The bridge
accumulates text deltas and sends to Discord in batches:

```python
buffer = ""
async for event in runner.run_async(...):
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.text:
                buffer += part.text
    # Flush on sentence break or 500ms timer
    if buffer and (buffer.endswith((".", "!", "?", "\n")) or timer_expired):
        await channel.send(buffer)
        buffer = ""
```

## Tool execution visibility

When an agent calls a tool (CRM health check, lead list, etc.), ADK emits
events with `event.actions`. The bridge can optionally surface a brief status:

```
🔧 checking CRM health...
```

But raw tool output stays internal. Only the agent's final text response
reaches Discord.

## Deployment

Runs as a long-lived Python process on the cloud box, alongside Hermes and
LiteLLM. Managed by s6 (same supervision system as Hermes gateway).

```
/opt/data/services/adk-bridge/
├── bridge.py              # main service
├── bridge_config.yaml     # channel → agent map
├── data/
│   └── adk_sessions.db    # SQLite session store
└── run                    # s6 run script
```

Discord bot token comes from the existing sops+age secret bundle (same
`DISCORD_BOT_TOKEN` Hermes uses, or a separate `ADK_DISCORD_BOT_TOKEN` if we
want isolation).

## What we don't build

- **No custom agent loop.** ADK's `InMemoryRunner` handles model calls, tool
  dispatch, session history, and event streaming. We just feed it messages.
- **No per-agent Discord bots.** One bot, one token, channel routing.
- **No message queue or job system.** ADK sessions are synchronous per message.
  If two users message the same agent simultaneously, they get separate
  `run_async` calls with separate session IDs — naturally concurrent.
- **No Hermes dependency.** The bridge is standalone Python + ADK. Hermes
  continues as Zach's personal chief-of-staff on Discord; the ADK agents are
  the team leads.

## Build order

1. **Scaffold bridge repo** — `forsch-adk-bridge`, pyproject.toml, depends on
   all five agent packages + `discord.py`
2. **Channel router** — load config, import agents, create runners, route by
   channel name
3. **Session wiring** — SQLite session service, one session per (user, agent)
4. **Streaming adapter** — `run_async` → text buffer → Discord send
5. **s6 service** — run script, log to `/opt/data/logs/adk-bridge.log`
6. **Smoke test** — DM the bot, get assistant agent response with tools

## Open questions

- **One App with sub-agents vs. one App per agent?** ADK's `App` can hold a
  root agent that delegates to sub-agents. But our agents are independent
  team leads — they don't delegate to each other. One `InMemoryRunner` per
  agent (each with its own `App`) is simpler and matches the channel-routing
  model. Revisit if we need cross-agent handoffs.
- **Shared Discord bot token or separate?** Hermes already uses
  `DISCORD_BOT_TOKEN`. A second bot token means a second Discord application.
  Simpler: same token, different command prefix or channel set. But Hermes
  listens to all channels — we'd need to exclude ADK channels from Hermes
  routing. Separate token is cleaner.
- **Authsome for agent tools?** Already done — `FrappeClient` and
  `AuthsomeHTTPClient` are in shared components. Agents import them. No bridge
  work needed.
