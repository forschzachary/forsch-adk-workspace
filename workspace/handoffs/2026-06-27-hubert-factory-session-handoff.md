# Session Handoff — 2026-06-27

> **Snapshot timestamp:** 2026-06-27T18:00Z
> **Local mirror (adk-live-current) is stale.** SSH to `root@100.120.21.13` to inspect live state. Run `git log --oneline -10` in each repo to verify SHAs.

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

| Task | Commit | Description |
|------|--------|-------------|
| T6 scaffold Hubert | `1182306` | agents/hubert/ scaffold |
| T7 orchestrator tools | `9a0519d` (components), `f5e2551` (adk) | graph_tools.py + wiring |
| T8 Agent·Logic specialist | `cbe4ba5` | specialist scaffold with 5 tools |
| T9 delegation | `0a466de` | route_to_agent_logic_specialist |
| T10 /chat integration | `fbe6cf3` | serve.py InMemoryRunner |
| T10 fix PYTHONPATH | `4597234` | added specialist + components paths |
| T10 fix API key | `188dc05` | set LITELLM_HERMES_KEY before import |

- **Hubert ADK agent** scaffolded on Hetzner box (`root@100.120.21.13`) — SOUL.md personality, orchestrator tools
- **Shared graph_tools module** — `get_graph_overview`, `manage_cluster`, `get_factory_status`
- **Agent·Logic specialist** scaffolded — 5 tools for agent config, models, evals, ADK reference
- **Specialist delegation** working — Hubert routes agent-dev questions to the specialist
- **Builder Cockpit integration** — `chat_with_hubert()` in serve.py now calls Hubert's ADK agent directly

## Live State

- **Live URL:** `graph.forschfrontiers.com`
- **Latest commit (live-agent-graph):** `4597234` (2026-06-27T18:00Z)
- **Latest commit (ADK):** `188dc05` (2026-06-27T18:00Z)
- **Hetzner box:** `root@100.120.21.13`

## Known Issues

1. **Cloudflare 1101 on live `/chat` endpoint** — testing via `curl https://graph.forschfrontiers.com/chat` returns error 1101. Local curl via SSH to `http://127.0.0.1:8898/chat` works fine. Likely a Cloudflare routing issue (the serve.py process may not be running on the port Cloudflare tunnels to). Test via SSH is the reliable path.

2. **Local mirror stale** — `/Users/zacharyforsch/Dev/adk-live-current/` has not been pulled from the live box. All `agent_specs/agents.yaml` entries, `serve.py` changes, and new agent directories exist only on the live box. `serve.py:chat_with_hubert` locally still shells out to `hermes`.

## Verification Done

Tested via SSH (`curl http://127.0.0.1:8898/chat`), not via browser.

| Test | Result |
|------|--------|
| pytest | 4/4 passing (local) |
| Hubert identity | "I'm Hubert - the factory orchestrator. Ginger tabby, scarf, unfortunate amount of responsibility." |
| Factory status | "7 agents: stability and ops are built; assistant, brand, build, social, and shelby are still building. 41 nodes, 29 links, active cluster is ops." |
| Specialist delegation (model query) | "shelby uses gpt-5.5, from the live agents.yaml entry under shelby.model. related code points at forsch.agent_shelby.agent.shelby_model." |
| Graph overview | "41 nodes, 29 links, active cluster is ops" |

**Browser E2E deferred** — the Builder Cockpit chat sidecar has not been tested end-to-end through the live URL in a browser session. This is blocked by the Cloudflare 1101 issue above. SSH-based curl tests cover the full stack (serve.py → Hubert agent → specialist delegation → response), so the backend is verified; only the browser → Cloudflare → serve.py routing path remains unverified.

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
- `chat_with_hubert()` — replaced `hermes` subprocess with ADK InMemoryRunner via components venv
- Added `Path` import for PYTHONPATH construction
- Added specialist + components PYTHONPATH entries to subprocess script

### ADK workspace (Hetzner box, not in local mirror)
- `agents/hubert/` — new ADK agent (agent.py, tools.py, __init__.py, pyproject.toml)
- `agents/agent_logic_specialist/` — new ADK agent with 5 tools
- `components/src/forsch/adk_components/tools/graph_tools.py` — shared graph tools
- `components/src/forsch/adk_components/tools/__init__.py` — registered new tools
- `agent_specs/agents.yaml` — added hubert + agent_logic_specialist entries (verified on live box; local mirror not yet pulled)
- `bridge/compose.yaml` — added PYTHONPATH entries for new agents

## Open Questions

1. **Hubert needs a web entrypoint** — currently only works via `/chat` endpoint, not as a standalone web agent
2. **Remaining specialists** — Tools·Data, Interfaces, Router specialists not yet built
3. **CLI** — `hubert chat` CLI not yet built
4. **SOUL.md loading** — currently loads from filesystem; might want to embed or cache
5. **Local mirror sync** — need to pull from live box to bring `adk-live-current` up to date
