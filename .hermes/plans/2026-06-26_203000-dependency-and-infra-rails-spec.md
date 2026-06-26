# Dependency & Infrastructure Rail Spec

> **For Hermes:** This is a spec, not a plan. Read it, understand the data model, then propose implementation slices.

---

## Problem

The graph has two toggle buttons — "Dependencies (rail)" and "Show shared" — that don't describe meaningful relationships. They're type filters, not relationship filters.

- **Dependencies (rail)** hides/shows nodes where `type === 'capability'`. No links are drawn from tools to the capabilities they actually depend on.
- **Show shared** hides/shows nodes where `shared === true`. This dumps authsome, all cred stores, all models, and all shared tools onto the canvas at the same visual level as the agent.

The result: the user sees `authsome`, `cred:github`, `cred:resend`, `Frappe CRM`, `Cloudflare` floating next to shelby and her 3 tools. These are plumbing, not peers. They should be tucked into rails that show *why* each node is there and *what* it connects to.

## What the user wants

Two distinct rails, each with real links:

1. **Dependencies rail** — "we need access to this thing in order to use the tools you've assigned to me." Tool-to-credential lines. `log_groceries → cred:frappe-crm` because that tool hits the CRM API. Not `authsome → cred:frappe-crm` (that's just the broker topology).

2. **Infrastructure rail** — "where does this agent physically run." `agent:shelby → host:hetzner-vps → docker:adk-bridge → net:tailscale → tunnel:cloudflare`. The runtime topology. Currently zero infra nodes exist in the graph.

Both rails should be collapsible drawers on the side of the graph. When closed, the canvas is clean: agents + tools + agent→tool links. When opened, the rail renders its nodes and draws real lines to the things they connect to.

Future use case: describing customer infrastructure and building it into agents for clients. The infra rail needs to be descriptive enough to represent arbitrary customer environments.

---

## Current state (handoff)

### Repos and branches

| Repo | Path | Branch | HEAD | Notes |
|------|------|--------|------|-------|
| live-agent-graph | `/opt/data/workspace/adk/live-agent-graph` | `main` | `c64e7c1` | Graph server + UI |
| forsch-adk-bridge | `/opt/data/workspace/adk/bridge` | `main` | `5509c89` | ADK agent chat bridge, Gradio sidecar |
| forsch-adk-workspace | `/opt/data/workspace/adk` (parent) | `main` | `b0e606e` | agents.yaml, factory, components |

### Running services

| Service | Port | Status | Notes |
|---------|------|--------|-------|
| Graph server | :8888 | Running | `python3 serve.py 8888` from live-agent-graph dir |
| ADK bridge | :8800 | Running | Docker `adk-bridge`, Gradio sidecar at `/chat` |
| LiteLLM | :4000 | Running | Model gateway |
| Authsome | :7998 | Running | Credential gateway |
| Cloudflared (graph) | — | Running | Tunnel to :8888, ephemeral URL |
| Cloudflared (sidecar) | — | Running | Tunnel to :8800/chat, ephemeral URL |

### What's been built this session

1. **Live agent graph promoted** from `spikes/` to `/opt/data/workspace/adk/live-agent-graph`. Committed `4dc1fd4`. Canonical docs updated `fd22661`. Skill patched.

2. **Gradio sidecar** built in bridge repo — custom Blocks layout, agent selector, quick prompts, persistent chat sessions, modular theme via `sidecar_config.py`. Reviewed twice, 10 findings fixed. Merged to main at `5509c89`.

3. **Shelby agent wired** — added to `bridge_config.yaml`, `compose.yaml` PYTHONPATH, `agents.yaml` entry regenerated (`b0e606e`). Bridge loads 8 agents, shelby responds with 3 tools: `log_groceries`, `get_grocery_log`, `add_reminder`.

4. **Shelby cluster in graph** — `clusters/shelby/cluster.yaml` created. Builder produces 19 nodes, 7 links. Only household tool family included. Shared infra (authsome, creds, models, capabilities) visible but faded behind "Show shared" toggle.

5. **Tool families system** — `shared/components.yaml` now has `tool_families: {terminal, crm, household}`. Clusters pick families via `config.tool_families` and can exclude individual tools via `config.exclude_tools`. Builder prunes shared tools not linked to any agent in cluster. Committed `04415ae`.

6. **Ghost link fix** — `index.html` was merging `capabilities.json` links unconditionally, adding 3 phantom links to pruned tool nodes. Fixed by checking both endpoints exist before merging. Committed `6c7d2dc`.

7. **Cloudflare Worker** — `cloudflare-worker.js` for single-origin routing (chat + graph under one domain). Committed `c64e7c1`.

8. **Plans written** (not yet implemented):
   - Agent focus zoom: `.hermes/plans/2026-06-26_013834-agent-focus-zoom-plan.md`
   - Gradio sidecar → graph integration: `.hermes/plans/2026-06-26_035651-gradio-sidecar-agent-graph-plan.md`
   - Graph cleanup + sidecar widgets: `.hermes/plans/2026-06-26_191200-graph-cleanup-and-sidecar-widgets.md`

### What's NOT done yet

- Agent focus zoom mode (plan exists, not implemented)
- Enter-to-send in Gradio sidecar (plan exists, not implemented)
- Sidecar iframe embedded in graph focus view (plan exists, not implemented)
- Shelby's tools are scaffolds — `log_groceries`, `get_grocery_log`, `add_reminder` exist as imports but are not fully functional
- Dependency and infra rails (this spec)
- Control plane staging docs at `forsch_frontiers/docs/control-plane/` — committed `b52f94d` on branch `docs/control-plane-staging`, not merged

### Uncommitted state

```
M __pycache__/serve.cpython-313.pyc  (noise)
?? .eval_runs/                        (eval experiment output)
?? .hermes/                            (plans dir)
?? cloudflare-worker.js               (committed on main already — this is a stray)
?? clusters/shelby/project.md         (shelby cluster notes)
```

### Key files

| File | Purpose |
|------|---------|
| `index.html` (1980 lines) | Graph frontend. All UI, toggles, lens logic, focus mode scaffolding. |
| `serve.py` (1309 lines) | HTTP server. Manifest builder, agent config/tools/verify/eval endpoints, chat proxy. |
| `build_live_graph.py` | Fallback manifest builder (CRM API is primary). |
| `capabilities.json` | Static cross-cutting capability nodes + links. Merged client-side in `loadGraph()`. |
| `shared/components.yaml` | Tool families, models, connections, `tool_connections` mapping. |
| `clusters/shelby/cluster.yaml` | Shelby cluster config. |
| `clusters/ops/cluster.yaml` | Ops cluster config (7 members, all tool families). |
| `bridge/src/forsch/adk_bridge/gradio_app.py` | Gradio sidecar app. |
| `bridge/src/forsch/adk_bridge/sidecar_config.py` | Theme, copy, prompts, enter-to-send JS. |
| `bridge/bridge_config.yaml` | Agent routing config (8 agents including shelby). |
| `bridge/compose.yaml` | Docker compose for bridge container. |

---

## Spec: Dependency & Infrastructure Rails

### Concept

Two collapsible rails on the left edge of the graph canvas. Each rail is a vertical drawer that can be opened/closed independently. When open, its nodes render in a column on the left side of the canvas with real links drawn to the things they connect to in the main graph.

**Core canvas (always visible):** agents, tools, agent→tool links.

**Dependency rail (toggle):** tool→cred/service links. Shows which credentials/services each tool needs.

**Infrastructure rail (toggle):** agent→host→container→network→tunnel. Shows where each agent physically runs.

### Rail 1: Dependencies

**Question it answers:** "What does this tool need in order to work?"

**Nodes:**
- `cred:frappe-crm` — Frappe CRM API access
- `cred:github` — GitHub OAuth
- `cred:resend` — Resend email API
- `cred:cloudflare-global` — Cloudflare API
- (future: any external service a tool calls)

**Links:**
- `tool:log_groceries → cred:frappe-crm` (this tool writes to CRM)
- `tool:get_grocery_log → cred:frappe-crm` (this tool reads from CRM)
- `tool:get_crm_health_snapshot → cred:frappe-crm`
- `tool:list_recent_crm_leads → cred:frappe-crm`
- Tools with no external dependencies: no link, no rail node.

**Data source:** `shared/components.yaml` already has a `tool_connections` map:
```yaml
tool_connections:
  get_crm_health_snapshot: frappe-crm
  list_recent_crm_leads: frappe-crm
```
This needs to be expanded. Every tool that calls an external service should declare its connection here. The builder reads this map and emits `tool:{id} → cred:{connection}` links.

**What's NOT a dependency node:**
- `authsome` itself — authsome is the *broker*, not the dependency. The tool depends on the credential, not the broker. Authsome is infrastructure (see below).
- `model:*` nodes — models are a separate axis (runtime config, not a tool dependency).
- `cap:*` nodes — capabilities describe what the agent *can do*, not what a tool *needs*. These are different. A capability like "local-mac-access" is infrastructure, not a tool dependency.

**Builder changes:**
- `_transform_crm_manifest()` and/or `build_live_graph.py` should read `tool_connections` from `shared/components.yaml` and emit `tool→cred` links.
- Cred nodes should NOT be `shared: true` in the current sense. They should be `rail: 'dependency'` so the UI can filter them independently of the shared toggle.
- Authsome node should move to the infra rail, not the dependency rail.

**UI behavior:**
- Toggle "Dependencies" → shows/hides cred nodes + tool→cred links.
- When hidden: cred nodes and their links are removed from the visible graph. Tools remain.
- When shown: cred nodes render on the left edge (rail position), with thin dashed lines to the tools that use them.
- A tool with no connections shows no rail link — clean.

### Rail 2: Infrastructure

**Question it answers:** "Where does this agent run, and what's between it and the outside world?"

**Nodes:**
- `host:hetzner-vps` — the physical/VPS host (hubertsp6, Hetzner, Tailscale `hubert-cloud-sp6.tail818cf8.ts.net`)
- `docker:adk-bridge` — the container that runs the agent
- `net:tailscale` — the mesh network connecting hosts
- `tunnel:cloudflare` — the Cloudflare tunnel exposing it externally
- `svc:litellm` — model gateway (:4000)
- `svc:authsome` — credential gateway (:7998)
- `svc:frappe-crm` — the CRM itself (Railway-hosted Frappe)

**Links:**
- `agent:shelby → docker:adk-bridge` (shelby runs inside this container)
- `docker:adk-bridge → host:hetzner-vps` (container lives on this host)
- `host:hetzner-vps → net:tailscale` (host is on this network)
- `host:hetzner-vps → tunnel:cloudflare` (host exposed via this tunnel)
- `docker:adk-bridge → svc:litellm` (container calls LiteLLM for model routing)
- `docker:adk-bridge → svc:authsome` (container calls Authsome for credentials)
- `svc:authsome → cred:github` (authsome brokers this credential — this is the only link between rails)
- `svc:frappe-crm → cred:frappe-crm` (CRM service backs this credential)

**Data source:** A new file `shared/infra.yaml` that describes the runtime topology:
```yaml
# Infrastructure topology for the ADK workspace
# Describes where agents run and what services support them.
# This is descriptive metadata, not live config — update when topology changes.

hosts:
  - id: hetzner-vps
    name: "Hetzner VPS (hubertsp6)"
    provider: hetzner
    tailscale: hubert-cloud-sp6.tail818cf8.ts.net

containers:
  - id: adk-bridge
    name: "ADK Bridge"
    host: hetzner-vps
    port: 8800
    runs_agents: true  # all ADK agents run inside this container

services:
  - id: litellm
    name: "LiteLLM (model gateway)"
    host: hetzner-vps
    port: 4000
    role: model_routing

  - id: authsome
    name: "Authsome (credential gateway)"
    host: hetzner-vps
    port: 7998
    role: credential_broker
    brokers: [github, resend, cloudflare-global, frappe-crm]

  - id: frappe-crm
    name: "Frappe CRM (ff-ops-prod)"
    host: railway  # external
    url: crm.forschfrontiers.com
    role: crm_backend

networks:
  - id: tailscale
    name: "Tailscale mesh"
    type: mesh_vpn

tunnels:
  - id: cloudflare
    name: "Cloudflare tunnel"
    type: reverse_proxy
```

**Builder changes:**
- New `build_infra_nodes()` function in `serve.py` (or `build_live_graph.py`) that reads `shared/infra.yaml` and emits infra nodes + links.
- Infra nodes tagged with `rail: 'infrastructure'` so the UI can filter them independently.
- Agent→container link only when the agent is actually wired to the bridge (check `bridge_config.yaml` or `agents.yaml`).

**UI behavior:**
- Toggle "Infrastructure" → shows/hides infra nodes + their links.
- When hidden: canvas is just agents + tools (+ optional dependency rail).
- When shown: infra nodes render on the left edge, below or above the dependency rail. Agent→container→host chain is visible.
- Infra nodes are visually distinct: smaller, muted color, structural icon (server, container, cloud).

### Node taxonomy (updated)

| Type | Rail | Examples | Currently exists? |
|------|------|----------|-------------------|
| agent | core | shelby, stability | Yes |
| tool | core | log_groceries, get_crm_health_snapshot | Yes |
| cred | dependency | cred:frappe-crm, cred:github | Yes (as `database`) |
| host | infrastructure | host:hetzner-vps | No — new |
| docker | infrastructure | docker:adk-bridge | No — new |
| net | infrastructure | net:tailscale | No — new |
| tunnel | infrastructure | tunnel:cloudflare | No — new |
| svc | infrastructure | svc:litellm, svc:authsome | No — new |
| model | (removed from canvas) | gpt-5.5, glm-5.2 | Yes, currently shown as shared |

**Models:** Models don't belong on the canvas or in a rail. They're runtime config shown in the agent inspect panel (already handled by `/agent-models` endpoint). Remove `model:*` nodes from the manifest entirely. The agent→model link is metadata, not a graph edge.

**Authsome:** Moves from shared `database` node to `svc:authsome` in the infra rail. The `authsome → cred:*` broker links become `svc:authsome → cred:*` cross-rail links visible only when both rails are open.

**Capabilities (`cap:*`):** These are the old "Dependencies (rail)" nodes. They describe what an agent *can do* (local-mac-access, ollama-cloud, railway, cloudflare, supabase). They're closer to infrastructure than dependencies — they describe the runtime environment's capabilities. Fold them into the infra rail as `cap:` nodes or convert them to `svc:` nodes. The current `capabilities.json` merge in `index.html` can be removed once the builder emits these nodes directly.

### Toggle UI

Replace the two current toggles:

```
▸ Dependencies (rail)    ← old, only filtered cap: nodes
▾ Show shared            ← old, only filtered shared: true
```

With three clear toggles:

```
▾ Agents & Tools         ← always on, not a toggle (label only)
▸ Dependencies           ← tool → cred links
▸ Infrastructure         ← agent → host → container → network
```

Both rails default closed. Canvas starts clean: agents + tools + agent→tool links. User opens a rail when they want to see the plumbing.

### Rendering

When a rail is open:
- Rail nodes render in a vertical column on the left edge of the canvas, not in the force-graph layout. They're pinned, not simulated.
- Links from rail nodes to canvas nodes are drawn as thin dashed lines.
- Rail nodes are smaller (radius ~3px vs normal ~6px), with a muted color per type.
- Hovering a rail node highlights its links and the connected canvas nodes.
- Clicking a rail node opens the inspect panel with its metadata.

When closed:
- Rail nodes and their links are removed from the visible graph entirely.
- No `shared` flag needed — the `rail` field determines visibility.

### Data flow

```
shared/components.yaml     → tool families, tool_connections (tool→cred map)
shared/infra.yaml          → hosts, containers, services, networks, tunnels
clusters/<name>/cluster.yaml → members, tool_families, exclude_tools
agents.yaml                → agent definitions, models, tools
bridge_config.yaml         → which agents are live in the bridge

serve.py /manifest?cluster=X
  → build_manifest()
    → agents + tools (from agents.yaml + components.yaml tool_families)
    → cred nodes + tool→cred links (from tool_connections)
    → infra nodes + agent→infra links (from infra.yaml)
    → returns { nodes, links, rail_nodes: { dependency: [...], infrastructure: [...] } }

index.html
  → loadGraph(cluster)
    → fetches /manifest
    → renders core nodes in force layout
    → renders rail nodes in pinned column when toggles open
    → filters by rail state, not by shared flag
```

### Migration path

1. **Create `shared/infra.yaml`** with the topology described above.
2. **Expand `tool_connections`** in `components.yaml` — add connections for all tools that call external services. Shelby's household tools currently have no declared connections (they may not need any yet — they're scaffolds).
3. **Update builder** (`_transform_crm_manifest` or `build_live_graph.py`) to:
   - Read `tool_connections` and emit `tool→cred` links.
   - Read `infra.yaml` and emit infra nodes + links.
   - Tag nodes with `rail` field instead of (or in addition to) `shared`.
   - Stop emitting `model:*` nodes to the canvas.
   - Stop emitting `authsome` as a shared database node; emit `svc:authsome` as an infra node.
4. **Update `index.html`:**
   - Replace "Dependencies (rail)" and "Show shared" toggles with "Dependencies" and "Infrastructure" toggles.
   - Update `getVisibleData()` to filter by `rail` field instead of `type === 'capability'` and `shared === true`.
   - Remove `capabilities.json` fetch from `loadGraph()` — builder now emits these nodes directly.
   - Add pinned-column rendering for rail nodes when toggles are open.
5. **Remove `capabilities.json`** once builder emits the same nodes.

### Future: customer infra

The `infra.yaml` format is designed to be per-deployment. For a customer agent, you'd have:

```yaml
# Customer: ACME Corp
hosts:
  - id: acme-prod
    name: "ACME AWS EC2"
    provider: aws
    region: us-east-1

containers:
  - id: ack-agent-customer1
    host: acme-prod
    runs_agents: [customer1-bot]

services:
  - id: acme-salesforce
    name: "Salesforce (ACME tenant)"
    host: external
    role: crm_backend

tunnels:
  - id: acme-ngrok
    type: reverse_proxy
```

The infra rail would show `agent:customer1-bot → docker:acme-agent-customer1 → host:acme-prod → net:aws-vpc → svc:acme-salesforce`. The dependency rail would show `tool:get_customer_leads → cred:salesforce`. Same rails, different topology. The data model scales.

---

## Open questions

1. **Should rail nodes be in the same force simulation or pinned?** Pinned column is cleaner but harder to implement with ForceGraph. Alternative: put them in the force sim with high `fx`/`fy` values to pin them to the left edge. ForceGraph supports fixed positions via `fx`/`fy` on node objects.

2. **Should the dependency rail show transitive deps?** e.g., `tool:log_groceries → cred:frappe-crm → svc:frappe-crm → host:railway`. Probably not in v1 — too noisy. Just show the direct tool→cred link. The infra rail handles the rest.

3. **What happens in agent focus view?** When zoomed into a single agent, both rails should still work but filtered to that agent's tools and runtime. The dependency rail shows only that agent's tool→cred links. The infra rail shows only that agent's host chain.

4. **Do capabilities (`cap:*`) still exist as a concept?** They were the original "rail" idea. If we fold them into infra, we lose the distinction between "what the environment can do" and "where the agent runs." For now, fold them in. If the distinction matters later, split them back out.

---

## Next steps

This is a spec. The next step is to write implementation slices (like the other plans in this directory) and then build. Suggested slice order:

1. Create `shared/infra.yaml` + expand `tool_connections` in `components.yaml`.
2. Update builder to emit rail-tagged nodes + tool→cred links + infra nodes.
3. Update `index.html` toggle UI + `getVisibleData()` filtering.
4. Add pinned-column rendering for rail nodes.
5. Remove `capabilities.json` merge.
6. Verify: shelby cluster shows agents + tools only by default, dependency rail shows tool→cred, infra rail shows agent→host→container.