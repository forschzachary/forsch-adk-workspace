# Repeatable PADI Components Design

Date: 2026-06-26
Status: Approved

## [S1] Problem

The PADI swim-lane control surface has 4 lanes (Interfaces, Router, Agent · Logic, Tools · Data), but only the Agent lane has a working shelf (label + spawn button + library pills). The other three lanes are stubs with `disabled: true`. The goal is to wire up all three disabled lanes with the same graph-native shelf pattern.

## [S2] Solution

Fill in the `LANE_SPAWNERS` stubs for `tool`, `interface`, and `router` with working `library()` and `onDrop()` implementations. Each lane gets the same shelf pattern as agent: label node + spawn button node + library pill nodes (ForceGraph nodes in fixed slots under the lane label).

### Library sources

| Lane | Source | Filter |
|------|--------|--------|
| tool | `graphData.nodes` | `type === 'tool'` |
| interface | `graphData.nodes` (collapsed) | `type === 'intake'`, grouped by channel type |
| router | `graphData.nodes` | `type === 'router'` |

The `library()` function for each lane reads from `graphData.nodes` directly — no new registry YAML files needed.

### Spawning

Spawning stays disabled for tool, interface, and router lanes (no spawn endpoints exist yet). The spawn button remains present but disabled. This can be wired up later when backend endpoints are added.

### onDrop behavior

Each lane's `onDrop()` calls `openInspect()` to show the node's details in the inspect panel. This is because tools, interfaces, and routers are already nodes in the graph — they're not "added to clusters" like agents. The shelf is a reference surface for viewing what's available.

Clicking a library pill also triggers `openInspect()` via `handlePadiControlClick`.

## [S3] Implementation

### Changes to `index.html`

1. **Add helper functions** after `clusterHasAgent()`:
   ```js
   function clusterHasNode(nodeId) {
     return !!(graphData && graphData.nodes && graphData.nodes.some(n => n.id === nodeId));
   }

   function findGraphNode(nodeId) {
     return (graphData?.nodes || []).find(n => n.id === nodeId);
   }
   ```

2. **Replace `LANE_SPAWNERS.tool`** stub with:
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
     onDrop(item, msg) {
       const node = findGraphNode('tool:' + item.id);
       if (node) openInspect(node);
     },
   },
   ```

3. **Replace `LANE_SPAWNERS.interface`** stub with:
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
     onDrop(item, msg) {
       const node = findGraphNode('iface:' + item.id);
       if (node) openInspect(node);
     },
   },
   ```

4. **Replace `LANE_SPAWNERS.router`** stub with:
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
     onDrop(item, msg) {
       const node = findGraphNode('router:' + item.id);
       if (node) openInspect(node);
     },
   },
   ```

5. **Add click handlers** to `handlePadiControlClick` for tool, interface, and router library pills.

### What does NOT change

- `buildPadiControlNodes()` — already iterates all lanes dynamically
- `layoutPadiControlShelf()` — already handles all lanes
- `PADI_LANES` constant — no new lanes
- The snap-back/drag behavior — already works for all `padiControl` nodes
- The DOM-based `renderLaneLibraries()` — remains as-is (PADI graph-native controls are the active surface)

## [S4] Verification

1. `python3 -m pytest -q` — existing tests pass
2. Local preview with `GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898`
3. Verify all 4 lanes show shelf controls: label + spawn (disabled) + library pills
4. Verify tool pills show from graph data (12 tools)
5. Verify interface pills show collapsed intake nodes (6 channels → ~2-3 groups)
6. Verify router pill shows (1 router)
7. Verify drag-snap-back works for all new library pills
