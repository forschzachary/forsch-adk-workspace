# Live Agent Graph — canonical control surface for the ADK engine

> **Production engine** for AI consulting projects. Force-graph UI + chat + specialist delegation + Cloudflare Access auth + full MiMo CLI backend. Not a spike.

**Status:** D1 ✅ D2 ✅ D3 ✅ | D4 ✅ D5 ✅ | MiMo swap ✅ | Cloudflare Access ✅  
**Project ID:** live-agent-graph  
**Started:** 2026-06-23  
**Repo:** https://github.com/forschzachary/live-agent-graph (private)

### Production paths

| Environment | Path |
|---|---|
| Box (canonical) | `/root/.hermes/workspace/adk/live-agent-graph` |
| Mac (dev mirror) | `~/Dev/live-agent-graph` |

### Live services (box)

| Service | Port | Process | Auth |
|---|---|---|---|
| `serve.py` (graph + MiMo chat) | 8888 | systemd `live-agent-graph.service` | Cloudflare Access JWT |
| `adk api_server` (specialist REST) | 8001 | systemd `adk-api.service` | localhost only |
| LiteLLM (model gateway) | 4000 | systemd | localhost only |
| cloudflared (edge tunnel) | — | docker | — |

### URLs

| URL | Purpose |
|---|---|
| https://graph.forschfrontiers.com | Operator UI (Cloudflare Access → Google OAuth → serve.py) |
| https://graph.forschfrontiers.com/chat/ | ADK bridge chat (Gradio iframe, proxied) |

## D1: Node Schema + Manifest Format ✅

### Node schema (canonical)

Every node, regardless of type:

```yaml
node:
  id: string            # unique, e.g. "agent:stability"
  type: string          # intake | router | agent | tool | ui | database | capability
  model: string         # LLM model code (embedded in agent nodes, not a separate node)
  state: string         # blank | building | built | live | error
  artifact: string      # file/dir this node OWNS on disk (truth pointer)
  contract:
    accepts: [string]   # what this node takes in (type-aware)
    emits: [string]     # what this node puts out
  deps: [string]        # node IDs this depends on
  gates:                # quality gates cleared
    L0: boolean         # syntax/lint
    L1: boolean         # contract
    L2: boolean         # smoke
    L3: boolean         # functional
  role: string          # plain | builder | orchestrator
```

### Type definitions

| Type | What it is | Example | Gates required |
|------|-----------|---------|---------------|
| `intake` | Message entry point | Discord channel, webhook | L0+L1 |
| `router` | Routes messages to agents | hubert-team-lead group | L0+L1+L2+L3 |
| `agent` | LLM-backed agent | stability, build, shelby | L0+L1+L2+L3 |
| `tool` | Function an agent calls | get_crm_health_snapshot | L0+L1+L2 |
| `ui` | Visual surface | Chainlit chat, cockpit | L0+L1+L2 |
| `database` | State store | authsome vault, Frappe DB | L0+L1+L2 |
| `capability` | Cross-cutting infrastructure dep | Ollama Cloud, Railway | pre-enriched in capabilities.json |

Models are embedded in agent nodes (`model` field), not standalone `logic` nodes. The `builder` role is a promotion path (plain → builder → orchestrator), not a separate node type.

### State machine

```
blank → building → built → live
  ↓        ↓         ↓       ↓
  └────────┴─────────┴───→ error
```

- **blank:** node declared in manifest, no artifact on disk
- **building:** artifact exists, gates not all cleared
- **built:** all required gates cleared, not yet deployed/trafficked
- **live:** passing traffic (messages flowing through)
- **error:** was live/built, now failing a gate

### Kill-criteria check (D1)

- ✅ Every existing agent can be expressed in the schema without loss
- ✅ State can be auto-detected from filesystem + live checks
- ✅ Contract (accepts/emits) is derivable from type + tools
- ✅ Gates L0-L3 have per-type checker implementations

## D2: Read-only render of current system ✅

### Deliverable

`index.html` — self-contained force-graph page that:
1. Loads `agent-graph-v2.json` (the extended v2 format)
2. Renders nodes colored by type, sized by state
3. Supports lens switching: tier (by kind), lineage (click to focus), live (dim non-live)
4. Shows edges with directional arrows and kind labels
5. Tooltips with full gate status on hover

### Implementation

- `build_live_graph.py` — extends the existing `build_agent_graph.py` to emit the v2 schema with state/artifact/contract/gates/role
- `index.html` — force-graph renderer using vasturiano/force-graph CDN
- `serve.py` — minimal HTTP server for UI + spawn endpoint

### Kill-criteria check (D2)

- ✅ Code→graph sync stays honest (manifest generated from live scan, not hand-edited)
- ✅ All 7 agents + their tools/channels render correctly (38 nodes, 29 links)
- ✅ Lens switching works on one dataset (all / tier / lineage / live / padi)
- ✅ State detection works: 17 building, 18 built, 2 blank

## D3: Write path — spawn blank agent, gate-check to live ✅

### Deliverable

`spawn_agent.py` — CLI tool that creates a blank agent on disk:
1. Creates `agents/<id>/` package (pyproject.toml + agent.py + README + DIRECTORY)
2. Creates `web_agents/<id>/` wrapper (agent.py + root_agent.yaml)
3. Appends entry to `agent_specs/agents.yaml`
4. Rebuilds `agent-graph-v2.json` to show the new node

### State progression proven

```
blank → building (L0: agent.py exists, syntax OK)
     → building (L1: tool added to agents.yaml)
     → building (L2: wired to bridge PYTHONPATH)
     → built   (L3: bridge responds — live traffic threshold)
```

Tested end-to-end: spawned `test_spike`, added tool, wired to bridge, re-scanned graph. Each gate transition reflected in the manifest.

### UI integration

`index.html` now has a "Spawn Agent" panel with id/description inputs and a Spawn button. POSTs to `/spawn` on `serve.py`, which calls `spawn_agent.py` and returns the result. Refresh button reloads the graph.

### Kill-criteria check (D3)

- ✅ Graph→code write path works: spawn creates real files on disk
- ✅ State progression is auto-detected: blank→building→built reflected in re-scan
- ✅ Gate checks are per-type and auto-evaluated
- ✅ "Functional" gates (L3) require live traffic — honest threshold, not fakeable

## D4: Directional particles on edges ✅

Wire directional particles to one real message path — prove the graph can show live traffic.

### Implementation

`/pulse` endpoint polls bridge/authsome/LiteLLM health every 3 seconds. Active edges get green coloring + animated directional particles. 19 active edges, 20 live nodes. `reachable` (cheap heartbeat) and `live` (round-trip) are distinct signals with different visual treatments.

## D5: Writeup ✅

Paperclip reborn vs Hermes team-lead/orchestrator front-end. See `D5-WRITEUP.md` for the full architectural verdict. See `D5-CONFIDENCE.md` for the trust-gap closure analysis. See `GRADUATION.md` for the formalized promotion criteria.

## PADI swim-lane lens ✅ (post-D5)

Four horizontal bands (INTERFACES / ROUTER / AGENT·LOGIC / TOOLS·DATA) with agents anchored to evenly-spaced X slots. Vertical slices read as clean columns. Dependency rail (left edge) for cross-cutting infrastructure. Interface abstraction collapses per-channel intake nodes into channel-type interfaces.

## Agent status visuals ✅ (post-D5)

At-a-glance signals on agent nodes: size = connected node count, fill arc = gate completion (clockwise fill), center symbol = state (⚠ building, ✕ error, ◎ live pulse ring). No hover needed.

## Open questions (from spike brief)

- **Manifest scan: file-watch vs registry on write?** Current answer: registry on write (spawn_agent.py rebuilds graph after creating files). File-watch would be more "live" but adds complexity. For spike scope, registry-on-write is sufficient and honest.
- **Minimal "blank node can respond" runtime?** A blank agent with `Agent(model=LiteLlm(...), instruction="...", tools=[])` can respond to messages immediately — no tools needed. The gate ladder (L0→L1→L2→L3) is the progression from "exists" to "functional."
- **Tier + lineage lens from one dataset — layout cost?** Negligible. force-graph re-renders in <100ms on 37 nodes. dagMode('td') for tier lens, free-force for lineage. No data reload needed.

## Verdict (partial)

D1-D3 are validated. The core premise holds: a force-directed graph CAN act as a live projection of the agent system, with code as source of truth and the graph reflecting state both ways. The write path (spawn) proves graph→code works. The read path (build_live_graph.py) proves code→graph works.

Kill criteria not yet triggered. D4 (live particles) and D5 (architectural writeup) remain.
