# Handoff: Agent Focus Zoom — Implementation Complete

**Date:** 2026-06-26
**Author:** Hubert
**Branch:** `main` (3 commits ahead of origin)
**Repo:** `/opt/data/workspace/adk/spikes/live-agent-graph/`

---

## What was built

A focus mode for the Live Agent Graph that lets you double-click an agent node to zoom into an agent-development surface without leaving the graph page. Two altitudes: project view (existing) and agent focus view (new).

### What changed

| File | Lines | What |
|------|-------|------|
| `index.html` | +580 | Focus mode: view state, breadcrumb, workbench panel (5 tabs), synthetic dev nodes, star layout, double-click detector, hash deep-linking, config editing, verify/generate/eval actions |
| `serve.py` | +117 | `/agent-evals` GET, `/agent-eval-run` POST, `_safe_agent_id`, `_list_agent_evalsets`, `_run_agent_eval` |
| `tests/test_focus_projection.py` | +66 | 4 tests pinning projection rules (neighborhood, synthetic IDs, cross-agent isolation) |
| `scripts/smoke_focus_endpoints.py` | +55 | 8-endpoint smoke test for the focus-mode backend contract |

### Commits

```
43ad4e3 fix: remove stray brace from corruption fix, replace onNodeDoubleClick with click detector
be96b19 feat: agent focus zoom — view mode, projection, workbench, eval endpoints
8424e15 test: pin agent focus projection rules
```

---

## How it works

### Entering focus mode

- **Double-click** an agent node (350ms click-time detector — force-graph 1.43.5 doesn't have `onNodeDoubleClick`)
- Or click the **"Focus this agent"** button in the inspect panel

### Focus view

- **Breadcrumb** top-left: `Project: ops / Agent: ops` + `Back to project` button
- **Graph narrows** to the focused agent + its direct neighbors + 7 synthetic dev nodes arranged in a star
- **Synthetic nodes** are visually distinct (dashed outline, slightly dimmed): Config, Tools, Evals, Runtime, Chat, Generate, Verify
- Clicking a synthetic node switches the workbench tab

### Workbench panel (replaces inspect panel in focus mode)

| Tab | What it shows | What it does |
|-----|---------------|--------------|
| **Config** | Agent ID, description, model dropdown (from LiteLLM), instruction textarea, tool checkboxes | Save via `/agent-config` POST. Blank-instruction guard. |
| **Tools** | Tool list from `/agent-tools` | Read-only display |
| **Evals** | Evalset list, last run result, eval status badge | Run evals via `/agent-eval-run` POST |
| **Runtime** | Model, state, role | Read-only (wire more after core shape verified) |
| **Run** | Verify status, verify/generate buttons | Verify via `/agent-verify` GET, Generate via `/agent-generate` POST (confirm dialog required) |

### Exiting focus mode

- **Escape** key
- **Back to project** button in breadcrumb
- Restores full PADI project graph

### URL deep-linking

Hash format: `#cluster=ops&agent=ops`

- Written on every cluster selection, focus enter, focus exit
- Restored on page load (waits for graph data, then enters focus if agent exists)

### Eval backend contract

```
GET  /agent-evals?agent_id=<id>   → {ok, agent_id, evalsets[], last_run}
POST /agent-eval-run              → {ok, agent_id, evalset_id, trajectory_pass, final_response_pass, score, error, ran_at}
```

**Honest fail:** No eval runner is wired yet. `/agent-eval-run` returns `ok: false` with `"eval runner not wired"`. No fake green. A passing eval will later require both `trajectory_pass` and `final_response_pass`.

---

## What was fixed along the way

### Pre-existing file corruption

`index.html` had a truncation marker (`... [OUTPUT TRUNCATED ...]`) embedded since commit `f3491e7`. The `renderTabs`, `selectCluster`, and most of `loadGraph` were missing, replaced by the marker. Restored from `7622cd1` (last clean commit). Also removed a stray `}` that the repair left behind.

### force-graph API mismatch

`onNodeDoubleClick` doesn't exist in force-graph 1.43.5. Replaced with a `_maybeDoubleClick` click-time detector (350ms threshold). Works the same way from the user's perspective.

---

## Verification checklist

**Backend (all pass):**
```bash
python3 scripts/smoke_focus_endpoints.py
# /pulse: 200 OK
# /clusters: 200 OK
# /manifest?cluster=ops: 200 OK
# /agent-tools: 200 OK
# /agent-models: 200 OK
# /agent-config?agent_id=ops: 200 OK
# /agent-verify?agent_id=ops: 200 OK
# /agent-evals?agent_id=ops: 200 OK
```

**Frontend (verified in browser):**
- [x] Project graph loads with PADI swim lanes
- [x] Cluster tabs work
- [x] Double-click agent enters focus mode
- [x] Breadcrumb shows project + agent
- [x] Graph narrows to agent neighborhood + synthetic nodes
- [x] Workbench tabs switch correctly
- [x] Config tab shows agent fields
- [x] Evals tab shows "No runs" (honest)
- [x] Run tab shows Verify + Generate buttons
- [x] Escape / Back button restores project view
- [x] PADI layout recovers after exiting focus

**Not yet verifiable in browser (requires CRM proxy):**
- [ ] Verify endpoint returns 200 (needs X-Graph-Secret, injected by CRM proxy)
- [ ] Config save works end-to-end
- [ ] Generate works end-to-end
- [ ] Evals run and return real results (runner not wired yet)

---

## What's next

1. **Eval runner:** Wire `roundtrip_check.py` or ADK eval as a real runner. The endpoint contract is shaped and waiting.
2. **Promotion gate:** Once evals pass, promotion to `live` should require both verify.ok and eval.ok. The data shape supports this.
3. **Chat in focus mode:** The existing Hubert sidecar works but isn't context-aware to the focused agent. Wire agent-specific context.
4. **Agent Builder Desk module:** The CRM's Agent Builder page (`/agent-builder`) exists separately. This graph-focus path replaces it. Remove or redirect after Zach confirms.
5. **Push to origin:** 3 commits ahead of origin/main. Push when review is done.

---

## Files to review

| File | What to look at |
|------|-----------------|
| `index.html` | Lines 312-322: double-click detector. Lines 490-545: enter/exit functions. Lines 547-587: focus projection. Lines 622-655: star layout. Lines 1124-1255: workbench panel. Lines 1450-1605: data fetch, config save, verify/generate/eval handlers. Lines 1634-1655: hash deep-linking. Lines 1714-1736: hash restore on init. |
| `serve.py` | Lines 875-925: eval helpers (`_safe_agent_id`, `_list_agent_evalsets`, `_run_agent_eval`). Lines 943-945: mutating list updated. Lines 998-1008: `/agent-evals` GET handler. Lines 1229-1242: `/agent-eval-run` POST handler. |
| `tests/test_focus_projection.py` | 4 tests: neighborhood with mutated links, neighborhood exclusion, synthetic ID namespacing, cross-agent isolation. |
| `scripts/smoke_focus_endpoints.py` | 8-endpoint smoke test. Reads secret from `GRAPH_SERVER_SECRET` env or `$HERMES_HOME/graph-server-secret`. |
