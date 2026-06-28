# Full Session Handoff — 2026-06-26/27

> **Session:** Two consecutive sessions covering PADI shelf, live particles, auth cleanup, Hubert factory bot, and Shelby v1 foundation.
> **Snapshot timestamp:** 2026-06-27T15:00Z
> **Local mirror stale.** SSH to `root@100.120.21.13` to inspect live state.

---

## What Shipped

### 1. PADI Shelf — Repeatable Components
- **Tool, Interface, Router lanes** wired up with graph-native shelf controls (label + spawn + library pills)
- **Consolidated** into shared `graphNodeLibrary()` and `inspectGraphNode()` — 3 lanes use identical logic
- **Uniform pill width** (90px) with canvas clip-path text truncation
- **Dynamic shelf spacing** — pills don't overlap regardless of name length
- **Click-to-inspect** for all graph-node lanes
- **Commits:** `e650028`, `82e571e`, `86224aa`, `55b06be`, `a347b17`, `d97efef`

### 2. Live Particles
- **Custom green dots** travel along visible link segments (node edge → lane pin → node edge)
- **Node-ID matching** — matches by shared node ID, not exact edge key (handles collapsed intake nodes)
- **Collapsed intake mapping** — `chan:#team-stability` → `iface:discord`
- **Rendered in `onRenderFramePost`** — draws on top of links
- **Sleek 2px radius**
- **Commits:** `f0ad111`, `8422f58`, `0488bf2`, `8fa10f8`

### 3. Auth Cleanup
- **Dropped Frappe CSRF** — removed `csrfHeaders()`, `X-Frappe-CSRF-Token`, `window.frappe` checks
- **Graph secret is sole auth layer** — `X-Graph-Secret` header, `sessionStorage` persistence
- **Commit:** `7189f5a`

### 4. Hubert Factory Bot (Phase 1 — ADK)

| Task | Commit | Description |
|------|--------|-------------|
| T6 scaffold Hubert | `1182306` | agents/hubert/ scaffold |
| T7 orchestrator tools | `9a0519d`, `f5e2551` | graph_tools.py + wiring |
| T8 Agent·Logic specialist | `cbe4ba5` | specialist scaffold with 5 tools |
| T9 delegation | `0a466de` | route_to_agent_logic_specialist |
| T10 /chat integration | `fbe6cf3` | serve.py InMemoryRunner |
| T10 fix PYTHONPATH | `4597234` | added specialist + components paths |
| T10 fix API key | `188dc05` | set LITELLM_HERMES_KEY before import |

**Hubert verified end-to-end via SSH curl:**
- Identity: "I'm Hubert - the factory orchestrator. Ginger tabby, scarf, unfortunate amount of responsibility."
- Factory status: "7 agents, 41 nodes, 29 links"
- Specialist delegation: "shelby uses gpt-5.5, from the live agents.yaml entry"

### 5. Shelby v1 Foundation (4 Lanes)

| Lane | What | Tests | Status |
|------|------|-------|--------|
| L1: Data Store | SQLite schema, Pydantic models, FastAPI endpoints, migration script | 22/22 | ✅ |
| L2: Reminders | remindctl core, honest receipts, Apple sync adapter (skipped), LLM tool | 18/18 + 1 skip | ✅ |
| L3: Trends | Chore-trend engine (overdue, cadence, assignee split, summary) | 30/30 | ✅ |
| L4: Weather | Open-Meteo fetch, shelby_flags, caching, /api/weather | 22/22 | ✅ |

**Total Shelby tests:** 92 passing, 1 skipped

### 6. Graph Routing Fix
- **Committed:** `07e154d` — Worker now routes to port 8898 (was 8888)
- **NOT YET DEPLOYED** — Cloudflare OAuth token expired, needs `wrangler login` + deploy

---

## Live State

- **Live URL:** `graph.forschfrontiers.com` (currently 502 — see Known Issues)
- **Hetzner box:** `root@100.120.21.13`
- **live-agent-graph HEAD:** `07e154d` (local, not pushed)
- **ADK HEAD:** `188dc05` (live box)
- **Components HEAD:** `522dc8a` (live box)

## Known Issues

1. **Graph 502** — Cloudflare Worker routes to port 8888, but serve.py runs on 8898. Fix committed (`07e154d`) but needs wrangler deployment. Run `wrangler login` then `wrangler workers put graph-forschfrontiers --file cloudflare-worker.js` to deploy.

2. **Local mirror stale** — `/Users/zacharyforsch/Dev/adk-live-current/` not pulled from live box. All Shelby work, Hubert agent, and serve.py changes exist only on the live box.

3. **Cloudflare OAuth expired** — Token expired 2026-04-17. Need `wrangler login` to re-authenticate.

## Files Changed

### `live-agent-graph/index.html`
- PADI shelf: shared library, click-to-inspect, uniform pills, dynamic spacing
- Live particles: custom rendering on link segments, node-ID matching
- Auth: removed Frappe CSRF, simplified mutationHeaders

### `live-agent-graph/serve.py`
- `chat_with_hubert()` — replaced hermes subprocess with ADK InMemoryRunner
- Added PYTHONPATH for specialist + components

### `live-agent-graph/cloudflare-worker.js`
- Route graph traffic to port 8898 (was 8888)

### ADK workspace (Hetzner box)
- `agents/hubert/` — ADK orchestrator agent
- `agents/agent_logic_specialist/` — specialist with 5 tools
- `components/src/forsch/adk_components/shelby/` — store.py, models.py, api.py, remindctl.py, tools.py, apple_sync.py, trends.py, weather.py, weather_tool.py
- `components/tests/test_store.py`, `test_reminders.py`, `test_trends.py`, `test_weather.py`
- `data/shelby_schema.sql`, `data/migrate_jsonl_to_sqlite.py`

## Open Questions / Night 2

1. **Deploy graph routing fix** — `wrangler login` + deploy Worker
2. **Sync local mirror** — pull from live box
3. **Shelby agent update** — wire new SQLite store + tools into agent.py
4. **Browser E2E** — test Hubert chat through live URL (blocked by 502)
5. **Remaining specialists** — Tools·Data, Interfaces, Router
6. **CLI** — `hubert chat` CLI
7. **Apple Reminders sync** — pair device, unskip integration test

## Quick Commands

**Health check (live box):**
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && git log --oneline -3 && echo "---" && cd live-agent-graph && git log --oneline -3'
```

**Test Shelby (live box):**
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk/components && .venv/bin/python -m pytest tests/test_store.py tests/test_reminders.py tests/test_trends.py tests/test_weather.py -q'
```

**Test Hubert chat:**
```bash
curl -s --max-time 60 http://127.0.0.1:8898/chat -X POST -H "Content-Type: application/json" -H "X-Graph-Secret: localtestsecret" -d '{"message":"hello hubert","principal":"graph-ui"}'
```

**Deploy graph fix:**
```bash
wrangler login
cd /Users/zacharyforsch/Dev/live-agent-graph
wrangler workers put graph-forschfrontiers --file cloudflare-worker.js
```
