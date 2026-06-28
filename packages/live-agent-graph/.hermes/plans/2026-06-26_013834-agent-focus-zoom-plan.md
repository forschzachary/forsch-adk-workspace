# Agent Focus Zoom Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add an agent-focus mode to the existing Live Agent Graph so a user can double-click an agent node in project view, zoom into that same graph, and operate a deeper agent-development surface without opening a separate `/agents/:agentId` page or reviving the old `:8780` cockpit.

**Architecture:** Keep `index.html` as the single graph shell. Add a UI-only focus mode that derives an agent-specific subgraph from the existing manifest and fetches deeper configuration/tool/model/verify/eval data from `serve.py`. Do not fork the graph, do not invent a second source of truth, and do not move state into browser-only structures that can drift from disk/CRM. Evals are first-class gates: `verify` proves import/files, `eval` proves behavior, tool trajectory, and final response quality.

**Tech Stack:** Plain JavaScript in `/opt/data/workspace/adk/live-agent-graph/index.html`, Python stdlib HTTP server in `/opt/data/workspace/adk/live-agent-graph/serve.py`, ForceGraph canvas renderer, existing `/agent-config`, `/agent-tools`, `/agent-models`, `/agent-verify`, `/agent-generate`, `/agent-config` POST endpoints, plus new minimal eval endpoints/files introduced in this plan.

---

## Current Context

The current working direction is native Frappe + Live Agent Graph, not the old builder cockpit:

- Main repo: `/opt/data/workspace/adk/live-agent-graph/`
- Live graph server: `python3 serve.py 8888`, currently returning 200 on `/pulse`, `/clusters`, and `/manifest?cluster=ops`.
- Project view already exists in `index.html`:
  - cluster tabs: `loadClusters()` / `loadGraph(currentCluster)`
  - PADI/project lens: `currentLens = 'padi'`
  - click inspect panel: `openInspect(node)`
  - AI sidecar: `/chat`
  - wiring: `/wire`
  - model assignment: `/models` + `/save-agent`
- Deep agent APIs already exist in `serve.py`:
  - `GET /agent-config?agent_id=<id>`
  - `POST /agent-config`
  - `POST /agent-generate`
  - `GET /agent-verify?agent_id=<id>`
  - `GET /agent-tools`
  - `GET /agent-models`
- Evals are not just UI decoration. ADK's evaluation model checks both trajectory/tool use and final response quality. The focus view must reserve real eval contracts early so "live" promotion can depend on behavior, not just successful imports.
- Existing gotchas from the skill:
  - ForceGraph mutates `link.source`/`link.target`; always use `lid()`.
  - `computeNodeMetrics()` must run after `collapseIntake()`.
  - `serve.py` changes require process restart.
  - `index.html` is conflict-prone; keep changes tightly grouped.

## Product Definition

### What this builds

A two-altitude graph:

1. **Project view**
   - Existing cluster/project graph.
   - PADI default lens stays.
   - Cluster tabs remain top-level project navigation.

2. **Agent focus view**
   - Entered by double-clicking an agent node, or by clicking a small `Focus` button in the inspect panel.
   - Same ForceGraph instance and same manifest.
   - Camera zooms to the agent.
   - Visible nodes narrow to the focused agent's local neighborhood plus synthetic development nodes.
   - Top chrome shows breadcrumb: `Project: ops / Agent: stability` plus `Back to project`.
   - The right panel becomes an agent workbench: config, tools, model/runtime, instruction, evalsets, last eval run, generate, verify.

### Non-goals

- Do not build or route to `/agents/:agentId`.
- Do not revive the old `forsch.adk_builder` cockpit on `:8780`.
- Do not add a framework.
- Do not embed Gradio in the graph yet. The Gradio spike is useful later for richer chat/eval surfaces, but agent focus should land first as native graph UI.
- Do not treat evals as a decorative placeholder. A minimal eval surface belongs in this slice: list evalsets, run evals, show trajectory/final-response status, and mark eval freshness.
- Do not invent durable browser state. Disk/CRM/manifest remains source of truth.

---

## Proposed Implementation

Add three small layers:

1. **Mode state** in `index.html`
   ```js
   let viewMode = 'project'; // 'project' | 'agent'
   let focusedAgentId = null; // full node id, e.g. 'agent:ops'
   let focusedAgentConfig = null;
   let focusedAgentTools = [];
   let focusedAgentModels = [];
   let focusedAgentVerify = null;
   let focusedAgentEvalsets = [];
   let focusedAgentEval = null;
   ```

2. **Derived graph projection** in `getVisibleData()`
   - If `viewMode === 'project'`, keep current behavior.
   - If `viewMode === 'agent'`, return:
     - the focused agent node
     - its directly connected existing manifest nodes
     - synthetic development nodes for `config`, `tools`, `evals`, `runtime`, `chat`, `generate`, `verify`
     - synthetic links from the agent to each development node
   - Mark synthetic nodes with `synthetic: true` and `focusChild: true` so they are visually distinct and never treated as source-of-truth artifacts.

3. **Agent workbench panel**
   - Extend `openInspect(node)` behavior:
     - normal project nodes keep current inspect panel
     - focused agent opens agent workbench
     - synthetic focus nodes switch the workbench tab/section
   - Keep writes routed through existing endpoints, except eval support, which gets a deliberately small new endpoint pair: `GET /agent-evals?agent_id=<id>` and `POST /agent-eval-run`.

4. **Eval gate contract**
   - Evalsets live as artifacts under `evalsets/<agent_id>/` or wherever the later ADK runner expects them; the browser only lists/runs them.
   - Last eval result is persisted under `.eval_runs/<agent_id>/last.json` for fast display.
   - A passing eval result has separate fields for `trajectory_pass` and `final_response_pass`.
   - Promotion/live state must later require both `focusedAgentVerify.ok` and `focusedAgentEval.ok`. This plan does not implement promotion blocking yet, but it shapes the data so that gate can be added cleanly.

---

## Task Plan

### Task 1: Add a tiny browser-level test harness for graph projections

**Objective:** Make the focus-mode graph filtering testable without a browser before touching ForceGraph behavior.

**Files:**
- Create: `/opt/data/workspace/adk/live-agent-graph/tests/test_focus_projection.py`
- Create: `/opt/data/workspace/adk/live-agent-graph/focus_projection.js` only if extracting shared projection logic is cleaner; otherwise keep JS in `index.html` and test via small replicated fixture in Python.

**Recommended minimal path:** Since the app has no JS test stack, write Python tests that validate expected projection rules against sample graph data. This is not perfect, but it catches the main algorithmic mistakes without adding Node tooling.

**Step 1: Create failing tests**

Create `tests/test_focus_projection.py`:

```python
from __future__ import annotations


def lid(value):
    if isinstance(value, dict):
        return value["id"]
    return value


def agent_neighborhood(data, focused_id):
    # This mirrors the browser algorithm. Keep simple and update if the JS changes.
    neighbor_ids = {focused_id}
    for link in data["links"]:
        source = lid(link["source"])
        target = lid(link["target"])
        if source == focused_id:
            neighbor_ids.add(target)
        if target == focused_id:
            neighbor_ids.add(source)
    return neighbor_ids


def test_agent_neighborhood_handles_forcegraph_mutated_links():
    data = {
        "nodes": [
            {"id": "agent:ops", "type": "agent"},
            {"id": "tool:deploy", "type": "tool"},
            {"id": "agent:brand", "type": "agent"},
        ],
        "links": [
            {"source": {"id": "agent:ops"}, "target": {"id": "tool:deploy"}},
            {"source": "agent:brand", "target": "tool:deploy"},
        ],
    }

    assert agent_neighborhood(data, "agent:ops") == {"agent:ops", "tool:deploy"}


def test_focus_synthetic_node_ids_are_namespaced_by_agent():
    agent_id = "agent:ops"
    suffixes = ["config", "tools", "evals", "runtime", "chat", "generate", "verify"]
    ids = [f"focus:{agent_id}:{suffix}" for suffix in suffixes]

    assert len(ids) == len(set(ids))
    assert all(node_id.startswith("focus:agent:ops:") for node_id in ids)
```

**Step 2: Run tests to verify pass/fail baseline**

Run:

```bash
cd /opt/data/workspace/adk/live-agent-graph
python3 -m pytest tests/test_focus_projection.py -q
```

Expected: Either pass if pytest is available, or fail because pytest is missing. If pytest is missing, use the factory venv if available:

```bash
/opt/data/workspace/adk/factory/.venv/bin/python3.12 -m pytest tests/test_focus_projection.py -q
```

**Step 3: Commit**

```bash
cd /opt/data/workspace/adk/live-agent-graph
git add tests/test_focus_projection.py
git commit -m "test: pin agent focus projection rules"
```

---

### Task 2: Add explicit view-mode state and top-bar breadcrumb

**Objective:** Introduce the UI state for project vs agent mode without changing graph filtering yet.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Add state near current state block**

Find:

```js
let graphData, currentLens = 'padi', lineageRoot = null, showDeps = false, showShared = true;
let currentCluster = null;
```

Change to:

```js
let graphData, currentLens = 'padi', lineageRoot = null, showDeps = false, showShared = true;
let currentCluster = null;
let viewMode = 'project'; // 'project' | 'agent'
let focusedAgentId = null;
let focusedAgentConfig = null;
let focusedAgentTools = [];
let focusedAgentModels = [];
let focusedAgentVerify = null;
let focusedAgentEvalsets = [];
let focusedAgentEval = null;
```

**Step 2: Add breadcrumb markup near the existing tab bar/panel chrome**

Add a compact status strip above or near `#graph`:

```html
<div id="view-crumb" class="view-crumb">
  <span id="view-crumb-text">Project view</span>
  <button id="back-project-btn" style="display:none">Back to project</button>
</div>
```

**Step 3: Add CSS**

Add minimal styles near existing top chrome CSS:

```css
.view-crumb {
  position: absolute;
  top: 48px;
  left: 16px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid rgba(139,148,158,0.25);
  border-radius: 8px;
  background: rgba(13,17,23,0.82);
  color: #8b949e;
  font-size: 12px;
}
.view-crumb button {
  border: 1px solid #30363d;
  border-radius: 6px;
  background: #161b22;
  color: #c9d1d9;
  cursor: pointer;
  padding: 3px 8px;
}
.view-crumb button:hover { border-color: #58a6ff; }
```

**Step 4: Add update function**

Add below state helpers:

```js
function updateViewCrumb() {
  const text = document.getElementById('view-crumb-text');
  const back = document.getElementById('back-project-btn');
  if (!text || !back) return;

  if (viewMode === 'agent' && focusedAgentId) {
    const cleanId = focusedAgentId.replace('agent:', '');
    text.textContent = `Project: ${currentCluster || 'unknown'} / Agent: ${cleanId}`;
    back.style.display = 'inline-block';
  } else {
    text.textContent = currentCluster ? `Project: ${currentCluster}` : 'Project view';
    back.style.display = 'none';
  }
}
```

**Step 5: Wire back button**

```js
document.getElementById('back-project-btn').addEventListener('click', exitAgentFocus);
```

`exitAgentFocus` is added in Task 4. For this task, if needed, stub it:

```js
function exitAgentFocus() {
  viewMode = 'project';
  focusedAgentId = null;
  focusedAgentConfig = null;
  focusedAgentVerify = null;
  updateViewCrumb();
  renderLens();
}
```

**Step 6: Call `updateViewCrumb()` from `loadGraph()` or after cluster selection**

At minimum, call it after `currentCluster` is set in `loadClusters()` / cluster selection path and at the end of `renderLens()`.

**Step 7: Verify**

Run:

```bash
cd /opt/data/workspace/adk/live-agent-graph
python3 -m py_compile serve.py
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8888/
```

Expected: `200` for the graph page. Then use browser to confirm crumb shows `Project: ops` when the ops cluster is selected.

**Step 8: Commit**

```bash
git add index.html
git commit -m "feat: add graph view mode breadcrumb"
```

---

### Task 3: Implement focus projection in `getVisibleData()`

**Objective:** In agent mode, show the focused agent, its neighborhood, and synthetic development nodes.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Add helper functions near `getVisibleData()`**

```js
function getNodeById(id) {
  return (graphData?.nodes || []).find(n => n.id === id) || null;
}

function focusNodeId(agentId, suffix) {
  return `focus:${agentId}:${suffix}`;
}

function buildFocusDevNodes(agent) {
  const base = agent.id;
  const clean = base.replace('agent:', '');
  return [
    { id: focusNodeId(base, 'config'), name: 'Config', type: 'ui', state: agent.state || 'blank', synthetic: true, focusChild: true, artifact: `agent-config:${clean}` },
    { id: focusNodeId(base, 'tools'), name: 'Tools', type: 'tool', state: 'built', synthetic: true, focusChild: true, artifact: `agent-tools:${clean}` },
    { id: focusNodeId(base, 'evals'), name: 'Evals', type: 'capability', state: focusedAgentEval?.ok ? 'built' : 'blank', synthetic: true, focusChild: true, artifact: `agent-evals:${clean}` },
    { id: focusNodeId(base, 'runtime'), name: 'Runtime', type: 'capability', state: agent.state || 'blank', synthetic: true, focusChild: true, artifact: `agent-runtime:${clean}` },
    { id: focusNodeId(base, 'chat'), name: 'Chat', type: 'ui', state: 'built', synthetic: true, focusChild: true, artifact: `agent-chat:${clean}` },
    { id: focusNodeId(base, 'generate'), name: 'Generate', type: 'capability', state: 'built', synthetic: true, focusChild: true, artifact: `agent-generate:${clean}` },
    { id: focusNodeId(base, 'verify'), name: 'Verify', type: 'capability', state: focusedAgentVerify?.ok ? 'built' : 'blank', synthetic: true, focusChild: true, artifact: `agent-verify:${clean}` },
  ];
}

function buildAgentFocusData() {
  const agent = getNodeById(focusedAgentId);
  if (!agent) return { nodes: [], links: [] };

  const ids = new Set([focusedAgentId]);
  for (const l of graphData.links || []) {
    const source = lid(l.source);
    const target = lid(l.target);
    if (source === focusedAgentId) ids.add(target);
    if (target === focusedAgentId) ids.add(source);
  }

  const baseNodes = graphData.nodes.filter(n => ids.has(n.id));
  const baseLinks = graphData.links.filter(l => ids.has(lid(l.source)) && ids.has(lid(l.target)));
  const devNodes = buildFocusDevNodes(agent);
  const devLinks = devNodes.map(n => ({ source: focusedAgentId, target: n.id, kind: 'focus' }));

  return {
    nodes: [...baseNodes, ...devNodes],
    links: [...baseLinks, ...devLinks],
  };
}
```

**Step 2: Modify `getVisibleData()`**

At the top of `getVisibleData()` add:

```js
if (viewMode === 'agent' && focusedAgentId) {
  return buildAgentFocusData();
}
```

Keep all existing project lens behavior below it.

**Step 3: Make synthetic nodes visibly different**

In `nodeCanvasObject`, before normal node drawing style, add:

```js
const isSynthetic = !!node.synthetic;
```

Then apply a dashed/soft border for synthetic nodes. Keep it subtle:

```js
if (isSynthetic) {
  ctx.setLineDash([4 / globalScale, 3 / globalScale]);
}
// existing stroke
ctx.setLineDash([]);
```

If the current drawing code has a single stroke call, wrap only that call. Do not rewrite the renderer.

**Step 4: Verify projection manually**

Run:

```bash
cd /opt/data/workspace/adk/live-agent-graph
curl -s http://127.0.0.1:8888/manifest?cluster=ops | python3 - <<'PY'
import json, sys
m=json.load(sys.stdin)
print(len(m.get('nodes', [])), len(m.get('links', [])))
print([n['id'] for n in m.get('nodes', []) if n.get('type') == 'agent'][:5])
PY
```

Expected: still returns the full manifest; focus projection is browser-only and should not change the endpoint.

**Step 5: Commit**

```bash
git add index.html
git commit -m "feat: derive focused agent graph view"
```

---

### Task 4: Add double-click enter/exit behavior with camera zoom

**Objective:** Double-clicking an agent enters focus mode; Back/Escape exits to project mode.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Check ForceGraph double-click API**

Use the library docs or current loaded API. If `onNodeDoubleClick` is available, use it. If not, implement a small click-time detector around `onNodeClick`.

Preferred:

```js
.onNodeDoubleClick(node => {
  if (node?.type === 'agent') enterAgentFocus(node.id);
})
```

Fallback detector:

```js
let lastClick = { id: null, ts: 0 };

function maybeDoubleClick(node) {
  const now = Date.now();
  const same = lastClick.id === node.id;
  const fast = now - lastClick.ts < 350;
  lastClick = { id: node.id, ts: now };
  return same && fast;
}
```

Then in `onNodeClick`:

```js
if (node.type === 'agent' && maybeDoubleClick(node)) {
  enterAgentFocus(node.id);
  return;
}
```

**Step 2: Add `enterAgentFocus` / `exitAgentFocus`**

```js
function enterAgentFocus(agentId) {
  if (!agentId || !agentId.startsWith('agent:')) return;
  viewMode = 'agent';
  focusedAgentId = agentId;
  lineageRoot = null;
  currentLens = 'padi';
  updateViewCrumb();
  renderLens();
  openAgentWorkbench(agentId);

  const n = getNodeById(agentId);
  if (n && Number.isFinite(n.x) && Number.isFinite(n.y)) {
    fg.centerAt(n.x, n.y, 650);
    fg.zoom(2.2, 650);
  }

  loadFocusedAgentData(agentId);
}

function exitAgentFocus() {
  viewMode = 'project';
  focusedAgentId = null;
  focusedAgentConfig = null;
  focusedAgentVerify = null;
  updateViewCrumb();
  renderLens();
  document.getElementById('inspect').classList.remove('open');
  fg.zoomToFit(650, 80);
}
```

**Step 3: Update Escape behavior**

In the keydown handler, after wire/inspect handling or before closing inspect, add:

```js
if (e.key === 'Escape' && viewMode === 'agent') {
  exitAgentFocus();
  return;
}
```

Order matters: if wire mode is active, Escape should cancel wiring first. If not wiring, exit focus.

**Step 4: Add a Focus button to agent inspect panel**

Inside `openInspect(node)` for agent nodes, add:

```js
html += `<button id="insp-focus" class="small-action">Focus this agent</button>`;
```

After `body.innerHTML = html`, attach:

```js
const focusBtn = document.getElementById('insp-focus');
if (focusBtn) focusBtn.addEventListener('click', () => enterAgentFocus(node.id));
```

**Step 5: Verify manually**

Use browser:

1. Load graph.
2. Double-click `ops` or `stability` node.
3. Confirm crumb changes to `Project: ops / Agent: ops`.
4. Confirm graph narrows and dev nodes appear.
5. Press Escape.
6. Confirm full project graph returns.

**Step 6: Commit**

```bash
git add index.html
git commit -m "feat: enter agent focus from graph nodes"
```

---

### Task 5: Build the agent workbench panel shell, with evals as a real tab

**Objective:** Replace the generic inspect panel with a focused agent-development panel in agent mode.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Add panel renderer**

Add below `openInspect`:

```js
function cleanAgentId(agentId) {
  return agentId.replace('agent:', '');
}

function openAgentWorkbench(agentId, section = 'config') {
  const agent = getNodeById(agentId);
  if (!agent) return;
  inspectedNode = agent;

  const panel = document.getElementById('inspect');
  const title = document.getElementById('inspect-title');
  const body = document.getElementById('inspect-body');
  const saveMsg = document.getElementById('inspect-save-msg');
  saveMsg.textContent = '';

  title.textContent = `${agent.name} workbench`;
  title.style.color = COLORS.agent || '#c9d1d9';

  body.innerHTML = `
    <div class="focus-tabs">
      <button data-section="config" class="focus-tab ${section === 'config' ? 'active' : ''}">Config</button>
      <button data-section="tools" class="focus-tab ${section === 'tools' ? 'active' : ''}">Tools</button>
      <button data-section="evals" class="focus-tab ${section === 'evals' ? 'active' : ''}">Evals</button>
      <button data-section="runtime" class="focus-tab ${section === 'runtime' ? 'active' : ''}">Runtime</button>
      <button data-section="run" class="focus-tab ${section === 'run' ? 'active' : ''}">Run</button>
    </div>
    <div id="focus-section"></div>
  `;

  panel.classList.add('open');
  document.querySelectorAll('.focus-tab').forEach(btn => {
    btn.addEventListener('click', () => renderFocusSection(agentId, btn.dataset.section));
  });
  renderFocusSection(agentId, section);
}
```

**Step 2: Add section renderer placeholder**

```js
function renderFocusSection(agentId, section) {
  const target = document.getElementById('focus-section');
  if (!target) return;
  const agent = getNodeById(agentId);
  const clean = cleanAgentId(agentId);

  if (section === 'config') {
    target.innerHTML = `
      <div class="field"><label>Agent ID</label><div class="ro">${esc(clean)}</div></div>
      <div class="field"><label>Model</label><div class="ro">${esc(agent?.model || '—')}</div></div>
      <div class="field"><label>Status</label><div class="ro">${esc(agent?.state || '—')}</div></div>
      <div class="field"><label>Config</label><pre class="ro json-block">${esc(JSON.stringify(focusedAgentConfig || {}, null, 2))}</pre></div>
    `;
  } else if (section === 'tools') {
    target.innerHTML = `<div class="field"><label>Tools</label><pre class="ro json-block">${esc(JSON.stringify(focusedAgentTools || [], null, 2))}</pre></div>`;
  } else if (section === 'evals') {
    target.innerHTML = `
      <div class="field"><label>Evalsets</label><pre class="ro json-block">${esc(JSON.stringify(focusedAgentEvalsets || [], null, 2))}</pre></div>
      <button id="focus-run-evals-btn" class="small-action">Run evals</button>
      <div class="field"><label>Last eval run</label><pre class="ro json-block">${esc(JSON.stringify(focusedAgentEval || {}, null, 2))}</pre></div>
    `;
    attachFocusEvalHandlers(agentId);
  } else if (section === 'runtime') {
    target.innerHTML = `<div class="field"><label>Runtime</label><div class="ro">Model, temperature, output tokens, safety, session/cache/runtime config. Wire this after the core config shape is verified.</div></div>`;
  } else if (section === 'run') {
    target.innerHTML = `
      <button id="focus-verify-btn" class="small-action">Verify</button>
      <button id="focus-generate-btn" class="small-action danger-light">Generate</button>
      <div class="field"><label>Last verify</label><pre class="ro json-block">${esc(JSON.stringify(focusedAgentVerify || {}, null, 2))}</pre></div>
    `;
    attachFocusRunHandlers(agentId);
  }
}
```

**Step 3: Add CSS for tabs/json blocks**

```css
.focus-tabs { display:flex; gap:6px; margin-bottom:10px; }
.focus-tab, .small-action {
  border: 1px solid #30363d;
  border-radius: 6px;
  background: #161b22;
  color: #c9d1d9;
  padding: 5px 8px;
  cursor: pointer;
}
.focus-tab.active { border-color:#58a6ff; color:#58a6ff; }
.small-action.danger-light { border-color: rgba(248,81,73,0.45); }
.json-block { white-space: pre-wrap; max-height: 220px; overflow:auto; }
```

**Step 4: Route focus synthetic nodes to tabs**

In `onNodeClick`, before `openInspect(node)`:

```js
if (node.synthetic && node.id.startsWith('focus:') && focusedAgentId) {
  const suffix = node.id.split(':').pop();
  const section = suffix === 'generate' || suffix === 'verify' || suffix === 'chat' ? 'run' : suffix;
  openAgentWorkbench(focusedAgentId, ['tools', 'evals', 'runtime'].includes(section) ? section : 'config');
  return;
}
```

Adjust mapping if the UX wants `chat` as its own tab later. Keep this first pass small.

**Step 5: Commit**

```bash
git add index.html
git commit -m "feat: add focused agent workbench shell"
```

---

### Task 6: Fetch focused agent config/tools/models/verify/eval data

**Objective:** Populate the workbench with real data from existing endpoints and the new eval read endpoint.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Add fetch helper**

```js
function loadFocusedAgentData(agentId) {
  const clean = cleanAgentId(agentId);

  Promise.allSettled([
    fetch(apiUrl(`/agent-config?agent_id=${encodeURIComponent(clean)}`), { headers: csrfHeaders() }).then(r => r.json()),
    fetch(apiUrl('/agent-tools'), { headers: csrfHeaders() }).then(r => r.json()),
    fetch(apiUrl('/agent-models'), { headers: csrfHeaders() }).then(r => r.json()),
    fetch(apiUrl(`/agent-verify?agent_id=${encodeURIComponent(clean)}`), { headers: csrfHeaders() }).then(r => r.json()),
    fetch(apiUrl(`/agent-evals?agent_id=${encodeURIComponent(clean)}`), { headers: csrfHeaders() }).then(r => r.json()),
  ]).then(results => {
    const [config, tools, models, verify, evals] = results;
    focusedAgentConfig = config.status === 'fulfilled' ? config.value : { ok: false, error: config.reason?.message || 'config failed' };
    focusedAgentTools = tools.status === 'fulfilled' ? (tools.value.tools || tools.value || []) : [];
    focusedAgentModels = models.status === 'fulfilled' ? (models.value.models || []) : [];
    focusedAgentVerify = verify.status === 'fulfilled' ? verify.value : { ok: false, error: verify.reason?.message || 'verify failed' };
    focusedAgentEvalsets = evals.status === 'fulfilled' ? (evals.value.evalsets || []) : [];
    focusedAgentEval = evals.status === 'fulfilled' ? (evals.value.last_run || null) : { ok: false, error: evals.reason?.message || 'evals failed' };

    if (viewMode === 'agent' && focusedAgentId === agentId) {
      openAgentWorkbench(agentId, 'config');
      renderLens();
    }
  });
}
```

**Step 2: Be careful with auth/proxy behavior**

The `apiUrl()` function rewrites requests through CRM `graph_embed` when inside CRM. Direct localhost requests will go straight to `serve.py`. The endpoints require `X-Graph-Secret`; in CRM, `graph_embed` injects it server-side. Direct browser to localhost may 403 for these endpoints unless running with secret available. This is expected.

If direct local browser testing gets 403, verify through CRM or use curl with the secret file:

```bash
SECRET=$(cat /opt/data/graph-server-secret)
curl -s -H "X-Graph-Secret: $SECRET" "http://127.0.0.1:8888/agent-config?agent_id=ops" | python3 -m json.tool
```

**Step 3: Improve workbench config section with actual fields**

If `focusedAgentConfig` returns `{ok, config}` or similar, render the actual nested config. Use defensive shape handling:

```js
const cfg = focusedAgentConfig?.config || focusedAgentConfig?.agent || focusedAgentConfig || {};
```

Do not assume one response shape without checking the endpoint output.

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: load focused agent workbench data"
```

---

### Task 7: Add safe config editing in the focus panel

**Objective:** Let the user edit instruction/model/tools for the focused agent via existing `/agent-config` POST, without broadening the write surface.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Render editable config fields**

In `renderFocusSection(agentId, 'config')`, replace the raw JSON-only view with fields:

```js
const cfg = focusedAgentConfig?.config || focusedAgentConfig?.agent || focusedAgentConfig || {};
const selectedTools = cfg.tools || [];
const instruction = cfg.instruction || '';
const model = cfg.model || agent?.model || '';
const description = cfg.description || agent?.name || clean;
```

Render:

```html
<div class="field"><label>Description</label><input id="focus-description" value="..."></div>
<div class="field"><label>Model</label><select id="focus-model">...</select></div>
<div class="field"><label>Instruction</label><textarea id="focus-instruction" rows="8">...</textarea></div>
<div class="field"><label>Tools</label><div id="focus-tool-list">...</div></div>
<button id="focus-save-config" class="small-action">Save config</button>
```

Use `focusedAgentModels` for model options and `focusedAgentTools` for checkboxes.

**Step 2: Add save handler**

```js
function attachFocusConfigHandlers(agentId) {
  const btn = document.getElementById('focus-save-config');
  if (!btn) return;
  btn.addEventListener('click', () => saveFocusedAgentConfig(agentId));
}

function saveFocusedAgentConfig(agentId) {
  const clean = cleanAgentId(agentId);
  const saveMsg = document.getElementById('inspect-save-msg');
  const tools = Array.from(document.querySelectorAll('.focus-tool-check:checked')).map(el => el.value);
  const body = JSON.stringify({
    agent_id: clean,
    description: document.getElementById('focus-description')?.value || clean,
    model: document.getElementById('focus-model')?.value || '',
    instruction: document.getElementById('focus-instruction')?.value || '',
    tools,
  });

  saveMsg.className = 'save-msg';
  saveMsg.textContent = 'Saving config...';

  fetch(apiUrl('/agent-config'), {
    method: 'POST',
    headers: { ...csrfHeaders(), 'Content-Type': 'application/json' },
    body,
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok === false || data.error) {
        saveMsg.className = 'save-msg err';
        saveMsg.textContent = data.error || 'Save failed';
        return;
      }
      saveMsg.className = 'save-msg ok';
      saveMsg.textContent = 'Config saved';
      loadFocusedAgentData(agentId);
    })
    .catch(err => {
      saveMsg.className = 'save-msg err';
      saveMsg.textContent = err.message;
    });
}
```

**Step 3: Guard against accidental blanking**

Before POST:

```js
if (!document.getElementById('focus-instruction')?.value.trim()) {
  saveMsg.className = 'save-msg err';
  saveMsg.textContent = 'Instruction cannot be blank';
  return;
}
```

This prevents the most likely destructive mistake.

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: edit agent config from focus view"
```

---

### Task 8: Wire Verify and Generate actions

**Objective:** Provide explicit, visible run actions from the focused workbench.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Add handler function**

```js
function attachFocusRunHandlers(agentId) {
  const verify = document.getElementById('focus-verify-btn');
  const generate = document.getElementById('focus-generate-btn');
  if (verify) verify.addEventListener('click', () => verifyFocusedAgent(agentId));
  if (generate) generate.addEventListener('click', () => generateFocusedAgent(agentId));
}
```

**Step 2: Add verify**

```js
function verifyFocusedAgent(agentId) {
  const clean = cleanAgentId(agentId);
  const saveMsg = document.getElementById('inspect-save-msg');
  saveMsg.className = 'save-msg';
  saveMsg.textContent = 'Verifying...';
  fetch(apiUrl(`/agent-verify?agent_id=${encodeURIComponent(clean)}`), { headers: csrfHeaders() })
    .then(r => r.json())
    .then(data => {
      focusedAgentVerify = data;
      saveMsg.className = data.ok === false ? 'save-msg err' : 'save-msg ok';
      saveMsg.textContent = data.ok === false ? (data.error || 'Verify failed') : 'Verify passed';
      renderFocusSection(agentId, 'run');
      renderLens();
    })
    .catch(err => { saveMsg.className = 'save-msg err'; saveMsg.textContent = err.message; });
}
```

**Step 3: Add generate with confirmation**

Generate is mutating. Require a confirm dialog:

```js
function generateFocusedAgent(agentId) {
  const clean = cleanAgentId(agentId);
  if (!confirm(`Generate agent ${clean}? This will write generated files from the current config.`)) return;

  const saveMsg = document.getElementById('inspect-save-msg');
  saveMsg.className = 'save-msg';
  saveMsg.textContent = 'Generating...';

  fetch(apiUrl('/agent-generate'), {
    method: 'POST',
    headers: { ...csrfHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: clean }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok === false || data.error) {
        saveMsg.className = 'save-msg err';
        saveMsg.textContent = data.error || 'Generate failed';
        return;
      }
      saveMsg.className = 'save-msg ok';
      saveMsg.textContent = 'Generated';
      verifyFocusedAgent(agentId);
    })
    .catch(err => { saveMsg.className = 'save-msg err'; saveMsg.textContent = err.message; });
}
```

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: run verify and generate from focus view"
```

---

### Task 8.5: Add minimal eval backend endpoints and run action

**Objective:** Make evals first-class enough for the focus view: list evalsets, run the selected/default evalset, persist the last result, and expose trajectory/final-response status. This is not the full eval authoring UI.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/serve.py`
- Create later as needed: `/opt/data/workspace/adk/live-agent-graph/evalsets/<agent_id>/smoke.evalset.json`
- Runtime output: `/opt/data/workspace/adk/live-agent-graph/.eval_runs/<agent_id>/last.json`

**Backend contract:**

`GET /agent-evals?agent_id=<id>` returns:

```json
{
  "ok": true,
  "agent_id": "ops",
  "evalsets": [
    {"id": "smoke", "path": "evalsets/ops/smoke.evalset.json", "cases": 3}
  ],
  "last_run": {
    "ok": true,
    "evalset_id": "smoke",
    "trajectory_pass": true,
    "final_response_pass": true,
    "score": 1.0,
    "ran_at": "2026-06-26T00:00:00Z"
  }
}
```

`POST /agent-eval-run` body:

```json
{"agent_id":"ops", "evalset_id":"smoke"}
```

returns the same `last_run` object, persisted to `.eval_runs/<agent_id>/last.json`.

**Important distinction:**

- `Verify` = import check + generated file existence + root agent sanity. Fast structural gate.
- `Eval` = behavior check. At minimum, trajectory/tool-use expectations and final response expectations. Slower quality gate.
- An agent can be `built` with verify only. It cannot be promoted to `live` if evals are missing, stale, or failing.

**Minimal implementation:**

If ADK CLI eval execution is not already wired, implement a conservative first pass:

1. List evalset JSON files under `evalsets/<agent_id>/*.evalset.json`.
2. For `POST /agent-eval-run`, if no real runner is available, return `{ok:false, error:"eval runner not wired"}` rather than fake a pass.
3. If `roundtrip_check.py` can safely run for this agent, use it as a temporary eval runner and label result `runner: "roundtrip_check"`.
4. Never fabricate trajectory or final-response scores.

**Step 1: Add filesystem helpers in `serve.py`**

```python
EVALSETS_DIR = SPIKE_DIR / "evalsets"
EVAL_RUNS_DIR = SPIKE_DIR / ".eval_runs"


def _safe_agent_id(agent_id: str) -> str:
    if not agent_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("invalid agent_id")
    return agent_id


def _list_agent_evalsets(agent_id: str) -> dict:
    agent_id = _safe_agent_id(agent_id)
    root = EVALSETS_DIR / agent_id
    evalsets = []
    if root.exists():
        for path in sorted(root.glob("*.evalset.json")):
            try:
                data = json.loads(path.read_text())
                cases = len(data.get("eval_cases", data.get("cases", [])))
            except Exception:
                cases = 0
            evalsets.append({"id": path.stem.replace(".evalset", ""), "path": str(path.relative_to(SPIKE_DIR)), "cases": cases})
    last_path = EVAL_RUNS_DIR / agent_id / "last.json"
    last_run = json.loads(last_path.read_text()) if last_path.exists() else None
    return {"ok": True, "agent_id": agent_id, "evalsets": evalsets, "last_run": last_run}
```

**Step 2: Add GET handler**

In `do_GET`, add `/agent-evals` to the secret-gated list and handler:

```python
elif path == "/agent-evals":
    qs = parse_qs(parsed.query)
    agent_id = qs.get("agent_id", [""])[0]
    if not agent_id:
        self._json_response(400, {"ok": False, "error": "agent_id required"})
        return
    try:
        self._json_response(200, _list_agent_evalsets(agent_id))
    except Exception as exc:
        self._json_response(400, {"ok": False, "error": str(exc)})
```

**Step 3: Add POST handler**

```python
def _run_agent_eval(agent_id: str, evalset_id: str | None = None) -> dict:
    agent_id = _safe_agent_id(agent_id)
    # First pass: no fake green. If a real runner is not implemented, fail honestly.
    result = {
        "ok": False,
        "agent_id": agent_id,
        "evalset_id": evalset_id or "default",
        "trajectory_pass": False,
        "final_response_pass": False,
        "score": 0.0,
        "error": "eval runner not wired",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out_dir = EVAL_RUNS_DIR / agent_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last.json").write_text(json.dumps(result, indent=2))
    return result
```

In `do_POST`:

```python
elif parsed.path == "/agent-eval-run":
    if not self._check_secret():
        self._json_response(403, {"ok": False, "error": "forbidden: X-Graph-Secret required"})
        return
    data = self._read_json_body()
    agent_id = data.get("agent_id", "")
    evalset_id = data.get("evalset_id")
    if not agent_id:
        self._json_response(400, {"ok": False, "error": "agent_id required"})
        return
    self._json_response(200, _run_agent_eval(agent_id, evalset_id))
```

Use the existing body-reading helper if one exists. Do not duplicate parsing if `serve.py` already has JSON helpers.

**Step 4: Add frontend handler**

```js
function attachFocusEvalHandlers(agentId) {
  const btn = document.getElementById('focus-run-evals-btn');
  if (!btn) return;
  btn.addEventListener('click', () => runFocusedAgentEvals(agentId));
}

function runFocusedAgentEvals(agentId) {
  const clean = cleanAgentId(agentId);
  const saveMsg = document.getElementById('inspect-save-msg');
  const evalsetId = focusedAgentEvalsets?.[0]?.id || 'default';
  saveMsg.className = 'save-msg';
  saveMsg.textContent = 'Running evals...';
  fetch(apiUrl('/agent-eval-run'), {
    method: 'POST',
    headers: { ...csrfHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: clean, evalset_id: evalsetId }),
  })
    .then(r => r.json())
    .then(data => {
      focusedAgentEval = data;
      saveMsg.className = data.ok ? 'save-msg ok' : 'save-msg err';
      saveMsg.textContent = data.ok ? 'Evals passed' : (data.error || 'Evals failed');
      renderFocusSection(agentId, 'evals');
      renderLens();
    })
    .catch(err => { saveMsg.className = 'save-msg err'; saveMsg.textContent = err.message; });
}
```

**Step 5: Verify**

```bash
cd /opt/data/workspace/adk/live-agent-graph
python3 -m py_compile serve.py
SECRET=$(cat /opt/data/graph-server-secret)
curl -s -H "X-Graph-Secret: $SECRET" "http://127.0.0.1:8888/agent-evals?agent_id=ops" | python3 -m json.tool
curl -s -X POST -H "X-Graph-Secret: $SECRET" -H "Content-Type: application/json" \
  -d '{"agent_id":"ops","evalset_id":"smoke"}' \
  "http://127.0.0.1:8888/agent-eval-run" | python3 -m json.tool
```

Expected first pass: list succeeds. Run may honestly return `ok:false` until a real ADK eval runner is wired. That is better than a fake green.

**Step 6: Restart if `serve.py` changed**

The graph-server runs under s6 in the Hermes container. Preferred restart:

```bash
docker exec hermes /command/s6-svc -r /run/service/graph-server
```

If that service is unavailable, use the local process restart documented elsewhere in this plan.

**Step 7: Commit**

```bash
git add serve.py index.html
git commit -m "feat: add focused agent eval contract"
```

---

### Task 9: Add focused layout positioning

**Objective:** Make focus view look intentional, not like a filtered project graph that happened by accident.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Extend `applyLayout(vd)`**

At the top of `applyLayout(vd)`, add:

```js
if (viewMode === 'agent' && focusedAgentId) {
  const center = vd.nodes.find(n => n.id === focusedAgentId);
  if (center) {
    center.fx = 0;
    center.fy = 0;
  }
  const dev = vd.nodes.filter(n => n.synthetic && n.focusChild);
  const radius = 220;
  dev.forEach((n, i) => {
    const angle = (-Math.PI / 2) + (i / Math.max(1, dev.length)) * Math.PI * 2;
    n.fx = Math.cos(angle) * radius;
    n.fy = Math.sin(angle) * radius;
  });
  const neighbors = vd.nodes.filter(n => !n.synthetic && n.id !== focusedAgentId);
  neighbors.forEach((n, i) => {
    n.fx = -340 + (i % 3) * 90;
    n.fy = -120 + Math.floor(i / 3) * 90;
  });
  return;
}
```

**Step 2: Ensure project view releases pins**

Existing PADI layout pins nodes. Before project lens applies, ensure focus pins do not leak. Add a helper:

```js
function clearFocusPins(nodes) {
  nodes.forEach(n => {
    if (!n.synthetic) {
      n.fx = undefined;
      n.fy = undefined;
    }
  });
}
```

Call it when exiting focus or before project layout applies.

**Step 3: Update info text**

In `renderLens()`, for focus mode:

```js
if (viewMode === 'agent' && focusedAgentId) {
  info.textContent = `${vd.nodes.length} focused nodes · agent: ${cleanAgentId(focusedAgentId)} · project: ${currentCluster || 'unknown'}`;
  return;
}
```

Do not return before applying graph data/layout; only alter the info text path.

**Step 4: Manual visual check**

Browser check:

- focused agent centered
- synthetic dev nodes form readable ring/cluster
- neighbors do not overlap agent label
- Back returns to PADI layout

**Step 5: Commit**

```bash
git add index.html
git commit -m "feat: lay out focused agent development nodes"
```

---

### Task 10: Add URL hash deep-linking without creating a new route

**Objective:** Allow refresh/share of focus state while preserving the one-page graph architecture.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Define hash format**

Use:

```text
#cluster=ops&agent=ops
```

Do not use `/agents/:agentId`.

**Step 2: Add helpers**

```js
function parseHashState() {
  const raw = window.location.hash.replace(/^#/, '');
  const params = new URLSearchParams(raw);
  return {
    cluster: params.get('cluster'),
    agent: params.get('agent'),
  };
}

function writeHashState() {
  const params = new URLSearchParams();
  if (currentCluster) params.set('cluster', currentCluster);
  if (viewMode === 'agent' && focusedAgentId) params.set('agent', cleanAgentId(focusedAgentId));
  const next = `#${params.toString()}`;
  if (window.location.hash !== next) history.replaceState(null, '', next);
}
```

**Step 3: Call write on cluster/focus changes**

Call `writeHashState()` in:

- successful cluster selection
- `enterAgentFocus`
- `exitAgentFocus`

**Step 4: Restore on load**

After clusters load and graph loads, if hash has `agent`, call:

```js
enterAgentFocus(`agent:${hash.agent}`);
```

Guard until `graphData` exists.

**Step 5: Verify**

Manual:

1. Focus ops.
2. Confirm hash becomes `#cluster=ops&agent=ops`.
3. Reload page.
4. Confirm it returns to ops focus view.
5. Back button removes agent from hash.

**Step 6: Commit**

```bash
git add index.html
git commit -m "feat: deep link focused graph state"
```

---

### Task 11: Add a small endpoint smoke test script

**Objective:** Give future agents one command to verify the backend contract before UI debugging.

**Files:**
- Create: `/opt/data/workspace/adk/live-agent-graph/scripts/smoke_focus_endpoints.py`

**Step 1: Create script**

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = os.environ.get("GRAPH_BASE", "http://127.0.0.1:8888")
SECRET = os.environ.get("GRAPH_SERVER_SECRET")
if not SECRET:
    secret_file = Path(os.environ.get("HERMES_HOME", "/opt/data")) / "graph-server-secret"
    if secret_file.exists():
        SECRET = secret_file.read_text().strip()


def get(path: str, secret: bool = False):
    headers = {}
    if secret:
        headers["X-Graph-Secret"] = SECRET or ""
    req = urllib.request.Request(BASE + path, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read())


def main() -> int:
    checks = [
        ("/pulse", False),
        ("/clusters", False),
        ("/manifest?cluster=ops", False),
        ("/agent-tools", True),
        ("/agent-models", True),
        ("/agent-config?agent_id=ops", True),
        ("/agent-verify?agent_id=ops", True),
        ("/agent-evals?agent_id=ops", True),
    ]
    failures = 0
    for path, needs_secret in checks:
        try:
            status, data = get(path, needs_secret)
            ok = status == 200 and not (isinstance(data, dict) and data.get("ok") is False)
            print(f"{path}: {status} {'OK' if ok else 'BAD'}")
            if not ok:
                print(json.dumps(data, indent=2)[:800])
                failures += 1
        except Exception as exc:
            print(f"{path}: ERROR {exc}")
            failures += 1
    return failures


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Run script**

```bash
cd /opt/data/workspace/adk/live-agent-graph
python3 scripts/smoke_focus_endpoints.py
```

Expected: all endpoints report `OK`. If `/agent-config?agent_id=ops` fails because the agent id differs in current cluster, run with another known agent id or update script to discover first agent from manifest.

**Step 3: Commit**

```bash
git add scripts/smoke_focus_endpoints.py
git commit -m "test: add focus endpoint smoke check"
```

---

### Task 12: End-to-end browser verification

**Objective:** Prove the complete UX path as Zach would use it.

**Files:**
- No code changes unless bugs are found.

**Step 1: Restart server only if `serve.py` changed**

If this plan only changed `index.html`, no restart should be required for static file changes served by `SimpleHTTPRequestHandler`. If `serve.py` changed, restart:

```bash
cd /opt/data/workspace/adk/live-agent-graph
pkill -f "serve.py 8888" || true
python3 serve.py 8888 &
```

Then verify:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8888/pulse
```

Expected: `200`.

**Step 2: Browser path**

Use browser tools or manual:

1. Open graph through the CRM route if testing production auth/proxy behavior.
2. Select `ops` cluster.
3. Double-click `ops` agent.
4. Confirm focus crumb and zoom.
5. Click Config synthetic node.
6. Confirm config fields populate.
7. Click Tools synthetic node.
8. Confirm tools list populates.
9. Click Verify synthetic node / Run tab.
10. Click Verify.
11. Confirm verify result displays and synthetic verify node state updates.
12. Click Evals synthetic node.
13. Confirm evalsets / last eval result display.
14. Click Run evals.
15. Confirm the UI shows a real pass/fail result. If the runner is not wired, it must say so plainly; no fake pass.
16. Press Escape or Back to project.
17. Confirm project graph returns.
18. Reload with hash and confirm focus restores.

**Step 3: Curl contract check**

```bash
cd /opt/data/workspace/adk/live-agent-graph
python3 scripts/smoke_focus_endpoints.py
```

**Step 4: Commit any bug fixes individually**

Do not squash every UI fix into one commit. Keep failures diagnosable.

---

## Files Likely to Change

Primary:

- `/opt/data/workspace/adk/live-agent-graph/index.html`
  - view mode state
  - breadcrumb
  - focus projection
  - double-click enter/exit
  - workbench panel
  - config/tools/models/verify/eval fetches
  - run actions
  - deep-link hash state

Optional / testing:

- `/opt/data/workspace/adk/live-agent-graph/tests/test_focus_projection.py`
- `/opt/data/workspace/adk/live-agent-graph/scripts/smoke_focus_endpoints.py`

Probably unchanged:

- `/opt/data/workspace/adk/live-agent-graph/serve.py`
  - Add minimal eval read/run endpoints. Otherwise keep changes small.
- `/opt/data/workspace/forsch_frontiers/`
  - No changes for this slice. Keep `/agents/:agentId` out of scope.

---

## Verification Checklist

Backend:

```bash
cd /opt/data/workspace/adk/live-agent-graph
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8888/pulse
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8888/clusters
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8888/manifest?cluster=ops"
python3 scripts/smoke_focus_endpoints.py
```

Frontend:

- Project graph still loads.
- Cluster tabs still work.
- PADI layout still default.
- Single click still opens inspect panel.
- Double click agent enters focus mode.
- Focus mode does not lose the selected project context.
- Back/Escape returns to project mode.
- Synthetic nodes do not persist to manifest.
- Generate requires explicit confirmation.
- Verify gives visible result.
- Evals give visible result, including honest failure if the runner is not wired.
- Verify and eval remain separate gates.
- Hash deep link restores focus state.

Regression:

- `/pulse` continues updating link colors.
- `Wire to...` still works in project view.
- Existing `save-agent` inspect edits still work.
- `Show shared` and `Dependencies` toggles do not break project view.

---

## Open Questions

1. **Evals scope:** For this slice, evals are first-class but minimal: list evalsets, show last result, run the default eval if a real runner exists, and fail honestly if not. Full eval authoring belongs in a later slice.
2. **Chat scope:** The existing Hubert sidecar is context-aware but not an agent chat runner. If Zach expects focused agent chat, wire it later through the Gradio spike or bridge route. Do not jam it into this slice.
3. **Source of truth:** Skill text says `save-agent` edits YAML, while other docs say CRM DocTypes are source of truth/fallback. Before broadening writes, inspect live endpoint behavior and decide whether the workbench should save to registry YAML, CRM, or both. For now, use the existing endpoint contract only.
4. **Route cleanup:** The separate `/agents/:agentId` Frappe page exists in `forsch_frontiers` HEAD. This plan intentionally ignores it. Later, remove or redirect it after Zach confirms the graph-focus path.

---

## Adversarial Review

### 1. This plan risks making `index.html` even more enormous

`index.html` is already about 50KB and conflict-prone. Adding focus mode, workbench, endpoint wiring, deep-linking, and layout in one file could make it harder to maintain.

**Mitigation:** Keep this slice minimal and grouped by comments. Do not add a JS build system yet. If the file becomes painful after this slice, the next refactor should extract `focus-mode.js`, but doing that before the feature lands is ceremony.

### 2. Synthetic nodes can become a lying map

The graph's rule is that code/manifest is canonical. Synthetic dev nodes are not source-of-truth artifacts. If rendered like real nodes, Zach may think they exist as actual graph components.

**Mitigation:** Mark every synthetic node with `synthetic: true`, dashed styling, and `artifact: agent-config:<id>` style labels. Never write them into `agent-graph-v2.json`; generate them only inside `getVisibleData()`.

### 3. Double-click may fight single-click inspect behavior

ForceGraph click and double-click interactions can be awkward. A double-click may open inspect first, then focus, creating flicker.

**Mitigation:** Prefer `onNodeDoubleClick` if the library supports it. If using manual detection, delay single-click inspect by ~200ms and cancel if a second click arrives. Only add that delay if flicker is actually visible.

### 4. Focus mode can accidentally break project lenses

`getVisibleData()` is the choke point for all lens behavior. A sloppy focus branch could break PADI, lineage, live, dependencies, or shared toggles.

**Mitigation:** Put the focus branch at the top and return early only when `viewMode === 'agent' && focusedAgentId`. Project mode should run the existing code untouched. Browser-regression project view after every task.

### 5. Layout pins can leak between modes

ForceGraph nodes are mutable. If focus mode sets `fx`/`fy`, those pins can persist after returning to project view.

**Mitigation:** Explicitly clear focus pins on exit and before project layout. Verify by entering focus, backing out, and seeing PADI bands recover.

### 6. Endpoint auth may pass locally but fail through CRM, or the reverse

Direct localhost calls need `X-Graph-Secret`; CRM proxy injects it. Browser code using `csrfHeaders()` may behave differently depending on route.

**Mitigation:** Test both direct curl with `X-Graph-Secret` and browser through CRM `graph_embed`. Do not treat localhost-only success as production success.

### 7. Generate is mutating and can overwrite real generated files

The focus workbench makes generate more discoverable, which also makes accidental writes more likely.

**Mitigation:** Require a confirmation dialog. Do not auto-generate on save. Keep verify separate. Report generated output visibly.

### 8. The Gradio spike is tempting but premature

Gradio gives a nicer chat/eval UI, but embedding it now adds routing/auth/UI complexity before the core graph zoom exists.

**Mitigation:** Leave Gradio out of this slice. Revisit once focus mode exists and the desired eval/chat surface is concrete.

### 9. Hash deep-links may conflict with CRM proxy URL encoding

The CRM `graph_embed` route already uses query params like `?path=...`; adding hash state is safe because hashes are browser-only, but restore logic must not assume normal path routing.

**Mitigation:** Use `window.location.hash` only. Do not add route paths. Do not use `/agents/:agentId`.

### 10. The plan still depends on ambiguous endpoint response shapes

`/agent-config`, `/agent-tools`, and `/agent-models` may not return the exact shapes assumed by the UI snippets.

**Mitigation:** First implementation step after UI shell should curl each endpoint and adapt defensively. The plan's snippets intentionally use `config || agent || root` style fallbacks, but the implementer must verify real output.

### 11. Eval greenwashing is worse than no eval surface

ADK evals are supposed to assess trajectory/tool use and final response. A fake "passed" because the endpoint ran would train everyone to ignore the gate.

**Mitigation:** The first eval endpoint may return `ok:false, error:"eval runner not wired"`. That is acceptable. It must not synthesize trajectory/final-response scores. Once a real ADK eval or roundtrip runner is attached, persist the real output and show the runner name.

### 12. Concierge/tool doctrine can get over-corrected

The focused view should not imply the front/concierge agent has zero direct tools. The better rule is: no junk drawer. Cross-cutting direct tools are allowed when they share a clear authority boundary.

**Mitigation:** The Tools tab should display direct tools and delegated/AgentTool capabilities separately once that data is available. Do not flatten all tools into one undifferentiated list.

---

## Recommended Execution Order

If time is short, implement only the spine:

1. Task 2: view state + breadcrumb.
2. Task 3: focus projection.
3. Task 4: double-click enter/exit.
4. Task 5: workbench shell.
5. Task 6: data fetch.
6. Task 8.5: minimal eval contract.

Leave config editing, generate, deep-linking, and smoke scripts for a second pass if the first pass feels unstable. Do not leave evals as a decorative placeholder.

Small, sharp, boring. The cat approves.
