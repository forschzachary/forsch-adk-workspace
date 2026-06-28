# Final Session Handoff — 2026-06-27

> **Session end:** 2026-06-27T19:50Z
> **Status:** Graph UI live, chat routing in progress

---

## What's Working

### Graph UI
- `https://graph.forschfrontiers.com/` — serves HTML, all lanes visible
- PADI shelf: all 4 lanes with library pills (uniform 90px, dynamic spacing)
- Live particles: green dots on link segments
- Auth: graph secret only (Frappe CSRF dropped)

### Shelby v1 Foundation (4 lanes complete)
- **L1: Data Store** — SQLite at `/opt/data/shelby.db`, Pydantic models, FastAPI endpoints, migration script (22 tests)
- **L2: Reminders** — remindctl core, honest receipts, Apple sync adapter (skipped), LLM tool (18 tests + 1 skip)
- **L3: Trends** — Chore-trend engine (overdue, cadence, assignee split) (30 tests)
- **L4: Weather** — Open-Meteo fetch, shelby_flags, caching, /api/weather (22 tests)
- **Total: 92 tests passing, 1 skipped**

### Hubert Factory Bot (Phase 1)
- Hubert ADK agent with SOUL.md personality
- Agent·Logic specialist with 5 tools
- Specialist delegation working (tested via SSH curl)
- `chat_with_hubert()` in serve.py calls Hubert ADK agent directly

---

## What's Broken

### Chat Endpoint (1101/1003 errors)

**Root cause discovered:** A `graph-router` Worker (separate from `graph-forschfrontiers`) intercepts traffic for `graph.forschfrontiers.com`:
- `/chat/*` → `chat.forschfrontiers.com` (broken/dead service)
- Everything else → named tunnel → serve.py on port 8888

**What I tried:**
1. Updated `graph-router` to route /chat to serve.py directly → got 1003 (Worker can't reach origin)
2. Updated `graph-router` to not intercept /chat → tunnel handles everything
3. This should work but hasn't been verified yet

**Current state of graph-router Worker:**
```javascript
addEventListener("fetch", event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  return fetch(request);
}
```
This lets all traffic go through the tunnel. The tunnel routes everything to serve.py on port 8888.

**To verify:** Test `curl -s --max-time 120 "https://graph.forschfrontiers.com/chat" -X POST -H "Content-Type: application/json" -H "X-Graph-Secret: localtestsecret" -d '{"message":"hello hubert"}'`

### serve.py Port Binding
- Changed from `127.0.0.1` to `0.0.0.0` to accept external connections
- Currently running on port 8888 (not 8898 as originally configured)
- Firewall port 8888 opened

---

## Live State

- **Live URL:** `https://graph.forschfrontiers.com`
- **Hetzner box:** `root@100.120.21.13`
- **serve.py:** running on port 8888 (0.0.0.0)
- **graph-router Worker:** updated to pass-through (no /chat interception)
- **Named tunnel:** running (PID 407110), routes to port 8888

## Cloudflare Architecture

```
graph.forschfrontiers.com
  ↓
graph-router Worker (intercepts traffic)
  ↓ (currently: pass-through, lets tunnel handle everything)
Named tunnel → http://127.0.0.1:8888 → serve.py
```

The `graph-router` Worker was originally routing /chat to `chat.forschfrontiers.com`. Now it passes everything through.

## Quick Commands

**Test graph:**
```bash
curl -s "https://graph.forschfrontiers.com/" | head -c 100
```

**Test chat (if working):**
```bash
curl -s --max-time 120 "https://graph.forschfrontiers.com/chat" \
  -X POST -H "Content-Type: application/json" \
  -H "X-Graph-Secret: localtestsecret" \
  -d '{"message":"hello hubert"}'
```

**Test locally on box:**
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 \
  'curl -s --max-time 60 http://127.0.0.1:8888/chat -X POST \
  -H "Content-Type: application/json" \
  -H "X-Graph-Secret: localtestsecret" \
  -d "{\"message\":\"hello hubert\"}"'
```

**Check serve.py:**
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 \
  'ps aux | grep serve.py | grep -v grep'
```

**Check tunnel:**
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 \
  'ps aux | grep cloudflared | grep -v grep'
```

## Night 2 Priorities

1. **Verify chat works** — test the updated graph-router Worker
2. **If chat still broken** — consider Option 4 (named tunnel with config file) or Option 5 (fix chat.forschfrontiers.com)
3. **Wire Shelby agent** — connect new SQLite store + tools to agent.py
4. **Sync local mirror** — pull from live box
5. **Browser E2E** — test Hubert chat through live URL
