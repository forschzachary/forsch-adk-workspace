# Spike: Live Agent Graph — force-graph control surface for the ADK bridge

**Status:** D1 ✅ D2 ✅ D3 ✅ | D4 pending | D5 pending  
**Spike ID:** live-agent-graph  
**Started:** 2026-06-23  
**Repo:** https://github.com/forschzachary/live-agent-graph (private)

## D1: Node Schema + Manifest Format ✅

### Node schema (canonical)

Every node, regardless of type:

```yaml
node:
  id: string            # unique, e.g. "agent:stability"
  type: string          # intake | router | agent | tool | design | logic | ui | database | builder
  model: string         # LLM model code (for agent/logic nodes)
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
| `design` | Spec/doc artifact | ARCHITECTURE.md | L0+L1 |
| `logic` | LLM model backend | gpt-5.5, glm-5.2 | L0+L1+L2 |
| `ui` | Visual surface | Chainlit chat, cockpit | L0+L1+L2 |
| `database` | State store | authsome vault, Frappe DB | L0+L1+L2 |
| `builder` | Agent that builds agents | adk_factory (future) | L0+L1+L2+L3 |

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
- ✅ All 7 agents + their tools/models/channels render correctly (37 nodes, 37 links)
- ✅ Lens switching works on one dataset (all / tier / lineage / live)
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

## D4: Directional particles on edges (pending)

Wire directional particles to one real message path — prove the graph can show live traffic.

## D5: Writeup (pending)

Paperclip reborn vs Hermes team-lead/orchestrator front-end.

## Open questions (from spike brief)

- **Manifest scan: file-watch vs registry on write?** Current answer: registry on write (spawn_agent.py rebuilds graph after creating files). File-watch would be more "live" but adds complexity. For spike scope, registry-on-write is sufficient and honest.
- **Minimal "blank node can respond" runtime?** A blank agent with `Agent(model=LiteLlm(...), instruction="...", tools=[])` can respond to messages immediately — no tools needed. The gate ladder (L0→L1→L2→L3) is the progression from "exists" to "functional."
- **Tier + lineage lens from one dataset — layout cost?** Negligible. force-graph re-renders in <100ms on 37 nodes. dagMode('td') for tier lens, free-force for lineage. No data reload needed.

## Verdict (partial)

D1-D3 are validated. The core premise holds: a force-directed graph CAN act as a live projection of the agent system, with code as source of truth and the graph reflecting state both ways. The write path (spawn) proves graph→code works. The read path (build_live_graph.py) proves code→graph works.

Kill criteria not yet triggered. D4 (live particles) and D5 (architectural writeup) remain.
