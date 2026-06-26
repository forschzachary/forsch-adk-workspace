# PADI lane control surface — Spec 1 (Agent·Logic live)

**Date:** 2026-06-26
**Status:** approved design, pre-implementation
**File touched:** `index.html` (UI only; reuses existing server endpoints)

## Context & goal

The PADI swim-lane view (`index.html`) is a static, screen-aligned sheet of four
typed lanes (Interfaces / Router / Agent·Logic / Tools·Data) that the live agent
graph floats over. It currently only *visualizes* the cluster.

We are turning it into a **control surface**: each lane becomes a typed shelf with
its own spawn menu and a draggable library of pre-built components. The right-side
control panel's compose controls migrate into the lanes; the right panel keeps only
view/global controls.

This spec is **Spec 1 of a phased build**. It delivers the full lane-header pattern
and a clean per-lane "spawner adapter" seam, with **Agent·Logic fully wired for real**.
The other three lanes show the same header pattern but disabled ("not wired yet").
Tools, Interfaces, and Router backends are each a **follow-on spec** (2–4) that fills
in a spawner-adapter entry — no further UI rework.

## Why phased (data-model finding)

From `build_live_graph.py` + `registry/agents/agents.yaml`, only **agents** and
**clusters** are standalone entities. The other lane node types are derived from
agent attributes:

| Lane | Underlying model | "spawn" / "drag in" semantics (future specs) |
|---|---|---|
| Agent · Logic | entity in `agents.yaml` (`spawn_agent.py`) | spawn blank / add from registry — **real now** |
| Tools · Data | a name in an agent's `tools: []` (+ credentials) | scaffold tool fn → attach to an agent's tool list |
| Interfaces | an agent's `discord_channels` / web bridge | define channel → attach to an agent |
| Router | an agent **group** (`group:` field) | create group → assign agents to it |

So three of four lanes are *edit-an-agent* semantics (handled later via `/save-agent`),
not standalone spawns. Spec 1 does not implement them; it only reserves their seam.

## Current state (what exists, reused as-is)

- **Endpoints:** `POST /spawn` `{agent_id, description}` (blank agent + add to cluster),
  `POST /add-agent` `{agent_id, cluster}` (add registry agent to current cluster),
  `GET registry/agents/agents.yaml` (built-agent library, already fetched by
  `loadRegistryAgents()`).
- **Right panel** currently holds: cluster indicator, Lens buttons, Deps/Infra toggles,
  **Add Agent to Cluster** (select + button), **Spawn Agent** (id/desc + button),
  Refresh, Hubert chat, legend.
- **PADI internals (already shipped):** `#swimlane-overlay` (4 CSS-grid lane rows,
  hue-washed, labels), `layoutPadi()` (1:1 camera, lane targets), `padiLaneForce`
  (tight float), `drawPadiLink` (vertical riser → static pin → bend), camera locked
  in PADI (`enableZoom/PanInteraction(false)`).

## Design

### 1. Lane header

Each `.swimlane-row` gets a header block pinned to its **top-left** (label moves up
from vertical-center):

```
▎AGENT · LOGIC      ＋ New agent
▎[ stability ][ assistant ][ brand ] …      ← draggable library strip
```

- **Label** — existing `.swimlane-label` content, re-anchored to the lane top
  (`top: 12px` instead of `50%`), keeps the hue accent bar.
- **Spawn control** — a `＋ New {type}` button next to the label. For Agent·Logic it
  opens a small inline form (agent_id + optional description → `/spawn`). Disabled
  lanes show the button greyed with a `not wired yet` tooltip.
- **Library strip** — a single horizontal, scrollable row of **chips**, one per
  pre-built component of that lane's type (Agent·Logic = registry agents). Each chip
  is `draggable`. Chips already present in the current cluster are marked (dimmed /
  check) and not re-addable.

### 2. Pointer-events model

The overlay is `pointer-events: none` so it never blocks canvas drag/click. Only the
**header** sub-region re-enables events:

- `.swimlane-header { pointer-events: auto }` — clickable spawn button + draggable chips.
- The lane **body** stays `pointer-events: none` **except during an active drag**: on
  `dragstart` of a chip, add `body.dragging` which sets the lane bodies to
  `pointer-events: auto` (so they can be `dragover`/`drop` targets); on `dragend`,
  remove it. This keeps node drag/click unaffected when not dragging a chip.

### 3. Right panel changes

- **Move out** → into the Agent·Logic header: the **Spawn Agent** and **Add Agent to
  Cluster** sections (their existing handlers are reused, just re-parented / re-bound).
- **Stay** (slimmed right panel = "view & global"): cluster indicator, Lens buttons,
  Deps/Infra toggles, Refresh graph, Hubert chat, legend.

### 4. Spawner-adapter seam

A single map decouples lane UI from per-type behavior:

```js
const LANE_SPAWNERS = {
  agent: {
    blankLabel: 'New agent',
    spawnBlank(input)  { /* POST /spawn {agent_id, description}; then refresh */ },
    library()          { /* registry agents → [{id, name, state, inCluster}] */ },
    onDrop(item)       { /* POST /add-agent {agent_id:item.id, cluster}; refresh */ },
  },
  tool:      { disabled: true },   // Spec 2
  interface: { disabled: true },   // Spec 3
  router:    { disabled: true },   // Spec 4
};
```

Each lane's header is rendered generically from its `LANE_SPAWNERS[laneKey]`. A
`disabled` entry renders the greyed header. Follow-on specs replace a stub with a real
entry; the header/drag code is untouched.

`PADI_LANES` already carries `key` (`interfaces|router|agent|tools`); map lane key →
spawner key (`interfaces→interface`, `tools→tool`, `agent→agent`, `router→router`).

### 5. Drag-and-drop mechanic

- Library chip `dragstart` → `dataTransfer.setData('application/x-lane-item', JSON({laneKey, id}))`.
- Lane body `dragover` (when `body.dragging`) → `preventDefault()` + highlight class so
  the lane shows a drop affordance.
- Lane body `drop` → parse item; if its `laneKey` matches the dropped lane and the
  spawner isn't disabled and the item isn't already in-cluster → `spawner.onDrop(item)`.
  A mismatched lane (drop a tool on the agent lane) is rejected with a brief shake/flash.
- After a successful spawn/add/drop, call the existing graph refresh so the new node
  appears and the lane re-lays-out via `layoutPadi()`.

### 6. Data flow

- **Spawn blank (agent):** header form → `/spawn` → on ok, refresh graph → new agent
  node floats into Agent·Logic lane.
- **Add from library (click or drag):** chip → `/add-agent` → refresh → node appears.
- **Library population:** `loadRegistryAgents()` result feeds `LANE_SPAWNERS.agent.library()`;
  in-cluster detection compares against current `graphData` agent ids.

## Visual / layout details

- Header sits in the lane's top ~44px; lane node targets (`layoutPadi`) shift down
  slightly so floating nodes don't collide with the header (reduce usable lane to start
  below the header band).
- Chips: compact, monospace id, lane-hue tinted border, `cursor: grab`. Dimmed +
  non-draggable when already in cluster.
- Disabled lanes: header at reduced opacity, `＋` greyed, `not wired yet` title.
- Keep current motion (tight float) and locked camera.

## Edge cases

- Empty library (no built components of a type) → header shows just the `＋` and a faint
  "no built {type}s yet".
- Spawn/add failure → inline error message in the header (reuse existing `.msg` styling),
  no node added.
- Dropping a chip outside any lane, or on the wrong lane → no-op + reject flash.
- Cluster with zero agents → Agent·Logic lane is empty but header still works.
- Resize → headers reflow with the CSS-grid lanes (already handled by `ResizeObserver`).

## Verification plan (browser, on shelby/client-acme via local serve.py)

1. Agent·Logic header renders with label top-left, `＋ New agent`, and a chip per
   registry agent; other lanes show disabled headers.
2. Right panel no longer shows Spawn/Add sections; still shows lens/global controls.
3. Click `＋ New agent`, spawn a blank id → new node appears in Agent·Logic lane
   (verify via graph node count + screenshot).
4. Drag a built-agent chip into the Agent·Logic lane → `/add-agent` fires, node appears.
5. Drag a chip onto a different lane → rejected, no add.
6. Canvas node drag + click still work (pointer-events not broken by headers).
7. No console errors; camera still locked; motion still tight.

## Out of scope (future specs)

- **Spec 2 — Tools·Data:** scaffold a tool fn + attach to an agent's `tools` list;
  data/credential nodes.
- **Spec 3 — Interfaces:** define a channel + attach to an agent's `discord_channels`.
- **Spec 4 — Router:** create an agent group + assign agents.
- Emptying the right panel entirely / further IA consolidation.
- Any new server endpoints (Spec 1 reuses `/spawn`, `/add-agent` only).
