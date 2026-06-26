# Graph Cleanup + Unified Sidecar Widget Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Clean up the live-agent-graph repo, then build a single unified sidecar widget with two persistent chat tabs — ADK Agent Chat (Gradio iframe) and Hubert (graph-server `/chat`). Both sessions persist across tab switches. Add "Agent Builder" to the CRM dropdown so it's reachable from anywhere in the CRM.

**Architecture:** One floating widget, bottom-right, two tabs. Tab 1: Gradio sidecar iframe for the selected ADK agent. Tab 2: JS chat UI hitting the graph server `/chat` endpoint (Hubert). Both maintain session state: Gradio via its own session management, Hubert via `session_id` round-trips to `hermes chat --resume`. Flipping tabs toggles visibility, never destroys state. The graph owns edit/generate/verify. The sidecar owns run/chat/vibe-code.

**Tech Stack:** Plain JS in `index.html`, Python stdlib HTTP in `serve.py`, Gradio 6.19 sidecar at `:8800/chat/`, graph server `/chat` endpoint (hermes chat subprocess), Frappe Web Page for CRM route.

---

## Task 1: Reset corrupted graph JSON and commit pending changes

**Objective:** Restore `agent-graph-v2.json` to the clean committed version (7 real agents, 41 nodes, 29 links, cluster=ops) and commit the legitimate index.html + serve.py changes that are currently uncommitted.

**Files:**
- Reset: `agent-graph-v2.json` (git checkout HEAD)
- Commit: `index.html` (+105 lines: graph secret injection, model node filtering, tools reorganization)
- Commit: `serve.py` (+8 lines: `/graph-secret` endpoint, relaxed secret gate)

**Steps:**

```bash
cd /opt/data/workspace/adk/live-agent-graph
git checkout HEAD -- agent-graph-v2.json
git add index.html serve.py
git commit -m "feat(graph): graph secret injection, model node filtering, tools reorganization"
git push origin main
```

**Verification:**
- `python3 -c "import json; d=json.load(open('agent-graph-v2.json')); print(len(d['nodes']), len(d['links']), d.get('cluster'))"` → `41 29 ops`
- `curl -s http://127.0.0.1:8888/pulse | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['live_nodes']))"` → `14` (no wow-guild junk in pulse)
- `git status` → clean working tree

---

## Task 2: Enter-to-send in the Gradio sidecar

**Objective:** Make Enter send the message in the Gradio sidecar prompt textarea. Shift+Enter keeps newline. IME composition ignored.

**Files:**
- Modify: `/opt/data/workspace/adk/bridge/src/forsch/adk_bridge/sidecar_config.py`
- Modify: `/opt/data/workspace/adk/bridge/src/forsch/adk_bridge/gradio_app.py`

**Step 1: Add ENTER_TO_SEND_JS to sidecar_config.py**

Add after the `build_css()` function:

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

**Step 2: Wire it into gradio_app.py**

Import `ENTER_TO_SEND_JS` alongside existing imports:

```python
from forsch.adk_bridge.sidecar_config import BRAND, ENTER_TO_SEND_JS, PROMPTS, build_css
```

Where the CSS HTML block is rendered (look for `gr.HTML(f"<style>{build_css()}</style>...")`), append the script:

```python
gr.HTML(f"<style>{build_css()}</style>{ENTER_TO_SEND_JS}", visible=False)
```

**Step 3: Verify**

```bash
cd /opt/data/workspace/adk/bridge
python3 -c "
import ast
from pathlib import Path
for p in ['src/forsch/adk_bridge/gradio_app.py', 'src/forsch/adk_bridge/sidecar_config.py']:
    ast.parse(Path(p).read_text())
print('ast ok')
"
docker exec adk-bridge sh -lc 'cd /workspace/bridge && python3 -c "
from forsch.adk_bridge.gradio_app import build_gradio_app
from forsch.adk_bridge.sidecar_config import ENTER_TO_SEND_JS
assert \"ff-prompt\" in ENTER_TO_SEND_JS
assert \"shiftKey\" in ENTER_TO_SEND_JS
assert type(build_gradio_app()).__name__ == \"Blocks\"
print(\"gradio enter helper ok\")
"'
docker restart adk-bridge
```

Manual browser check: open `/chat/?chat_token=<token>`, type `hello` + Enter → sends. Shift+Enter → newline.

**Commit:**
```bash
git add src/forsch/adk_bridge/gradio_app.py src/forsch/adk_bridge/sidecar_config.py
git commit -m "feat: enter-to-send for gradio sidecar"
git push
```

---

## Task 3: Unified sidecar widget shell with two tabs

**Objective:** Add a single floating bottom-right chat widget to `index.html` with two tabs: "Agent" (Gradio iframe) and "Hubert" (JS chat UI). Both sessions persist across tab switches. The widget slides up on open, slides down on close.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Design:**
- Floating widget, bottom-right corner, ~440px wide, ~560px tall
- Header bar: tab buttons ("Agent" | "Hubert") + agent name label + close button
- Tab 1 (Agent): Gradio sidecar iframe, `src` set by `openAdkSidecar(agentId)`
- Tab 2 (Hubert): JS chat UI — message list + input + send button, hits `/chat` endpoint
- Both panels stay in DOM always. Toggling tabs just shows/hides via `display: none/block`
- Session state: Gradio iframe keeps its own session. Hubert panel stores `sessionId` in JS and passes it with every `/chat` request
- Escape closes the widget. Opening the widget does not close the other panels (inspect, workbench)
- Widget z-index: 100 (above graph, below modals)

**CSS to add:**

```css
/* ── Unified sidecar widget ── */
#sidecar-widget {
  position: fixed;
  right: 20px;
  bottom: 20px;
  width: 440px;
  height: 560px;
  z-index: 100;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  display: flex;
  flex-direction: column;
  transform: translateY(calc(100% + 40px));
  opacity: 0;
  transition: transform 0.25s ease, opacity 0.2s ease;
  pointer-events: none;
  overflow: hidden;
}
#sidecar-widget.open {
  transform: translateY(0);
  opacity: 1;
  pointer-events: auto;
}
#sidecar-header {
  height: 42px;
  display: flex;
  align-items: center;
  padding: 0 10px 0 6px;
  border-bottom: 1px solid #30363d;
  background: #161b22;
  border-radius: 12px 12px 0 0;
  flex-shrink: 0;
  gap: 2px;
}
.sidecar-tab {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #8b949e;
  background: none;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.sidecar-tab:hover { color: #c9d1d9; }
.sidecar-tab.active {
  color: #e6edf3;
  background: #21262d;
  border-color: #30363d;
}
#sidecar-agent-label {
  font-size: 11px;
  color: #8b949e;
  margin-left: 6px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
#sidecar-close {
  background: none;
  border: 0;
  color: #8b949e;
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
}
#sidecar-close:hover { color: #c9d1d9; }

/* Tab panels */
.sidecar-panel {
  flex: 1;
  display: none;
  flex-direction: column;
  overflow: hidden;
}
.sidecar-panel.active { display: flex; }

/* Agent tab: iframe fills the space */
#sidecar-agent-frame {
  flex: 1;
  border: 0;
  background: #f7f3ea;
}

/* Hubert tab: message list + input */
#hubert-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hubert-msg {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-wrap: break-word;
}
.hubert-msg.user {
  align-self: flex-end;
  background: #21262d;
  color: #e6edf3;
}
.hubert-msg.assistant {
  align-self: flex-start;
  background: #161b22;
  color: #c9d1d9;
  border: 1px solid #30363d;
}
.hubert-msg.system {
  align-self: center;
  color: #8b949e;
  font-size: 11px;
  font-style: italic;
}
#hubert-input-row {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid #30363d;
  background: #0d1117;
}
#hubert-input {
  flex: 1;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  color: #e6edf3;
  font-size: 13px;
  padding: 8px 10px;
  resize: none;
  min-height: 20px;
  max-height: 100px;
  font-family: inherit;
}
#hubert-input:focus { border-color: #58a6ff; outline: none; }
#hubert-send {
  background: #238636;
  border: 1px solid #2ea043;
  border-radius: 8px;
  color: #fff;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
#hubert-send:hover { background: #2ea043; }
#hubert-send:disabled { opacity: 0.5; cursor: not-allowed; }
```

**HTML to add:**

```html
<div id="sidecar-widget">
  <div id="sidecar-header">
    <button class="sidecar-tab active" data-tab="agent">Agent</button>
    <button class="sidecar-tab" data-tab="hubert">Hubert</button>
    <span id="sidecar-agent-label"></span>
    <button id="sidecar-close">&times;</button>
  </div>
  <div id="sidecar-panel-agent" class="sidecar-panel active">
    <iframe id="sidecar-agent-frame" title="Agent Chat"></iframe>
  </div>
  <div id="sidecar-panel-hubert" class="sidecar-panel">
    <div id="hubert-messages">
      <div class="hubert-msg system">Connected to Hubert. Ask anything about the graph, agents, or what to build next.</div>
    </div>
    <div id="hubert-input-row">
      <textarea id="hubert-input" placeholder="Describe what you want..." rows="1"></textarea>
      <button id="hubert-send">Send</button>
    </div>
  </div>
</div>
```

**JS to add:**

```js
// ── Sidecar widget state ──
let sidecarOpen = false;
let sidecarTab = 'agent';        // 'agent' | 'hubert'
let sidecarAgentId = null;
let hubertSessionId = null;      // persisted across tab switches
let hubertMessages = [];         // {role, text}[]
let hubertSending = false;

const ADK_CHAT_BASE = window.ADK_CHAT_BASE || 'http://127.0.0.1:8800/chat/';

// ── Tab switching ──
document.querySelectorAll('.sidecar-tab').forEach(btn => {
  btn.addEventListener('click', () => switchSidecarTab(btn.dataset.tab));
});

function switchSidecarTab(tab) {
  sidecarTab = tab;
  document.querySelectorAll('.sidecar-tab').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab));
  document.getElementById('sidecar-panel-agent').classList.toggle('active', tab === 'agent');
  document.getElementById('sidecar-panel-hubert').classList.toggle('active', tab === 'hubert');
  // Focus the right input
  if (tab === 'hubert') {
    setTimeout(() => document.getElementById('hubert-input')?.focus(), 100);
  }
}

// ── Open / close ──
function openSidecar(agentId, defaultTab) {
  const clean = (agentId || '').replace(/^agent:/, '');
  sidecarAgentId = clean;
  document.getElementById('sidecar-agent-label').textContent = clean || '';

  // Load agent iframe if switching agents
  if (clean) {
    const url = new URL(ADK_CHAT_BASE, window.location.href);
    url.searchParams.set('agent', clean);
    document.getElementById('sidecar-agent-frame').src = url.toString();
  }

  document.getElementById('sidecar-widget').classList.add('open');
  sidecarOpen = true;
  switchSidecarTab(defaultTab || sidecarTab);
}

function closeSidecar() {
  document.getElementById('sidecar-widget').classList.remove('open');
  sidecarOpen = false;
  // Don't clear iframe src or hubert state — sessions persist
}

document.getElementById('sidecar-close').addEventListener('click', closeSidecar);

// ── Hubert chat ──
function renderHubertMessages() {
  const el = document.getElementById('hubert-messages');
  el.innerHTML = hubertMessages.map(m =>
    `<div class="hubert-msg ${m.role}">${esc(m.text)}</div>`
  ).join('');
  el.scrollTop = el.scrollHeight;
}

async function sendHubertMessage() {
  const input = document.getElementById('hubert-input');
  const text = input.value.trim();
  if (!text || hubertSending) return;

  hubertSending = true;
  hubertMessages.push({ role: 'user', text });
  renderHubertMessages();
  input.value = '';
  document.getElementById('hubert-send').disabled = true;

  try {
    const hdrs = { ...graphSecretHeaders(), 'Content-Type': 'application/json' };
    const body = JSON.stringify({
      message: text,
      session_id: hubertSessionId,
      principal: 'graph-ui'
    });
    const r = await fetch(apiUrl('/chat'), { method: 'POST', headers: hdrs, body });
    const data = await r.json();
    if (data.ok) {
      hubertMessages.push({ role: 'assistant', text: data.response || '(no response)' });
      hubertSessionId = data.session_id || hubertSessionId;
    } else {
      hubertMessages.push({ role: 'system', text: `Error: ${data.error || 'unknown'}` });
    }
  } catch (e) {
    hubertMessages.push({ role: 'system', text: `Network error: ${e.message}` });
  }

  hubertSending = false;
  document.getElementById('hubert-send').disabled = false;
  renderHubertMessages();
}

document.getElementById('hubert-send').addEventListener('click', sendHubertMessage);
document.getElementById('hubert-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    sendHubertMessage();
  }
});

// Auto-resize textarea
document.getElementById('hubert-input').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 100) + 'px';
});
```

**Verification:**
- Open graph page
- Call `openSidecar('agent:ops')` from browser console → widget slides up, Agent tab active
- Click "Hubert" tab → Hubert panel shows, Agent iframe stays loaded in background
- Type "what agents are running?" + Enter → gets response from Hubert
- Click "Agent" tab back → Gradio iframe is still showing, no reload
- Click Hubert tab again → message history still there, session persisted
- X button closes widget
- Reopen → both sessions still intact
- Escape closes widget

**Commit:**
```bash
git add index.html
git commit -m "feat: unified sidecar widget with agent + hubert tabs"
```

---

## Task 4: Wire entry points to the sidecar

**Objective:** Three entry points: (a) clicking the Chat synthetic node in agent focus view opens sidecar on Agent tab, (b) "Run in Sidecar" button in workbench footer opens sidecar on Agent tab, (c) Hubert chat icon in toolbar opens sidecar on Hubert tab.

**Files:**
- Modify: `/opt/data/workspace/adk/live-agent-graph/index.html`

**Step 1: Chat node click handler**

In the node click handler (inside `Graph.onNodeClick` callback), add before generic inspect handling:

```js
if (node?.artifact?.startsWith('agent-chat:')) {
  openSidecar(node.artifact.replace('agent-chat:', ''), 'agent');
  return; // skip inspect panel
}
```

**Step 2: Run in Sidecar button**

In `renderFocusSection` where the workbench footer buttons render, add:

```js
html += `<button class="small-action" id="run-sidecar-btn">Run in Sidecar</button>`;
```

Wire after innerHTML assignment:

```js
document.getElementById('run-sidecar-btn')?.addEventListener('click', () => {
  openSidecar(focusedAgentId, 'agent');
});
```

**Step 3: Hubert toolbar button**

Add a button in the graph toolbar (near the existing top-bar controls):

```html
<button id="hubert-toolbar-btn" title="Chat with Hubert" style="
  background: none; border: 1px solid #30363d; border-radius: 6px;
  color: #c9d1d9; padding: 4px 10px; font-size: 12px; cursor: pointer;
  display: flex; align-items: center; gap: 5px;
">
  <span style="font-size:14px;">🐱</span> Hubert
</button>
```

Wire it:

```js
document.getElementById('hubert-toolbar-btn').addEventListener('click', () => {
  if (sidecarOpen && sidecarTab === 'hubert') {
    closeSidecar();
  } else {
    openSidecar(sidecarAgentId || '', 'hubert');
  }
});
```

**Verification:**
- Double-click agent → focus mode → click Chat node → sidecar opens on Agent tab
- Click "Run in Sidecar" button in workbench → same
- Click Hubert button in toolbar → sidecar opens on Hubert tab (or switches to it if already open)
- Click Hubert button again → toggles sidecar closed
- Tab switching preserves both sessions throughout

**Commit:**
```bash
git add index.html
git commit -m "feat: wire chat node, workbench button, and hubert toolbar to sidecar"
```

---

## Task 5: Add "Agent Builder" to CRM workspace (Frappe-native)

**Objective:** Add "Agent Builder" as a first-class shortcut in the Frappe CRM workspace so it appears in the desk sidebar alongside Leads, Deals, etc. Built as a proper Frappe fixture, not a hooks hack.

**Files:**
- Create: `/opt/data/workspace/forsch_frontiers/forsch_frontiers/patches/add_agent_builder_shortcut.py` (one-time migration)
- Modify: `/opt/data/workspace/forsch_frontiers/forsch_frontiers/patches.txt` (register patch)
- Modify: `/opt/data/workspace/forsch_frontiers/forsch_frontiers/hooks.py` (add Workspace to fixtures list)
- Export: workspace fixture via `bench export-fixtures`

**Context:** The CRM uses a "Frappe CRM" Workspace doctype (module: FCRM). It has a `shortcuts` child table (Workspace Shortcut entries) and a `content` JSON field with block layout. Existing shortcuts: Leads, Deals, Organizations, Contacts, SLA, etc. There's already a Web Page doctype `agent-builder` (route: `/agent-builder`) served by the `graph_embed` reverse proxy.

**Approach:** Use a proper Frappe data patch to insert the shortcut, then export the Workspace as a fixture so it's version-controlled and auto-applied on `bench migrate`.

**Step 1: Create the patch file**

Create `/opt/data/workspace/forsch_frontiers/forsch_frontiers/patches/add_agent_builder_shortcut.py`:

```python
"""Add Agent Builder shortcut to the Frappe CRM workspace."""
import frappe
import json


def execute():
    ws = frappe.get_doc("Workspace", "Frappe CRM")

    # Skip if shortcut already exists
    if any(s.label == "Agent Builder" for s in ws.shortcuts):
        return

    # Add Workspace Shortcut child row
    ws.append("shortcuts", {
        "type": "URL",
        "label": "Agent Builder",
        "url": "/agent-builder",
        "icon": "graph",
        "color": "Blue",
        "doc_view": None,
        "idx": len(ws.shortcuts) + 1,
    })

    # Add a content block referencing the shortcut
    content = json.loads(ws.content) if ws.content else []
    # Insert after the PORTAL section (before the SHORTCUTS spacer)
    # Find the first shortcut block to insert near
    insert_idx = 0
    for i, block in enumerate(content):
        if block.get("type") == "shortcut":
            insert_idx = i
            break
    content.insert(insert_idx, {
        "id": "ff-agent-builder-sc",
        "type": "shortcut",
        "data": {"shortcut_name": "Agent Builder", "col": 3},
    })
    ws.content = json.dumps(content)

    ws.save(ignore_permissions=True)
    frappe.db.commit()
```

**Step 2: Register the patch**

Add to `/opt/data/workspace/forsch_frontiers/forsch_frontiers/patches.txt`:

```
forsch_frontiers.patches.add_agent_builder_shortcut
```

**Step 3: Add Workspace to fixtures**

In `hooks.py`, add to the existing `fixtures` list:

```python
fixtures = [
    # ... existing entries ...
    {"dt": "Workspace", "filters": [["name", "=", "Frappe CRM"]]},
]
```

This ensures the workspace (with the Agent Builder shortcut) is exported to `fixtures/workspace.json` on `bench export-fixtures` and auto-restored on deploy.

**Step 4: Apply the patch**

```bash
cd /opt/data/workspace/forsch_frontiers
bench --site crm.forschfrontiers.com migrate
```

**Step 5: Export the fixture**

```bash
bench --site crm.forschfrontiers.com export-fixtures
```

This writes the updated workspace JSON to `fixtures/workspace.json`. Commit it.

**Step 6: Verify**

- Log into CRM desk at `crm.forschfrontiers.com`
- "Agent Builder" appears in the workspace shortcuts section with a graph icon
- Click → loads `/agent-builder` (the graph page)
- The shortcut is visible from the desk sidebar, not just one page

**Commit:**
```bash
cd /opt/data/workspace/forsch_frontiers
git add forsch_frontiers/patches/add_agent_builder_shortcut.py \
        forsch_frontiers/patches.txt \
        forsch_frontiers/hooks.py \
        forsch_frontiers/fixtures/workspace.json
git commit -m "feat(crm): add Agent Builder workspace shortcut (Frappe fixture)"
git push origin main
```

Then trigger Railway redeploy (`bench migrate` runs the patch automatically on deploy).

---

## Task 6: E2E smoke test through CRM

**Objective:** Verify the full flow end-to-end through the CRM proxy: navigate to Agent Builder → interact with graph → open sidecar → chat with agent → switch to Hubert → send message → switch back → session preserved.

**Steps:**
1. Open `crm.forschfrontiers.com/agent-builder`
2. Click an agent node → inspect panel opens
3. Double-click → focus mode with workbench
4. Click Chat synthetic node → sidecar opens on Agent tab
5. Switch to Hubert tab → type "what agents are running?" → get response
6. Switch back to Agent tab → Gradio still loaded
7. Switch to Hubert → message history preserved
8. Close sidecar → reopen via Hubert toolbar button → both sessions intact
9. Escape closes sidecar
10. Back button exits focus mode

**Commit (if fixes needed):**
```bash
cd /opt/data/workspace/adk/live-agent-graph
git add -A && git commit -m "fix: E2E smoke test fixes"
git push origin main
```

---

## Post-implementation

- `git log --oneline -10` in both repos to confirm clean history
- Document the `ADK_CHAT_BASE` override: for CRM production, this should be a same-origin proxy path (not raw `:8800`). That's a follow-up task.
- The Hubert chat endpoint uses `hermes chat --resume` for session persistence — sessions live on the server filesystem and survive widget close/reopen.

## Risks

- **ADK_CHAT_BASE URL**: `http://127.0.0.1:8800/chat/` only works when the browser can reach the bridge directly. For Zach's Mac → cloud box, needs a trycloudflare tunnel URL or CRM same-origin proxy. For CRM embed, same-origin proxy is the production answer. For now, make the constant easily overridable via `window.ADK_CHAT_BASE`.
- **Hubert `/chat` response time**: `hermes chat` spawns a subprocess, loads context, runs inference. Expect 5-30s per response. Show a "thinking..." indicator while waiting.
- **Hubert session cleanup**: Sessions accumulate on disk. The `/chat` endpoint has rate limiting and session ownership tracking, but no TTL cleanup. Not a blocker for v1.
- **Gradio iframe in CRM**: Cross-origin iframe may need `allow` attributes for microphone/camera if Gradio ever uses them. Currently not an issue.
- **Widget stacking**: The existing Hubert chat sidecar in the graph (the old one at the bottom) should be removed or renamed to avoid confusion with the new unified widget.
