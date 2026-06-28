# Hubert Factory Bot — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Hubert as an ADK orchestrator agent with Agent·Logic specialist, wired into the Builder Cockpit chat.

**Architecture:** Hubert is a Google ADK agent using LiteLLM proxy for model routing. He has orchestrator tools (graph overview, specialist routing, cluster management) and delegates agent-development tasks to an Agent·Logic specialist. The existing `/chat` endpoint in `serve.py` is modified to call Hubert's ADK agent directly instead of shelling out to `hermes`.

**Tech Stack:** Python 3.13, Google ADK, LiteLLM proxy (localhost:4000), ForceGraph (frontend, unchanged)

## Global Constraints

- All agents use `LiteLlm` with `api_base=http://127.0.0.1:4000/v1` (LiteLLM proxy)
- Agent tools are Python functions decorated with ADK tool patterns (see existing `forsch.adk_components.tools`)
- Hubert's personality comes from `hubert_soul.md` (existing file at `/root/.hermes/workspace/adk/chat/hubert_soul.md`)
- The Builder Cockpit chat UI (`index.html`) is unchanged — only `serve.py` backend changes
- `X-Graph-Secret` remains the sole auth mechanism

---

### Task 1: Scaffold Hubert ADK agent

**Covers:** [S3, S6]

**Files:**
- Create: `agents/hubert/src/forsch/agent_hubert/__init__.py`
- Create: `agents/hubert/src/forsch/agent_hubert/agent.py`
- Create: `agents/hubert/src/forsch/agent_hubert/tools.py`
- Modify: `agent_specs/agents.yaml` (add hubert entry)

**Interfaces:**
- Produces: `root_agent` (ADK Agent instance), `hubert_model` (LiteLlm instance)

- [ ] **Step 1: Create agent directory structure**

```bash
mkdir -p /root/.hermes/workspace/adk/agents/hubert/src/forsch/agent_hubert
```

- [ ] **Step 2: Create `__init__.py`**

```python
"""Hubert — Factory orchestrator agent."""
```

- [ ] **Step 3: Create `agent.py`**

```python
"""hubert agent definition — factory orchestrator."""

from __future__ import annotations

import os
import pathlib

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = (
    os.environ.get("ADK_LITELLM_KEY_HUBERT")
    or os.environ.get("LITELLM_HERMES_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or os.environ.get("LITELLM_API_KEY")
)
_LITELLM_MODEL = "openai/gpt-5.5"

hubert_model = LiteLlm(
    model=_LITELLM_MODEL,
    api_base=_LITELLM_BASE_URL,
    api_key=_LITELLM_API_KEY,
)

# Load SOUL.md for Hubert's personality
_SOUL_PATH = pathlib.Path(__file__).resolve().parents[4] / "chat" / "hubert_soul.md"
_SOUL_TEXT = _SOUL_PATH.read_text() if _SOUL_PATH.exists() else ""

_INSTRUCTION = f"""{_SOUL_TEXT}

---

## Builder Cockpit Context

You are Hubert, responding inside the Live Agent Graph Builder Cockpit.
The user is interacting with the agent graph visualization.
Stay in character. Be concise. No bullets in chat.
If asked about agents/graph/clusters, reference the live data via your tools.
You can delegate agent-development questions to the agent_logic_specialist.
"""

from .tools import (
    get_graph_overview,
    manage_cluster,
    get_factory_status,
    route_to_agent_logic_specialist,
)

root_agent = Agent(
    name="hubert",
    model=hubert_model,
    description="Factory orchestrator. Chief of staff. Routes work to lane specialists.",
    instruction=_INSTRUCTION,
    tools=[
        get_graph_overview,
        manage_cluster,
        get_factory_status,
        route_to_agent_logic_specialist,
    ],
)

agent = root_agent
```

- [ ] **Step 4: Create stub `tools.py`**

```python
"""Hubert's orchestrator tools."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

WS = Path("/root/.hermes/workspace/adk")
GRAPH_DATA = WS / "live-agent-graph" / "agent-graph-v2.json"


def get_graph_overview() -> str:
    """Return a summary of the current graph state: node counts by type, link counts, cluster info."""
    try:
        data = json.loads(GRAPH_DATA.read_text())
        nodes = data.get("nodes", [])
        links = data.get("links", [])
        by_type = {}
        for n in nodes:
            t = n.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return json.dumps({
            "node_count": len(nodes),
            "link_count": len(links),
            "by_type": by_type,
            "cluster": data.get("cluster", "none"),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def manage_cluster(action: str, name: str = "") -> str:
    """Create, list, or switch clusters. Actions: 'list', 'create', 'switch'."""
    clusters_dir = WS / "live-agent-graph" / "clusters"
    if action == "list":
        clusters = [d.name for d in clusters_dir.iterdir() if d.is_dir()]
        return json.dumps({"clusters": clusters})
    elif action == "create" and name:
        target = clusters_dir / name
        target.mkdir(parents=True, exist_ok=True)
        return json.dumps({"ok": True, "created": name})
    elif action == "switch" and name:
        return json.dumps({"ok": True, "switched_to": name})
    return json.dumps({"error": f"unknown action: {action}"})


def get_factory_status() -> str:
    """Return health status of the factory: agents, tools, services."""
    agents_dir = WS / "agents"
    agents = []
    for d in agents_dir.iterdir():
        if d.is_dir() and (d / "src").exists():
            agents.append(d.name)
    return json.dumps({
        "agent_count": len(agents),
        "agents": sorted(agents),
        "workspace": str(WS),
    })


def route_to_agent_logic_specialist(task: str) -> str:
    """Delegate an agent-development task to the Agent·Logic specialist.
    
    Use this for questions about: agent config, model selection, evals, ADK patterns,
    agent generation, tool wiring, safety levels.
    """
    # Placeholder — will be replaced with actual ADK sub-agent call in Task 3
    return json.dumps({
        "delegated_to": "agent_logic_specialist",
        "task": task,
        "status": "placeholder — specialist not yet implemented",
    })
```

- [ ] **Step 5: Add Hubert to `agents.yaml`**

Append to the agents section:

```yaml
  hubert:
    package: forsch.agent_hubert.agent
    attr: root_agent
    adk_name: hubert
    description: Factory orchestrator. Chief of staff. Routes work to lane specialists.
    model_code: forsch.agent_hubert.agent.hubert_model
    safety_level: read_write
    purpose: 'Orchestrate the factory. Route work to lane specialists. Manage clusters and deployments.'
    instruction: 'You are Hubert. See SOUL.md for personality. See Builder Cockpit context for environment.'
    tools:
      - forsch.agent_hubert.tools.get_graph_overview
      - forsch.agent_hubert.tools.manage_cluster
      - forsch.agent_hubert.tools.get_factory_status
      - forsch.agent_hubert.tools.route_to_agent_logic_specialist
    model: gpt-5.5
    role: orchestrator
```

- [ ] **Step 6: Verify agent loads**

```bash
cd /root/.hermes/workspace/adk
python3 -c "from forsch.agent_hubert.agent import root_agent; print(root_agent.name)"
```
Expected: `hubert`

- [ ] **Step 7: Commit**

```bash
cd /root/.hermes/workspace/adk
git add agents/hubert agent_specs/agents.yaml
git commit -m "feat: scaffold Hubert ADK orchestrator agent"
```

---

### Task 2: Implement Hubert orchestrator tools

**Covers:** [S3]

**Files:**
- Modify: `agents/hubert/src/forsch/agent_hubert/tools.py`
- Create: `components/src/forsch/adk_components/tools/graph_tools.py` (shared graph tools)

**Interfaces:**
- Produces: `get_graph_overview`, `manage_cluster`, `get_factory_status` (real implementations)

- [ ] **Step 1: Create shared graph tools module**

```python
"""Graph tools for reading and analyzing the live agent graph."""

from __future__ import annotations

import json
from pathlib import Path

WS = Path("/root/.hermes/workspace/adk")
GRAPH_DATA = WS / "live-agent-graph" / "agent-graph-v2.json"
CLUSTERS_DIR = WS / "live-agent-graph" / "clusters"
AGENTS_DIR = WS / "agents"


def load_graph() -> dict:
    """Load the current graph data from agent-graph-v2.json."""
    return json.loads(GRAPH_DATA.read_text())


def get_graph_overview() -> str:
    """Return a summary of the current graph state: node counts by type, link counts, cluster info."""
    try:
        data = load_graph()
        nodes = data.get("nodes", [])
        links = data.get("links", [])
        by_type = {}
        for n in nodes:
            t = n.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        clusters = [d.name for d in CLUSTERS_DIR.iterdir() if d.is_dir()] if CLUSTERS_DIR.exists() else []
        return json.dumps({
            "node_count": len(nodes),
            "link_count": len(links),
            "by_type": by_type,
            "clusters": clusters,
            "current_cluster": data.get("cluster", "none"),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def manage_cluster(action: str, name: str = "") -> str:
    """Create, list, or switch clusters. Actions: 'list', 'create', 'switch'."""
    if action == "list":
        clusters = [d.name for d in CLUSTERS_DIR.iterdir() if d.is_dir()] if CLUSTERS_DIR.exists() else []
        return json.dumps({"clusters": clusters})
    elif action == "create" and name:
        target = CLUSTERS_DIR / name
        target.mkdir(parents=True, exist_ok=True)
        return json.dumps({"ok": True, "created": name})
    elif action == "switch" and name:
        return json.dumps({"ok": True, "switched_to": name, "note": "UI must reload graph"})
    return json.dumps({"error": f"unknown action: {action}"})


def get_factory_status() -> str:
    """Return health status of the factory: agents, tools, services."""
    agents = []
    if AGENTS_DIR.exists():
        for d in AGENTS_DIR.iterdir():
            if d.is_dir() and (d / "src").exists():
                agents.append(d.name)
    tools_dir = WS / "components" / "src" / "forsch" / "adk_components" / "tools"
    tool_modules = []
    if tools_dir.exists():
        for f in tools_dir.glob("*.py"):
            if f.name != "__init__.py":
                tool_modules.append(f.stem)
    return json.dumps({
        "agent_count": len(agents),
        "agents": sorted(agents),
        "tool_modules": sorted(tool_modules),
        "workspace": str(WS),
    })
```

- [ ] **Step 2: Register graph tools in `__init__.py`**

Add to `components/src/forsch/adk_components/tools/__init__.py`:

```python
from .graph_tools import get_graph_overview, manage_cluster, get_factory_status
```

And add to `__all__`:
```python
"get_graph_overview",
"manage_cluster",
"get_factory_status",
```

- [ ] **Step 3: Update Hubert's `tools.py` to use shared tools**

```python
"""Hubert's orchestrator tools."""

from __future__ import annotations

import json

from forsch.adk_components.tools.graph_tools import (
    get_graph_overview,
    manage_cluster,
    get_factory_status,
)


def route_to_agent_logic_specialist(task: str) -> str:
    """Delegate an agent-development task to the Agent·Logic specialist.
    
    Use this for questions about: agent config, model selection, evals, ADK patterns,
    agent generation, tool wiring, safety levels.
    """
    # Placeholder — will be replaced with actual ADK sub-agent call in Task 3
    return json.dumps({
        "delegated_to": "agent_logic_specialist",
        "task": task,
        "status": "placeholder — specialist not yet implemented",
    })
```

- [ ] **Step 4: Verify tools work**

```bash
cd /root/.hermes/workspace/adk
python3 -c "
from forsch.adk_components.tools.graph_tools import get_graph_overview, get_factory_status
print(get_graph_overview())
print(get_factory_status())
"
```
Expected: JSON output with node counts and agent list

- [ ] **Step 5: Commit**

```bash
cd /root/.hermes/workspace/adk
git add components/src/forsch/adk_components/tools/graph_tools.py
git add components/src/forsch/adk_components/tools/__init__.py
git add agents/hubert/src/forsch/agent_hubert/tools.py
git commit -m "feat: implement Hubert orchestrator tools (graph overview, cluster mgmt, factory status)"
```

---

### Task 3: Scaffold Agent·Logic specialist

**Covers:** [S3, S6]

**Files:**
- Create: `agents/agent_logic_specialist/src/forsch/agent_agent_logic_specialist/__init__.py`
- Create: `agents/agent_logic_specialist/src/forsch/agent_agent_logic_specialist/agent.py`
- Create: `agents/agent_logic_specialist/src/forsch/agent_agent_logic_specialist/tools.py`
- Modify: `agent_specs/agents.yaml` (add agent_logic_specialist entry)

**Interfaces:**
- Produces: `root_agent` (ADK Agent instance) for the specialist

- [ ] **Step 1: Create agent directory structure**

```bash
mkdir -p /root/.hermes/workspace/adk/agents/agent_logic_specialist/src/forsch/agent_agent_logic_specialist
```

- [ ] **Step 2: Create `__init__.py`**

```python
"""Agent·Logic specialist — agent development expert."""
```

- [ ] **Step 3: Create `agent.py`**

```python
"""agent_logic_specialist agent definition."""

from __future__ import annotations

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = (
    os.environ.get("ADK_LITELLM_KEY_AGENT_LOGIC")
    or os.environ.get("LITELLM_HERMES_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or os.environ.get("LITELLM_API_KEY")
)
_LITELLM_MODEL = "openai/gpt-5.5"

agent_logic_model = LiteLlm(
    model=_LITELLM_MODEL,
    api_base=_LITELLM_BASE_URL,
    api_key=_LITELLM_API_KEY,
)

_INSTRUCTION = """You are the Agent·Logic specialist for the Forsch ADK Factory.

Your domain: agent configuration, model selection, evals, ADK patterns, agent generation, tool wiring, safety levels.

When asked about an agent:
1. Read its config from agents.yaml
2. Check its current status (built/blank/error)
3. Report its model, tools, safety level, and purpose

When asked to generate an agent:
1. Ask for the agent id, description, and tools
2. Scaffold the agent directory and code
3. Register it in agents.yaml

When asked about models:
1. Query LiteLLM proxy for available models
2. Compare capabilities, pricing, context windows
3. Recommend based on the use case

When asked about evals:
1. Check if eval files exist for the agent
2. Run evals if requested
3. Report results with pass/fail per prompt

Be precise. Cite file paths. Show code when relevant.
"""

from .tools import (
    list_agents,
    get_agent_config,
    update_agent_config,
    get_model_info,
    get_adk_reference,
)

root_agent = Agent(
    name="agent_logic_specialist",
    model=agent_logic_model,
    description="Agent development expert. Config, models, evals, ADK patterns.",
    instruction=_INSTRUCTION,
    tools=[
        list_agents,
        get_agent_config,
        update_agent_config,
        get_model_info,
        get_adk_reference,
    ],
)

agent = root_agent
```

- [ ] **Step 4: Create `tools.py`**

```python
"""Agent·Logic specialist tools."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

WS = Path("/root/.hermes/workspace/adk")
AGENTS_DIR = WS / "agents"
SPECS_FILE = WS / "agent_specs" / "agents.yaml"


def list_agents() -> str:
    """List all agents with their status, model, and tools."""
    agents = []
    if AGENTS_DIR.exists():
        for d in sorted(AGENTS_DIR.iterdir()):
            if d.is_dir() and (d / "src").exists():
                agent_file = None
                for f in (d / "src").rglob("agent.py"):
                    agent_file = f
                    break
                status = "built" if agent_file else "blank"
                agents.append({"id": d.name, "status": status})
    return json.dumps({"agents": agents, "count": len(agents)}, indent=2)


def get_agent_config(agent_id: str) -> str:
    """Read an agent's configuration from agents.yaml."""
    try:
        import yaml
        raw = yaml.safe_load(SPECS_FILE.read_text()) or {}
        agents_raw = raw.get("agents") or {}
        if agent_id not in agents_raw:
            return json.dumps({"error": f"agent '{agent_id}' not found"})
        spec = agents_raw[agent_id]
        return json.dumps({"agent_id": agent_id, "config": spec}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def update_agent_config(agent_id: str, field: str, value: str) -> str:
    """Update a single field in an agent's config in agents.yaml."""
    try:
        import yaml
        raw = yaml.safe_load(SPECS_FILE.read_text()) or {}
        agents_raw = raw.get("agents") or {}
        if agent_id not in agents_raw:
            return json.dumps({"error": f"agent '{agent_id}' not found"})
        agents_raw[agent_id][field] = value
        with open(SPECS_FILE, "w") as f:
            yaml.dump(raw, f, default_flow_style=False, sort_keys=False)
        return json.dumps({"ok": True, "updated": f"{agent_id}.{field}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_model_info(model: str = "") -> str:
    """Get available models from LiteLLM proxy, or info about a specific model."""
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:4000/v1/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["id"] for m in data.get("data", [])]
            if model:
                matching = [m for m in models if model.lower() in m.lower()]
                return json.dumps({"query": model, "matches": matching})
            return json.dumps({"models": sorted(models), "count": len(models)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_adk_reference(topic: str = "") -> str:
    """Get ADK reference information for common patterns and best practices."""
    ref = {
        "agent_structure": "Agent defined in agent.py with Agent() from google.adk. Uses LiteLlm for model routing.",
        "tools": "Tools are Python functions imported from forsch.adk_components.tools. Each tool returns a string (usually JSON).",
        "models": "Models routed through LiteLLM proxy at localhost:4000. Use LiteLlm() with model, api_base, api_key.",
        "safety_levels": "read_only (no mutations), read_write (can modify graph), local_write (can modify host files).",
        "evals": "Eval prompts defined in agents.yaml under smoke_prompts. Run with adk eval command.",
        "testing": "Use pytest. Test tools independently. Mock external calls.",
    }
    if topic and topic in ref:
        return json.dumps({topic: ref[topic]})
    return json.dumps(ref, indent=2)
```

- [ ] **Step 5: Add to `agents.yaml`**

```yaml
  agent_logic_specialist:
    package: forsch.agent_agent_logic_specialist.agent
    attr: root_agent
    adk_name: agent_logic_specialist
    description: Agent development expert. Config, models, evals, ADK patterns.
    model_code: forsch.agent_agent_logic_specialist.agent.agent_logic_model
    safety_level: read_write
    purpose: 'Agent configuration, model selection, evals, ADK patterns, agent generation, tool wiring.'
    instruction: 'You are the Agent·Logic specialist. See full instruction in agent.py.'
    tools:
      - forsch.agent_agent_logic_specialist.tools.list_agents
      - forsch.agent_agent_logic_specialist.tools.get_agent_config
      - forsch.agent_agent_logic_specialist.tools.update_agent_config
      - forsch.agent_agent_logic_specialist.tools.get_model_info
      - forsch.agent_agent_logic_specialist.tools.get_adk_reference
    model: gpt-5.5
    role: specialist
```

- [ ] **Step 6: Verify agent loads**

```bash
cd /root/.hermes/workspace/adk
python3 -c "from forsch.agent_agent_logic_specialist.agent import root_agent; print(root_agent.name)"
```
Expected: `agent_logic_specialist`

- [ ] **Step 7: Commit**

```bash
cd /root/.hermes/workspace/adk
git add agents/agent_logic_specialist agent_specs/agents.yaml
git commit -m "feat: scaffold Agent·Logic specialist ADK agent"
```

---

### Task 4: Wire Hubert to Agent·Logic specialist

**Covers:** [S3]

**Files:**
- Modify: `agents/hubert/src/forsch/agent_hubert/tools.py`
- Modify: `agents/hubert/src/forsch/agent_hubert/agent.py`

**Interfaces:**
- Consumes: `agent_logic_specialist.root_agent` (from Task 3)
- Produces: Working `route_to_agent_logic_specialist()` that calls the specialist

- [ ] **Step 1: Implement `route_to_agent_logic_specialist`**

Replace the placeholder in `agents/hubert/src/forsch/agent_hubert/tools.py`:

```python
def route_to_agent_logic_specialist(task: str) -> str:
    """Delegate an agent-development task to the Agent·Logic specialist.
    
    Use this for questions about: agent config, model selection, evals, ADK patterns,
    agent generation, tool wiring, safety levels.
    """
    try:
        from forsch.agent_agent_logic_specialist.agent import root_agent as specialist
        from google.adk.runners import InMemoryRunner
        from google.adk.sessions import Session
        import asyncio

        runner = InMemoryRunner(agent=specialist, app_name="hubert_delegation")
        session = Session()

        async def run():
            result = await runner.run_async(
                session=session,
                user_message=task,
            )
            return result

        result = asyncio.run(run())
        return json.dumps({
            "delegated_to": "agent_logic_specialist",
            "task": task,
            "response": str(result),
        })
    except Exception as e:
        return json.dumps({
            "delegated_to": "agent_logic_specialist",
            "task": task,
            "error": str(e),
        })
```

- [ ] **Step 2: Verify delegation works**

```bash
cd /root/.hermes/workspace/adk
python3 -c "
from forsch.agent_hubert.tools import route_to_agent_logic_specialist
print(route_to_agent_logic_specialist('What agents exist in the factory?'))
"
```
Expected: JSON with agent list from specialist

- [ ] **Step 3: Commit**

```bash
cd /root/.hermes/workspace/adk
git add agents/hubert/src/forsch/agent_hubert/tools.py
git commit -m "feat: wire Hubert to Agent·Logic specialist delegation"
```

---

### Task 5: Integrate Hubert into Builder Cockpit `/chat` endpoint

**Covers:** [S5]

**Files:**
- Modify: `live-agent-graph/serve.py` (replace `chat_with_hubert()`)

**Interfaces:**
- Consumes: `hubert.root_agent` (from Task 1)
- Produces: Working `/chat` endpoint that calls Hubert's ADK agent

- [ ] **Step 1: Replace `chat_with_hubert()` in `serve.py`**

Find the existing `chat_with_hubert` function (line ~754) and replace it with:

```python
def chat_with_hubert(message: str, session_id: str | None = None) -> dict:
    """Send a message to Hubert via ADK agent and return the response."""
    try:
        from forsch.agent_hubert.agent import root_agent as hubert_agent
        from google.adk.runners import InMemoryRunner
        from google.adk.sessions import Session
        import asyncio

        context_msg = (
            "[Builder Cockpit context] You are Hubert, responding inside the "
            "Live Agent Graph Builder Cockpit chat sidecar. "
            "The user is interacting with the agent graph visualization. "
            "Stay in character. Be concise. No bullets in chat. "
            "If asked about agents/graph/clusters, reference the live data via your tools.\n\n"
            f"User: {message}"
        )

        runner = InMemoryRunner(agent=hubert_agent, app_name="builder_cockpit")
        session = Session()

        async def run():
            result = await runner.run_async(
                session=session,
                user_message=context_msg,
            )
            return result

        result = asyncio.run(run())
        return {"ok": True, "response": str(result), "session_id": session_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 2: Verify `/chat` endpoint works locally**

```bash
cd /root/.hermes/workspace/adk/live-agent-graph
GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898 &
sleep 2
curl -s -X POST http://127.0.0.1:8898/chat \
  -H "Content-Type: application/json" \
  -H "X-Graph-Secret: localtestsecret" \
  -d '{"message":"hello hubert","principal":"graph-ui"}' | python3 -m json.tool
```
Expected: JSON with `"ok": true` and Hubert's response

- [ ] **Step 3: Commit**

```bash
cd /root/.hermes/workspace/adk/live-agent-graph
git add serve.py
git commit -m "feat: integrate Hubert ADK agent into /chat endpoint"
```

---

### Task 6: End-to-end verification

**Covers:** [S8]

**Files:** None (verification only)

- [ ] **Step 1: Run existing tests**

```bash
cd /root/.hermes/workspace/adk/live-agent-graph
python3 -m pytest -q
```
Expected: All tests pass

- [ ] **Step 2: Test Hubert chat via Builder Cockpit**

1. Open `https://graph.forschfrontiers.com`
2. Unlock edits (enter graph secret)
3. Open Hubert chat sidecar
4. Send: "What agents exist in the factory?"
5. Verify Hubert responds in character with agent list

- [ ] **Step 3: Test specialist delegation**

1. In Hubert chat, send: "What model is shelby using?"
2. Verify Hubert delegates to Agent·Logic specialist and returns the answer

- [ ] **Step 4: Deploy to live**

```bash
cd /root/.hermes/workspace/adk
git push origin main
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && git pull --ff-only'
```

- [ ] **Step 5: Verify on live**

```bash
curl -s -X POST https://graph.forschfrontiers.com/chat \
  -H "Content-Type: application/json" \
  -H "X-Graph-Secret: <secret>" \
  -d '{"message":"hello hubert","principal":"graph-ui"}' | python3 -m json.tool
```
Expected: Hubert responds in character
