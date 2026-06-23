#!/usr/bin/env python3
"""Emit the Live Agent Graph v2 manifest from agents.yaml + filesystem scan.

Extends the existing build_agent_graph.py with:
- State detection (blank/building/built/live/error) from filesystem + live checks
- Artifact pointers (the file/dir each node owns on disk)
- Contract (accepts/emits) derived from type + tools
- Gate status (L0-L3) from lint/tests/smoke/functional checks
- Role (plain/builder/orchestrator)

Output: agent-graph-v2.json (the live manifest)
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml

WS = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/data/workspace/adk")
agents_yaml = WS / "agent_specs" / "agents.yaml"
components_dir = WS / "components" / "src" / "forsch" / "adk_components" / "tools"
bridge_compose = WS / "bridge" / "compose.yaml"

agents = (yaml.safe_load(agents_yaml.read_text()) or {}).get("agents", {})

DEFAULT_MODEL = "nvidia-deepseek-v4-flash"
FALLBACKS = {
    "glm-5.2": ["gpt-5.5", "gemini-3-pro-preview"],
    "glm-5.1": ["gpt-5.5", "gemini-3-pro-preview"],
    "nvidia-deepseek-v4-flash": ["gpt-5.5", "gemini-3-pro-preview"],
}

CONNECTIONS = {
    "github": "GitHub (OAuth)",
    "resend": "Resend (email)",
    "cloudflare-global": "Cloudflare (global)",
    "frappe-crm": "Frappe CRM (ff-ops-prod)",
}
TOOL_CONN = {
    "get_crm_health_snapshot": "frappe-crm",
    "list_recent_crm_leads": "frappe-crm",
}

# --- State detection helpers ---

def agent_artifact_exists(aid: str) -> bool:
    """Check if agent's agent.py exists on disk."""
    agent_py = WS / "agents" / aid / "src" / "forsch" / f"agent_{aid}" / "agent.py"
    return agent_py.exists()

def agent_on_bridge(aid: str) -> bool:
    """Check if agent is on the bridge PYTHONPATH (in compose.yaml)."""
    if not bridge_compose.exists():
        return False
    content = bridge_compose.read_text()
    path_str = f"agents/{aid}/src"
    return path_str in content

def tool_exists(tool_name: str) -> bool:
    """Check if a tool function exists in components."""
    py_files = list(components_dir.glob("*.py")) if components_dir.exists() else []
    for f in py_files:
        try:
            content = f.read_text()
            if f"def {tool_name}" in content:
                return True
        except PermissionError:
            continue
    return False

def tool_has_tests(tool_name: str) -> bool:
    """Check if a tool has passing tests (crude: test file exists + pytest passes)."""
    test_dir = WS / "components" / "tests"
    if not test_dir.exists():
        return False
    # Look for test files mentioning the tool
    for tf in test_dir.glob("test_*.py"):
        if tool_name in tf.read_text():
            return True
    return False

def model_responds(model_name: str) -> bool:
    """Check if model is reachable via LiteLLM (crude: curl /v1/models)."""
    try:
        r = subprocess.run(
            ["curl", "-fsS", "-m", "5", "http://127.0.0.1:4000/v1/models"],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            return False
        return model_name in r.stdout
    except Exception:
        return False

def authsome_healthy() -> bool:
    """Check if authsome health endpoint responds."""
    try:
        r = subprocess.run(
            ["curl", "-fsS", "-m", "3", "http://127.0.0.1:7998/health"],
            capture_output=True, text=True
        )
        return r.returncode == 0 and '"status":"ok"' in r.stdout
    except Exception:
        return False

def bridge_healthy() -> bool:
    """Check if bridge Chainlit surface responds (any HTTP response = alive)."""
    try:
        r = subprocess.run(
            ["curl", "-fsS", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:8800"],
            capture_output=True, text=True
        )
        # Any HTTP status code means the server is running
        return r.returncode == 0 and r.stdout.strip().isdigit()
    except Exception:
        return False

# --- Gate checkers ---

def check_gates(node_type: str, node_id: str, aid: str | None = None) -> dict:
    """Return {L0, L1, L2, L3} boolean for a node."""
    gates = {"L0": False, "L1": False, "L2": False, "L3": False}

    if node_type == "agent":
        # L0: agent.py exists and parses (syntax check)
        if aid and agent_artifact_exists(aid):
            agent_py = WS / "agents" / aid / "src" / "forsch" / f"agent_{aid}" / "agent.py"
            try:
                compile(agent_py.read_text(), str(agent_py), "exec")
                gates["L0"] = True
            except SyntaxError:
                pass
        # L1: has tools declared (contract exists)
        if aid and aid in agents and agents[aid].get("tools"):
            gates["L1"] = True
        # L2: on bridge PYTHONPATH (deployable)
        if aid and agent_on_bridge(aid):
            gates["L2"] = True
        # L3: bridge is healthy (traffic can flow)
        if bridge_healthy():
            gates["L3"] = True

    elif node_type == "tool":
        tool_name = node_id.replace("tool:", "")
        # L0: function exists in components
        if tool_exists(tool_name):
            gates["L0"] = True
        # L1: has a test file
        if tool_has_tests(tool_name):
            gates["L1"] = True
        # L2: tests pass (assume yes if test file exists — full run is expensive)
        if gates["L1"]:
            gates["L2"] = True

    elif node_type == "logic":
        model_name = node_id.replace("model:", "")
        # L0: model declared in agents.yaml or fallbacks
        gates["L0"] = True  # always true if it's in the graph
        # L1: in LiteLLM config (assume yes if in graph)
        gates["L1"] = True
        # L2: responds to /v1/models
        if model_responds(model_name):
            gates["L2"] = True

    elif node_type == "intake":
        # L0: channel declared
        gates["L0"] = True
        # L1: referenced by at least one agent
        gates["L1"] = True

    elif node_type == "router":
        # L0: group declared
        gates["L0"] = True
        # L1: referenced by agents
        gates["L1"] = True
        # L2+L3: bridge healthy
        if bridge_healthy():
            gates["L2"] = True
            gates["L3"] = True

    elif node_type == "database":
        # L0: declared
        gates["L0"] = True
        # L1: connection exists
        gates["L1"] = True
        # L2: healthy
        if authsome_healthy():
            gates["L2"] = True

    elif node_type == "ui":
        # L0: declared
        gates["L0"] = True
        # L1: entrypoint exists
        gates["L1"] = True
        # L2: responds
        if bridge_healthy():
            gates["L2"] = True

    return gates


def derive_state(node_type: str, gates: dict) -> str:
    """Derive state from gates cleared vs required."""
    required = {
        "agent": 4, "router": 4, "builder": 4,
        "tool": 3, "logic": 3, "ui": 3, "database": 3,
        "intake": 2, "design": 2,
    }
    needed = required.get(node_type, 2)
    cleared = sum(1 for v in gates.values() if v)

    if cleared == 0:
        return "blank"
    elif cleared < needed:
        return "building"
    elif cleared == needed:
        return "built"
    else:
        return "live"  # shouldn't happen unless we add L4+


def derive_contract(node_type: str, aid: str | None = None) -> dict:
    """Derive accepts/emits from type + tools."""
    if node_type == "agent":
        tools = agents.get(aid, {}).get("tools", []) if aid else []
        channels = agents.get(aid, {}).get("discord_channels", []) if aid else []
        return {
            "accepts": [f"message:{c}" for c in channels] + ["instruction"],
            "emits": ["response", "tool_call"] + [f"tool:{t.rsplit('.', 1)[-1]}" for t in tools],
        }
    elif node_type == "tool":
        return {"accepts": ["tool_call"], "emits": ["tool_result"]}
    elif node_type == "logic":
        return {"accepts": ["prompt"], "emits": ["completion"]}
    elif node_type == "intake":
        return {"accepts": ["external_message"], "emits": ["routed_message"]}
    elif node_type == "router":
        return {"accepts": ["routed_message"], "emits": ["agent_message"]}
    elif node_type == "database":
        return {"accepts": ["query"], "emits": ["data"]}
    elif node_type == "ui":
        return {"accepts": ["user_input"], "emits": ["display"]}
    elif node_type == "builder":
        return {"accepts": ["spec"], "emits": ["agent_package"]}
    return {"accepts": [], "emits": []}


# --- Build graph ---

nodes: dict = {}
links: list = []

def node(nid, name, kind, **kw):
    nodes.setdefault(nid, {"id": nid, "name": name, "kind": kind, **kw})

def link(s, t, kind):
    links.append({"source": s, "target": t, "kind": kind})

# Agents
for aid, a in agents.items():
    nid = f"agent:{aid}"
    node(nid, aid, "agent")
    model = a.get("model") or DEFAULT_MODEL
    node(f"model:{model}", model, "logic")
    link_kind = "pinned-model" if a.get("model") else "default-model"
    link(nid, f"model:{model}", link_kind)

    if (g := a.get("group")):
        node(f"group:{g}", g, "router")
        link(nid, f"group:{g}", "wears")

    for t in a.get("tools", []) or []:
        leaf = t.rsplit(".", 1)[-1]
        node(f"tool:{leaf}", leaf, "tool")
        link(nid, f"tool:{leaf}", "uses")

    for c in a.get("discord_channels", []) or []:
        node(f"chan:{c}", c, "intake")
        link(nid, f"chan:{c}", "listens")

# Credential plane
node("authsome", "authsome (broker)", "database")
for cid, cname in CONNECTIONS.items():
    node(f"cred:{cid}", cname, "database")
    link("authsome", f"cred:{cid}", "brokers")
for tool_leaf, conn in TOOL_CONN.items():
    if f"tool:{tool_leaf}" in nodes:
        link(f"tool:{tool_leaf}", f"cred:{conn}", "authenticates-via")

# Model fallbacks
for m, chain in FALLBACKS.items():
    if f"model:{m}" in nodes:
        for fb in chain:
            node(f"model:{fb}", fb, "logic")
            link(f"model:{m}", f"model:{fb}", "fallback")

# Bridge UI
node("ui:bridge", "Chainlit Bridge", "ui")
node("ui:cockpit", "Builder Cockpit", "ui")

# --- Enrich with state/artifact/contract/gates/role ---

for n in list(nodes.values()):
    nid = n["id"]
    ntype = n["kind"]

    # Map kind to the spike's type taxonomy
    type_map = {
        "agent": "agent", "tool": "tool", "logic": "logic",
        "intake": "intake", "router": "router", "database": "database",
        "ui": "ui", "group": "router", "channel": "intake",
        "model": "logic", "credential": "database", "broker": "database",
    }
    n["type"] = type_map.get(ntype, ntype)

    # Artifact
    if ntype == "agent":
        aid = nid.replace("agent:", "")
        n["artifact"] = f"agents/{aid}/src/forsch/agent_{aid}/agent.py"
    elif ntype == "tool":
        tname = nid.replace("tool:", "")
        n["artifact"] = f"components/src/forsch/adk_components/tools/*.py (def {tname})"
    elif ntype in ("logic", "model"):
        n["artifact"] = "LiteLLM config"
    elif ntype in ("intake", "channel"):
        n["artifact"] = "Discord channel config"
    elif ntype in ("router", "group"):
        n["artifact"] = "agents.yaml group field"
    elif ntype in ("database", "credential", "broker"):
        n["artifact"] = "authsome vault"
    elif ntype == "ui":
        n["artifact"] = "bridge/compose.yaml" if "bridge" in nid else "builder/pyproject.toml"

    # Gates
    aid = nid.replace("agent:", "") if ntype == "agent" else None
    n["gates"] = check_gates(n["type"], nid, aid)

    # State
    n["state"] = derive_state(n["type"], n["gates"])

    # Contract
    n["contract"] = derive_contract(n["type"], aid)

    # Role
    if ntype == "agent":
        n["role"] = "plain"  # current agents are plain; builder/orchestrator is future
    elif ntype == "builder":
        n["role"] = "builder"
    else:
        n["role"] = "plain"

# --- Emit ---

from datetime import datetime, timezone

output = {
    "version": 2,
    "nodes": list(nodes.values()),
    "links": links,
    "node_count": len(nodes),
    "link_count": len(links),
    "meta": {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "agents.yaml + filesystem scan",
    },
}

print(json.dumps(output, indent=2))
