# Gradio Sidecar in Agent Graph View Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make the Gradio ADK sidecar feel native inside the Live Agent Graph focused-agent view, with Enter-to-send support, while keeping the integration small and reversible.

**Architecture:** Keep the Gradio app as the chat runtime/template owned by `forsch-adk-bridge`. The Live Agent Graph should not rebuild chat UI. It should open/embed the existing `/chat/` Gradio surface and pass enough context to select the current agent. Agent edits remain in the graph inspect/workbench panels; running/chatting happens in the embedded sidecar after save/generate/verify.

**Tech Stack:** Gradio 6.19, FastAPI bridge at `:8800`, Live Agent Graph static HTML/JS at `live-agent-graph/index.html`, Python `serve.py` proxy only if needed, Cloudflare/CRM proxy later.

---

## Current context

- Gradio sidecar already exists in `/opt/data/workspace/adk/bridge` and is mounted at `/chat/`.
- Sidecar uses real ADK runtime: `get_runtime()` -> selected agent -> `stream_agent_structured()`.
- Sidecar branch: `feat/gradio-sidecar-interface`, latest reviewed/fixed commit: `66e3402`.
- Sidecar is token-gated by `_TokenBridge` in `bridge/src/forsch/adk_bridge/http.py`.
- Live Agent Graph focused-agent mode already creates a synthetic `Chat` node with artifact `agent-chat:<agent_id>`.
- Existing graph `index.html` has an old tiny Hubert chat sidecar wired to graph server `/chat`; do not expand that. Replace or bypass it for ADK agent chat.
- User specifically asked: Enter should send message to the agent; integrate into agent-graph-view for edit-on-the-fly then run.

## Key product decision

Use **Gradio as an iframe sidecar** inside the graph view for v1.

Why:

- Fewest lines in graph UI.
- Reuses the working persistent chat template.
- Avoids duplicating Gradio chat controls in force-graph HTML.
- Keeps branding/theme modular in `sidecar_config.py`.
- Lets graph focus on edit/generate/verify, while bridge handles runtime chat.

Do **not** build a custom JS chat client against ADK bridge yet. That is more control, more code, and more auth/session sharp edges. Later, maybe. Not now.

---

## Slice 1: Enter sends in the Gradio sidecar

**Objective:** Make Enter send a message; Shift+Enter keeps newline. This belongs in the Gradio template, not the graph.

**Files:**

- Modify: `/opt/data/workspace/adk/bridge/src/forsch/adk_bridge/sidecar_config.py`
- Modify: `/opt/data/workspace/adk/bridge/src/forsch/adk_bridge/gradio_app.py`

**Approach:** Inject a tiny JS helper in Gradio that watches the prompt textarea and clicks the Run button on Enter. Keep it in config next to theme/copy.

**Implementation sketch:**

In `sidecar_config.py`, add:

```python
ENTER_TO_SEND_JS = r"""
<script>
(() => {
  function bindEnterToSend() {
    const prompt = document.querySelector('#ff-prompt textarea');
    const run = document.querySelector('#ff-run-btn button');
    if (!prompt || !run || prompt.dataset.ffEnterBound === '1') return;
    prompt.dataset.ffEnterBound = '1';
    prompt.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      run.click();
    });
  }
  const observer = new MutationObserver(bindEnterToSend);
  observer.observe(document.body, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', bindEnterToSend);
  bindEnterToSend();
})();
</script>
"""
```

In `gradio_app.py`, import and render it:

```python
from forsch.adk_bridge.sidecar_config import BRAND, ENTER_TO_SEND_JS, PROMPTS, build_css
...
gr.HTML(f"<style>{build_css()}</style>{ENTER_TO_SEND_JS}", visible=False)
```

**Verification:**

Run in `/opt/data/workspace/adk/bridge`:

```bash
python3 - <<'PY'
import ast
from pathlib import Path
for p in ['src/forsch/adk_bridge/gradio_app.py', 'src/forsch/adk_bridge/sidecar_config.py']:
    ast.parse(Path(p).read_text())
print('ast ok')
PY

docker exec adk-bridge sh -lc 'cd /workspace/bridge && python3 - <<"PY"
from forsch.adk_bridge.gradio_app import build_gradio_app
from forsch.adk_bridge.sidecar_config import ENTER_TO_SEND_JS
assert "ff-prompt" in ENTER_TO_SEND_JS
assert "shiftKey" in ENTER_TO_SEND_JS
assert type(build_gradio_app()).__name__ == "Blocks"
print("gradio enter helper ok")
PY'

docker restart adk-bridge
# wait until /healthz returns 200
```

Manual browser check:

- Open `/chat/?chat_token=<token>`.
- Type `hello` and press Enter.
- Expected: message sends.
- Type multi-line text using Shift+Enter.
- Expected: newline remains, no send.

**Commit:**

```bash
git add src/forsch/adk_bridge/gradio_app.py src/forsch/adk_bridge/sidecar_config.py
git commit -m "feat: add enter-to-send for gradio sidecar"
git push
```

---

## Slice 2: Add a minimal graph-side iframe sidecar container

**Objective:** In the Live Agent Graph, add a right-side or bottom-right panel that embeds the existing Gradio `/chat/` route.

**Files:**

- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Approach:** Add an iframe panel with one function: `openAdkSidecar(agentId)`. It should default to current focused agent when available. Use one configurable base URL constant. Do not touch `serve.py` yet.

**Important auth note:** For a quick demo, the iframe URL can use `?chat_token=<token>` if served directly from the bridge/tunnel. For production/CRM, do not expose the raw token in page source. Use a CRM/server proxy or cookie-priming route later.

**Implementation sketch:**

Add near the current sidecar CSS:

```css
#adk-sidecar {
  position: fixed;
  right: 0;
  top: 40px;
  width: min(520px, 42vw);
  height: calc(100vh - 40px);
  z-index: 30;
  background: #0d1117;
  border-left: 1px solid #30363d;
  transform: translateX(100%);
  transition: transform 0.2s ease;
  display: flex;
  flex-direction: column;
}
#adk-sidecar.open { transform: translateX(0); }
#adk-sidecar header {
  height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border-bottom: 1px solid #30363d;
  color: #c9d1d9;
  font-size: 12px;
}
#adk-sidecar iframe { flex: 1; border: 0; background: #f7f3ea; }
#adk-sidecar .close-btn { margin-left: auto; background: none; border: 0; color: #8b949e; cursor: pointer; }
```

Add HTML near existing sidecars:

```html
<div id="adk-sidecar">
  <header>
    <span id="adk-sidecar-title">ADK Sidecar</span>
    <button class="close-btn" id="adk-sidecar-close">&times;</button>
  </header>
  <iframe id="adk-sidecar-frame" title="ADK Sidecar"></iframe>
</div>
```

Add JS constants and helpers:

```js
const ADK_CHAT_BASE = window.ADK_CHAT_BASE || 'http://127.0.0.1:8800/chat/';
const ADK_CHAT_TOKEN = window.ADK_CHAT_TOKEN || '';

function cleanAgentId(agentId) {
  return (agentId || '').replace(/^agent:/, '');
}

function adkChatUrl(agentId) {
  const url = new URL(ADK_CHAT_BASE, window.location.href);
  if (ADK_CHAT_TOKEN) url.searchParams.set('chat_token', ADK_CHAT_TOKEN);
  const clean = cleanAgentId(agentId || focusedAgentId || '');
  if (clean) url.searchParams.set('agent', clean);
  return url.toString();
}

function openAdkSidecar(agentId) {
  const clean = cleanAgentId(agentId || focusedAgentId || '');
  document.getElementById('adk-sidecar-title').textContent = clean ? `ADK Sidecar · ${clean}` : 'ADK Sidecar';
  document.getElementById('adk-sidecar-frame').src = adkChatUrl(clean);
  document.getElementById('adk-sidecar').classList.add('open');
}

document.getElementById('adk-sidecar-close').addEventListener('click', () => {
  document.getElementById('adk-sidecar').classList.remove('open');
});
```

**Caveat:** `new URL('http://127.0.0.1:8800/chat/', window.location.href)` in a browser on Zach's Mac points to Zach's machine, not the cloud box. For local graph demos, use the trycloudflare URL or CRM-proxied URL as `ADK_CHAT_BASE`. For production, this must be a same-origin CRM proxy path.

**Verification:**

- Open graph page.
- Call `openAdkSidecar('agent:ops')` from browser console.
- Expected: sidecar slides open and iframe loads Gradio shell.
- Close button hides it.
- No graph data changes.

**Commit:**

```bash
git add index.html
git commit -m "feat: add ADK sidecar iframe shell"
```

---

## Slice 3: Make the Chat synthetic node open the iframe

**Objective:** When the user is in agent focus mode and clicks the `Chat` synthetic node, open the Gradio sidecar for that focused agent.

**Files:**

- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Approach:** Reuse existing artifact naming: synthetic chat nodes have `artifact: agent-chat:<agent_id>`. Hook node click handling; if artifact starts with `agent-chat:`, open sidecar.

**Implementation sketch:**

Find the node click handler. Add the smallest branch before generic inspect handling:

```js
function handleNodeClick(node) {
  if (node?.artifact?.startsWith('agent-chat:')) {
    openAdkSidecar(node.artifact.replace('agent-chat:', ''));
    return;
  }
  // existing behavior...
}
```

If there is no named `handleNodeClick`, add the condition inside the existing `Graph.onNodeClick(...)` callback.

**Verification:**

- Open graph.
- Double-click/focus an agent.
- Click the synthetic `Chat` child node.
- Expected: ADK sidecar opens with title showing that agent.
- Click non-chat nodes.
- Expected: existing inspect/workbench behavior unchanged.

**Commit:**

```bash
git add index.html
git commit -m "feat: open ADK sidecar from chat node"
```

---

## Slice 4: Pass initial agent selection into Gradio

**Objective:** If the iframe URL includes `?agent=ops`, the Gradio sidecar should default to that agent.

**Files:**

- Modify: `/opt/data/workspace/adk/bridge/src/forsch/adk_bridge/gradio_app.py`

**Approach:** Use a tiny request-aware default if Gradio exposes request context cleanly. If not clean, skip this slice and rely on manual dropdown selection. Do not overbuild.

**Likely simple path:** Gradio event callbacks can accept `gr.Request`, but initial component values are built at app startup, not per request. That makes true URL-driven initial dropdown tricky inside plain Blocks. Lazy answer: do not force it in v1. Instead, title the iframe by agent and let user pick agent in dropdown.

**Alternative if needed later:** create a small `/chat-select/<agent>` wrapper route in FastAPI that sets a cookie `ff_agent=<agent>` before redirecting to `/chat/?chat_token=...`, then read cookie through a custom startup JS. This is more code. Do not do it until manual dropdown annoys Zach twice.

**Recommendation:** Skip for now.

---

## Slice 5: Edit -> save/generate/verify -> run flow in graph

**Objective:** Make the focused-agent workbench flow obvious: edit config, save, generate, verify, then open chat.

**Files:**

- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Approach:** Add a `Run in Sidecar` button to the existing agent focus workbench footer/header. It should be disabled or warn if verify state is failing/stale. It should call `openAdkSidecar(focusedAgentId)`.

**Implementation sketch:**

Where focus workbench buttons render, add:

```html
<button class="small-action" onclick="openAdkSidecar(focusedAgentId)">Run in sidecar</button>
```

Better JS-safe version if rendering strings:

```js
html += `<button class="small-action" id="run-sidecar-btn">Run in sidecar</button>`;
...
document.getElementById('run-sidecar-btn')?.addEventListener('click', () => openAdkSidecar(focusedAgentId));
```

**Guard:**

If `focusedAgentVerify?.ok === false`, show status text:

```js
setFocusStatus('verify is failing; chat may still run stale code', 'warn');
```

Do not block the button yet. Blocking requires stronger deploy-state semantics than we have today.

**Verification:**

- Focus an agent.
- Edit a config field.
- Save.
- Generate.
- Verify.
- Click Run in sidecar.
- Expected: sidecar opens, no page navigation.

**Commit:**

```bash
git add index.html
git commit -m "feat: add run-in-sidecar action to agent focus"
```

---

## Slice 6: Production routing/auth plan

**Objective:** Avoid hardcoding demo tokens or trycloudflare URLs into the graph.

**Files likely later:**

- `/opt/data/workspace/forsch_frontiers/forsch_frontiers/api/cockpit.py`
- `/opt/data/workspace/adk/live-agent-graph/index.html`
- maybe `/opt/data/workspace/adk/bridge/src/forsch/adk_bridge/http.py`

**Recommended production shape:**

1. CRM page serves graph via existing `graph_embed` proxy.
2. Graph opens iframe to a CRM same-origin proxy path, not raw `:8800`.
3. CRM proxy injects/sets `CHAT_TOKEN` server-side, never exposing it in `index.html`.
4. Bridge keeps `_TokenBridge` unchanged.

**Do not do this in the first implementation slice.** First prove the iframe sidecar flow with a demo URL. Then harden.

---

## Risks and tradeoffs

### Iframe is less elegant than native JS chat

True. It is also 10x less code and already works. Use it until it actually blocks the workflow.

### URL token exposure in demo mode

Acceptable only for demo. Not acceptable for CRM production. Production needs server-side token injection/proxy.

### Gradio URL-driven agent selection is awkward

Gradio Blocks initial values are app-level, not per-request. Do not fight it yet. Manual dropdown is fine for v1; graph title can still show intended agent.

### Enter-to-send JS may be brittle against Gradio DOM changes

Small and isolated. If Gradio changes DOM, the failure mode is harmless: Enter inserts newline again. Keep the helper in `sidecar_config.py` so it is easy to adjust.

### Existing old Hubert sidecar in graph may confuse users

Yes. Once ADK sidecar is working, either rename old button to `Hubert cockpit chat` or remove it from the main panel. Do not keep two generic “chat” buttons.

---

## Final recommended build order

1. Add Enter-to-send in `forsch-adk-bridge`.
2. Add graph iframe shell with configurable `ADK_CHAT_BASE`.
3. Wire synthetic `Chat` focus node to open iframe.
4. Add `Run in sidecar` action in focused-agent workbench.
5. Demo with trycloudflare URL/token.
6. Only after that, design CRM same-origin proxy for production auth.

This keeps the first real integration tiny: mostly one iframe and one click handler. Lazy, as requested. Annoyingly rare.
