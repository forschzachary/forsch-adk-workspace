# Hubert Factory Bot Design

Date: 2026-06-27
Status: Draft

## [S1] Problem

Hubert chat in the Builder Cockpit currently shells out to `hermes chat -q`, which isn't installed on the live server. The chat is broken end-to-end. Beyond just fixing chat, Hubert should be a proper factory operator — a custom ADK agent with domain-specific tools, orchestrating lane specialists.

## [S2] Architecture

Hubert is the orchestrator. He speaks to the user via the Builder Cockpit sidecar and a custom CLI. He routes work to lane specialists — one ADK agent per swim lane.

```
User (Browser / CLI)
       │
    Hubert (orchestrator)
       │
       ├── Router Specialist      (lane: router)
       ├── Interfaces Specialist   (lane: interfaces)
       ├── Agent·Logic Specialist  (lane: agent)
       └── Tools·Data Specialist   (lane: tools)
```

Each specialist is a standalone ADK agent with domain tools and knowledge. Hubert owns orchestration, personality, and factory-wide operations.

## [S3] Agent Definitions

### Hubert (orchestrator)

- **Model:** `openai/gpt-5.5` via LiteLLM proxy
- **Personality:** SOUL.md (existing — cat chief of staff, warm-but-dry, opinionated)
- **Tools:**
  - `get_graph_overview` — full graph state: nodes, links, clusters, health metrics
  - `route_to_specialist` — delegate a task to a lane specialist, return result
  - `manage_cluster` — create, switch, list clusters
  - `deploy_agent` — push agent code to live (git push + SSH pull)
  - `get_factory_status` — health check across all lanes and agents
- **Instruction:** Builder Cockpit context prefix + SOUL.md identity

### Agent·Logic Specialist

- **Model:** `openai/gpt-5.5` via LiteLLM proxy
- **Tools:**
  - `list_agents` — all agents with status, model, tools, gates
  - `get_agent_config` — read agent spec from agents.yaml
  - `update_agent_config` — modify agent spec (model, tools, instruction, safety level)
  - `generate_agent` — scaffold a new ADK agent from a description
  - `run_eval` — execute eval suite for an agent
  - `get_model_info` — available models, pricing, context windows, capabilities
  - `get_adk_reference` — ADK patterns, best practices, code examples
- **Knowledge:** ADK agent structure, eval patterns, model routing, safety levels

### Tools·Data Specialist

- **Model:** `openai/gpt-5.5` via LiteLLM proxy
- **Tools:**
  - `list_tools` — all tools with owner agents, usage stats, test coverage
  - `get_tool_source` — read tool implementation code
  - `create_tool` — scaffold a new ADK tool (Python function + tests)
  - `test_tool` — run tool against test fixtures
  - `wire_tool_to_agent` — add tool to an agent's toolset in agents.yaml
- **Knowledge:** Tool patterns, testing conventions, shared component library

### Interfaces Specialist

- **Model:** `openai/gpt-5.5` via LiteLLM proxy
- **Tools:**
  - `list_interfaces` — all interfaces (Discord, hosted chat, etc.) with status
  - `get_interface_config` — read interface/channel config
  - `configure_interface` — update interface settings
  - `test_interface` — send a test message through an interface
- **Knowledge:** Channel types, Discord bot setup, webhook config

### Router Specialist

- **Model:** `openai/gpt-5.5` via LiteLLM proxy
- **Tools:**
  - `list_routes` — all routing rules and contracts
  - `get_route_config` — read route definition
  - `update_route` — modify routing rules
  - `test_route` — trace a message through the router
- **Knowledge:** Contract checking, message flow, routing patterns

## [S4] CLI

Location: `/root/.hermes/workspace/adk/hubert-cli/`

Commands:
- `hubert chat` — interactive chat with Hubert (local dev, no browser needed)
- `hubert ask "<question>"` — one-shot question, print response
- `hubert spawn <agent_id>` — spawn a new agent via the factory
- `hubert wire <source> <target>` — wire two nodes together
- `hubert status` — factory health check
- `hubert deploy <agent_id>` — deploy an agent to live

Implementation: Python CLI using `click` or `argparse`, calls Hubert's ADK agent via the LiteLLM proxy or direct ADK runner.

## [S5] Integration with Builder Cockpit

The existing `/chat` endpoint in `serve.py` calls `chat_with_hubert()`. This function currently shells out to `hermes`. Replace it with:

1. Import and run Hubert's ADK agent directly (in-process, no subprocess)
2. Pass the user message + Builder Cockpit context
3. Return the response + session_id for continuity

The chat sidecar in `index.html` remains unchanged — it already sends messages to `/chat` and displays responses.

## [S6] File Structure

```
/root/.hermes/workspace/adk/
├── agents/
│   ├── hubert/                    # NEW — Hubert orchestrator
│   │   └── src/forsch/agent_hubert/
│   │       ├── __init__.py
│   │       ├── agent.py           # ADK Agent definition
│   │       ├── tools.py           # Hubert's tools
│   │       └── soul.py            # SOUL.md loaded at runtime
│   ├── agent_logic_specialist/    # NEW
│   │   └── src/forsch/agent_agent_logic_specialist/
│   │       ├── __init__.py
│   │       ├── agent.py
│   │       └── tools.py
│   ├── tools_specialist/          # NEW
│   ├── interfaces_specialist/     # NEW
│   └── router_specialist/         # NEW
├── agent_specs/
│   └── agents.yaml                # ADD hubert + 4 specialists
├── hubert-cli/                    # NEW — CLI package
│   ├── pyproject.toml
│   └── src/hubert_cli/
│       ├── __init__.py
│       ├── main.py                # CLI entry point
│       └── chat.py                # Chat session management
└── live-agent-graph/
    └── serve.py                   # MODIFY — chat_with_hubert() calls ADK directly
```

## [S7] Implementation Order

1. **Hubert agent** — ADK agent with SOUL.md personality + orchestrator tools
2. **Agent·Logic specialist** — most valuable first (agent dev focus)
3. **Tools·Data specialist** — second priority
4. **Builder Cockpit integration** — wire Hubert into `/chat` endpoint
5. **CLI** — `hubert chat` + factory commands
6. **Remaining specialists** — Interfaces, Router

## [S8] Verification

1. `hubert chat` locally → Hubert responds in character
2. Builder Cockpit chat → Hubert responds via `/chat` endpoint
3. `hubert spawn shelby` → creates agent via factory
4. `hubert status` → returns factory health
5. Hubert can delegate to Agent·Logic specialist for agent config questions
