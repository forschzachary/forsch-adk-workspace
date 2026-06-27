# Session Handoff — 2026-06-27

## What Shipped

### PADI Shelf (repeatable components)
- **Tool, Interface, Router lanes** wired up with graph-native shelf controls (label + spawn + library pills)
- **Consolidated** into shared `graphNodeLibrary()` and `inspectGraphNode()` — 3 lanes use identical logic
- **Uniform pill width** (90px) with canvas clip-path text truncation
- **Dynamic shelf spacing** — pills don't overlap regardless of name length
- **Click-to-inspect** for all graph-node lanes (tools, interfaces, routers)

### Live Particles
- **Custom green dots** travel along visible link segments (node edge → lane pin → node edge)
- **Node-ID matching** — matches by shared node ID, not exact edge key (handles collapsed intake nodes)
- **Collapsed intake mapping** — `chan:#team-stability` → `iface:discord` so particles appear on collapsed links
- **Rendered in `onRenderFramePost`** — draws on top of links, not behind them
- **Sleek 2px radius**

### Auth Cleanup
- **Dropped Frappe CSRF** — removed `csrfHeaders()`, `X-Frappe-CSRF-Token`, `window.frappe` checks
- **Graph secret is sole auth layer** — `X-Graph-Secret` header, `sessionStorage` persistence

### Hubert Factory Bot (Phase 1 — ADK)
- **Hubert ADK agent** scaffolded on live box — SOUL.md personality, orchestrator tools
- **Shared graph_tools module** — `get_graph_overview`, `manage_cluster`, `get_factory_status`
- **Agent·Logic specialist** scaffolded — 5 tools for agent config, models, evals, ADK reference
- **Specialist delegation** working — Hubert routes agent-dev questions to the specialist
- **Builder Cockpit integration** — `chat_with_hubert()` in serve.py now calls Hubert's ADK agent directly

## Live State

- **Live URL:** `graph.forschfrontiers.com`
- **Latest commit (live-agent-graph):** `4597234`
- **Latest commit (ADK):** `188dc05` (specialist API key fix)
- **Hetzner box:** `root@100.120.21.13`

## Verification Done

- `python3 -m pytest -q` — 4/4 passing (local)
- PADI shelf: all 4 lanes show library pills
- Live particles: green dots visible on active link segments
- Hubert chat: responds in character ("hello. I'm here, scarf on, watching the graph.")
- Specialist delegation: returns agent list and model info
- Factory status: "7 agents, 41 nodes, 29 links, nothing on fire"
- Model query via specialist: "shelby uses gpt-5.5"

## End-to-End Test Results

| Test | Result |
|------|--------|
| Hubert identity | "I'm Hubert - the factory orchestrator. Ginger tabby, scarf, unfortunate amount of responsibility." |
| Factory status | "7 agents: stability and ops are built; assistant, brand, build, social, and shelby are still building." |
| Specialist delegation | "shelby uses gpt-5.5, from the live agents.yaml entry" |
| Graph overview | "41 nodes, 29 links, active cluster is ops" |

## Files Changed

### `live-agent-graph/index.html`
- `graphNodeLibrary()` — shared library function for tool/interface/router lanes
- `inspectGraphNode()` — shared click-to-inspect handler
- `handlePadiControlClick()` — consolidated from 5 `if` blocks to 2
- `padiControlWidth()` — uniform 90px library pills
- `layoutPadiControlShelf()` — dynamic spacing (no more `PADI_LIBRARY_COL_STEP`)
- `drawPadiControlNode()` — canvas clip-path for text truncation
- `drawLiveParticles()` — custom particle rendering on visible link segments
- `padiLinkPath()` / `clipSegment()` / `pathLength()` / `pointAtDist()` — link path math
- `liveNodeIds` — replaces `liveEdgeKeys` for node-based matching
- Pulse function — maps collapsed intake nodes to live status
- `mutationHeaders()` — simplified, removed `csrfHeaders()`
- Removed: `csrfHeaders()`, `X-Frappe-CSRF-Token` references

### `live-agent-graph/serve.py`
- `chat_with_hubert()` — replaced `hermes` subprocess with ADK InMemoryRunner

### ADK workspace (live box)
- `agents/hubert/` — new ADK agent (agent.py, tools.py, __init__.py, pyproject.toml)
- `agents/agent_logic_specialist/` — new ADK agent with 5 tools
- `components/src/forsch/adk_components/tools/graph_tools.py` — shared graph tools
- `components/src/forsch/adk_components/tools/__init__.py` — registered new tools
- `agent_specs/agents.yaml` — added hubert + agent_logic_specialist entries
- `bridge/compose.yaml` — added PYTHONPATH entries for new agents

## Open Questions

1. **Hubert needs a web entrypoint** — currently only works via `/chat` endpoint, not as a standalone web agent
2. **Remaining specialists** — Tools·Data, Interfaces, Router specialists not yet built
3. **CLI** — `hubert chat` CLI not yet built
4. **SOUL.md loading** — currently loads from filesystem; might want to embed or cache
