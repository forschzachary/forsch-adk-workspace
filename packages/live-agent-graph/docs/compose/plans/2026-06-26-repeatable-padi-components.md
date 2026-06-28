# Repeatable PADI Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up the tool, interface, and router lanes with the same graph-native PADI shelf pattern as the agent lane.

**Architecture:** Fill in `LANE_SPAWNERS` stubs in `index.html` with working `library()` and `onDrop()` functions. Each lane reads from `graphData.nodes` to populate its library pills. No new files, no new abstractions.

**Tech Stack:** Vanilla JS in `index.html`, ForceGraph for rendering, existing `graphData` and `collapseIntake()`.

## Global Constraints

- PADI shelf controls are ForceGraph nodes, not static DOM overlays
- They live in graph coordinates under their lane title
- They do not use a packing algorithm
- They do not visually scale or resize with zoom
- If dragged, they snap back to their assigned slot
- Spawn buttons stay disabled for tool/interface/router (no backend endpoints yet)

---

### Task 1: Wire up tool lane spawner

**Covers:** [S2, S3]

**Files:**
- Modify: `index.html:1967` (replace `LANE_SPAWNERS.tool` stub)

**Interfaces:**
- Consumes: `graphData.nodes`, `currentCluster`, `mutationHeaders()`, `ensureGraphSecret()`
- Produces: Working `LANE_SPAWNERS.tool.library()` and `onDrop()`

- [ ] **Step 1: Replace the tool spawner stub**

In `index.html`, replace line 1967:

```js
tool: { disabled: true, blankLabel: 'New tool' },
```

With:

```js
tool: {
  blankLabel: 'New tool',
  disabled: true,
  library() {
    return (graphData?.nodes || [])
      .filter(n => n.type === 'tool')
      .map(n => ({
        id: n.id.replace('tool:', ''),
        name: n.name || n.id.replace('tool:', ''),
        inCluster: clusterHasNode(n.id),
      }));
  },
  onDrop(item, msg) { addNodeToCluster('tool', item.id, msg); },
},
```

- [ ] **Step 2: Add helper functions**

After the `clusterHasAgent()` function (line ~1917), add:

```js
function clusterHasNode(nodeId) {
  return !!(graphData && graphData.nodes && graphData.nodes.some(n => n.id === nodeId));
}

async function addNodeToCluster(type, id, msgEl) {
  if (!(await ensureGraphSecret())) { setLaneMsg(msgEl, 'err', 'Edits locked'); return; }
  setLaneMsg(msgEl, '', 'Adding…');
  const body = `type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`;
  fetch(apiUrl('/wire'), { method: 'POST', headers: mutationHeaders(), body })
    .then(r => r.json())
    .then(data => {
      if (data.ok) { setLaneMsg(msgEl, 'ok', 'Added'); loadGraph(currentCluster); }
      else setLaneMsg(msgEl, 'err', data.error || 'Failed');
    })
    .catch(() => setLaneMsg(msgEl, 'err', 'Network error'));
}
```

- [ ] **Step 3: Verify tool shelf renders**

Run: `GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898`
Open: `http://127.0.0.1:8898/?review=1782501510163#cluster=shelby`
Expected: Tools lane shows label + spawn (disabled) + ~12 tool pills

---

### Task 2: Wire up interface lane spawner

**Covers:** [S2, S3]

**Files:**
- Modify: `index.html:1968` (replace `LANE_SPAWNERS.interface` stub)

**Interfaces:**
- Consumes: `graphData.nodes`, `collapseIntake()`
- Produces: Working `LANE_SPAWNERS.interface.library()`

- [ ] **Step 1: Replace the interface spawner stub**

In `index.html`, replace line 1968:

```js
interface: { disabled: true, blankLabel: 'New interface' },
```

With:

```js
interface: {
  blankLabel: 'New interface',
  disabled: true,
  library() {
    const collapsed = collapseIntake({ nodes: graphData?.nodes || [], links: [] });
    return collapsed.nodes
      .filter(n => n.type === 'intake')
      .map(n => ({
        id: n.id.replace('iface:', ''),
        name: n.name || n.id.replace('iface:', ''),
        inCluster: clusterHasNode(n.id),
      }));
  },
  onDrop(item, msg) { addNodeToCluster('interface', item.id, msg); },
},
```

- [ ] **Step 2: Verify interface shelf renders**

Run: `GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898`
Open: `http://127.0.0.1:8898/?review=1782501510163#cluster=shelby`
Expected: Interfaces lane shows label + spawn (disabled) + ~2-3 collapsed interface pills (Discord, etc.)

---

### Task 3: Wire up router lane spawner

**Covers:** [S2, S3]

**Files:**
- Modify: `index.html:1969` (replace `LANE_SPAWNERS.router` stub)

**Interfaces:**
- Consumes: `graphData.nodes`
- Produces: Working `LANE_SPAWNERS.router.library()`

- [ ] **Step 1: Replace the router spawner stub**

In `index.html`, replace line 1969:

```js
router: { disabled: true, blankLabel: 'New router' },
```

With:

```js
router: {
  blankLabel: 'New router',
  disabled: true,
  library() {
    return (graphData?.nodes || [])
      .filter(n => n.type === 'router')
      .map(n => ({
        id: n.id.replace('router:', ''),
        name: n.name || n.id.replace('router:', ''),
        inCluster: clusterHasNode(n.id),
      }));
  },
  onDrop(item, msg) { addNodeToCluster('router', item.id, msg); },
},
```

- [ ] **Step 2: Verify router shelf renders**

Run: `GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898`
Open: `http://127.0.0.1:8898/?review=1782501510163#cluster=shelby`
Expected: Router lane shows label + spawn (disabled) + 1 router pill

---

### Task 4: Verify all lanes and run tests

**Covers:** [S4]

**Files:**
- None (verification only)

- [ ] **Step 1: Run existing tests**

Run: `python3 -m pytest -q`
Expected: 4 passed (or more)

- [ ] **Step 2: Visual verification**

Run: `GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898`
Open: `http://127.0.0.1:8898/?review=1782501510163#cluster=shelby`
Verify:
- All 4 lanes show shelf controls (label + spawn + library pills)
- Tool pills show ~12 tools
- Interface pills show ~2-3 collapsed groups
- Router pill shows 1 router
- Drag-snap-back works for all new library pills

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: wire up tool, interface, router PADI shelf lanes"
```
