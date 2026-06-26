# Dependency & Infrastructure Rails — Implementation Plan

> Spec: `.hermes/plans/2026-06-26_203000-dependency-and-infra-rails-spec.md`

## Slice 1 — Data layer

- [ ] Create `shared/infra.yaml` with runtime topology (hosts, containers, services, networks, tunnels)
- [ ] Expand `tool_connections` in `components.yaml` — add connections for all tools that call external services
- [ ] Remove `models:` list from `components.yaml` (models stay in agents.yaml, shown in inspect panel only)

## Slice 2 — Builder

- [ ] Update `_transform_crm_manifest()` to read `tool_connections` and emit `tool→cred` links
- [ ] New `build_infra_nodes()` reads `infra.yaml`, emits infra nodes with `rail: 'infrastructure'`
- [ ] Tag cred nodes with `rail: 'dependency'` instead of `shared: true`
- [ ] Stop emitting `model:*` nodes to the canvas
- [ ] Move `authsome` from shared database to `svc:authsome` infra node
- [ ] Emit `rail_nodes: { dependency: [...], infrastructure: [...] }` in manifest response

## Slice 3 — UI toggles

- [ ] Replace "Dependencies (rail)" and "Show shared" with "Dependencies" and "Infrastructure" toggles
- [ ] Update `getVisibleData()` to filter by `rail` field instead of `type === 'capability'` and `shared === true`
- [ ] Remove `capabilities.json` fetch from `loadGraph()`

## Slice 4 — Rail rendering

- [ ] Pinned column on left edge for rail nodes (use `fx`/`fy` fixed positions)
- [ ] Thin dashed links from rail nodes to canvas nodes
- [ ] Smaller radius (~3px), muted colors per rail type
- [ ] Hover highlights connected nodes
- [ ] Click opens inspect panel with metadata

## Verification

- [ ] Shelby cluster: agents + tools only by default, dependency rail shows tool→cred, infra rail shows agent→host→container
- [ ] Ops cluster: all rails populated, no model nodes on canvas
- [ ] Agent focus view: rails filtered to that agent's scope

---

## Focus view fixes (from review)

### Fix 1 — Dynamic zoom

`enterAgentFocus()` hardcodes `fg.zoom(2.2, 650)`. Replace with dynamic zoom based on node count:

```js
const nodeCount = buildAgentFocusData().nodes.length;
const zoom = Math.max(0.8, Math.min(2.5, 3.0 / Math.sqrt(nodeCount)));
fg.zoom(zoom, 650);
```

100 tools -> zoom out. 3 tools -> zoom in. always readable.

### Fix 2 — Tiered layout (replace ring)

Current: dev nodes in a circle (radius 220), tools in a flat grid to the left.

New layout in `applyLayout()` for focus mode:

```
Tier 0 (top):     agent pinned at (0, -200)
Tier 1 (mid):     dev nodes (Config, Tools, Evals, etc.) in a horizontal row at y=0
Tier 2 (bottom):  real tools fanned out at y=200+
```

- Agent centered above everything
- Dev nodes evenly spaced in a row below agent, dynamic spacing based on count
- Real tools spread below, spacing adjusts: 1 agent + 100 tools -> wide fan. 3 agents + 1 tool -> tight
- Edges from tools go up to a routing tier, then curve to the agent (the fan pattern from the drawing)

### Fix 3 — Y-pins preserved

`applyLayout()` should set `fy` on all focus nodes (synthetic + real). Currently only `fx` is set for neighbors (line 835-836) but `fy` uses a fixed offset. Replace with tier-based `fy` that respects node role:
- Agent: `fy = -200`
- Dev nodes (synthetic): `fy = 0`
- Tools: `fy = 200`
- Model: `fy = 100` (between dev nodes and tools)

Spread within tiers using hash-based jitter (existing pattern at line 858-859) but with wider spread for tools.
