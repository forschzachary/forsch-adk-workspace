#!/usr/bin/env python3
"""HTTP bridge for the Live Agent Graph UI — serves index.html + cluster tabs + spawn + pulse + chat.

Usage:
  python3 serve.py [port]

Security:
  - Binds 127.0.0.1 (not 0.0.0.0). Only reachable from this box.
  - Mutating endpoints require X-Graph-Secret header matching GRAPH_SERVER_SECRET env var.
  - Read-only endpoints (/pulse, /clusters, /manifest, /models) are unauthenticated.
  - /chat enforces session ownership, rate-limits per principal, and logs every invocation.
  - CORS is pinned to the CRM origin on read-only endpoints; mutating endpoints have no CORS.
"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from workspace_resolver import workspace_root

SPIKE_DIR = Path(__file__).resolve().parent
WS = workspace_root() / "adk"
FACTORY_PYTHON = WS / "factory" / ".venv" / "bin" / "python3.12"
BUILDER_PY = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable

# Persistent home (HERMES_HOME); on the box this is /opt/data (== host /root/.hermes).
_HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))

GRAPH_SECRET = os.environ.get("GRAPH_SERVER_SECRET", "")
# Durability: if the env var wasn't injected at launch, read the secret from the
# persistent file ($HERMES_HOME/graph-server-secret). This makes the secret survive
# ANY restart — manual, supervised, or container reboot — without depending on the
# launch env. The file is the durable store; if it's also absent, GRAPH_SECRET
# stays empty and _check_secret fails closed (refuses every mutating request).
if not GRAPH_SECRET:
    _secret_file = _HERMES_HOME / "graph-server-secret"
    if _secret_file.exists():
        GRAPH_SECRET = _secret_file.read_text().strip()
CRM_ORIGIN = os.environ.get("CRM_ORIGIN", "https://crm.forschfrontiers.com")

# Bridge CHAT_TOKEN — needed so the browser can authenticate the Gradio iframe.
# Read from env var first, then fall back to bridge.env file.
_BRIDGE_ENV_FILE = Path("/opt/data/workspace/adk/bridge/bridge.env")
def _chat_token() -> str:
    token = os.environ.get("CHAT_TOKEN", "")
    if not token and _BRIDGE_ENV_FILE.exists():
        for line in _BRIDGE_ENV_FILE.read_text().splitlines():
            if line.startswith("CHAT_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    return token

# External URL for the Gradio bridge (browser-facing iframe src).
CHAT_BASE_URL = os.environ.get("CHAT_BASE_URL", "https://chat.forschfrontiers.com/chat/")
CRM_API_KEY_FILE = _HERMES_HOME / "secrets" / "frappe-admin-api-key"
CRM_BASE = os.environ.get("CRM_BASE_URL", "https://crm.forschfrontiers.com")

# ── Session ownership ──
_session_owners: dict[str, tuple[str, float]] = {}  # session_id → (principal, created_at)
_session_lock = threading.Lock()
SESSION_MAX_AGE = 3600.0  # evict sessions older than 1 hour

# ── Rate limiting ──
_rate_state: dict[str, tuple[int, float]] = {}  # principal → (count, window_start)
_rate_lock = threading.Lock()
RATE_LIMIT = 30       # max requests
RATE_WINDOW = 60.0    # per 60 seconds

# ── Audit log ──
AUDIT_LOG = SPIKE_DIR / "chat_audit.log"

# ── Eval paths ──
EVALSETS_DIR = SPIKE_DIR / "evalsets"
EVAL_RUNS_DIR = SPIKE_DIR / ".eval_runs"

def _evict_stale():
    """Periodic cleanup: evict stale sessions and rate-limit windows."""
    while True:
        time.sleep(300)  # every 5 minutes
        now = time.time()
        with _session_lock:
            stale = [sid for sid, (_, created) in _session_owners.items()
                     if now - created > SESSION_MAX_AGE]
            for sid in stale:
                del _session_owners[sid]
        with _rate_lock:
            stale_keys = [p for p, (c, ws) in _rate_state.items()
                         if now - ws > RATE_WINDOW * 2]
            for k in stale_keys:
                del _rate_state[k]

# Start eviction thread
_evict_thread = threading.Thread(target=_evict_stale, daemon=True)
_evict_thread.start()

def _audit(principal: str, message: str, session_id: str | None, outcome: str):
    """Append a chat invocation to the audit log."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = json.dumps({
        "ts": ts,
        "principal": principal,
        "message": message[:200],
        "session_id": session_id,
        "outcome": outcome,
    })
    try:
        with open(AUDIT_LOG, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass

def _check_rate(principal: str) -> bool:
    """Return True if within rate limit, False if exceeded."""
    with _rate_lock:
        now = time.time()
        count, window_start = _rate_state.get(principal, (0, now))
        if now - window_start > RATE_WINDOW:
            count = 0
            window_start = now
        if count >= RATE_LIMIT:
            return False
        _rate_state[principal] = (count + 1, window_start)
        return True

def _crm_post(endpoint: str, data: dict) -> dict:
    """Call a whitelisted CRM endpoint with the admin API key."""
    if not CRM_API_KEY_FILE.exists():
        return {"ok": False, "error": "CRM API key not available"}
    try:
        import urllib.request
        key = CRM_API_KEY_FILE.read_text().strip()
        url = f"{CRM_BASE}/api/method/{endpoint}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"token {key}",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _crm_get(endpoint: str, params: dict = None) -> dict | None:
    """Call a CRM whitelisted GET endpoint. Returns parsed JSON or None."""
    if not CRM_API_KEY_FILE.exists():
        return None
    try:
        import urllib.request
        import urllib.parse
        key = CRM_API_KEY_FILE.read_text().strip()
        url = f"{CRM_BASE}/api/method/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {key}",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def fetch_clusters_from_crm() -> list:
    """Fetch cluster list from CRM DocType (source of truth)."""
    data = _crm_get("forsch_frontiers.sync.agent_graph.list_clusters")
    if data and "message" in data:
        return data["message"]
    return []


def fetch_manifest_from_crm(cluster_id: str) -> dict | None:
    """Fetch agent graph manifest for a cluster from CRM."""
    data = _crm_get("forsch_frontiers.sync.agent_graph.get_agent_graph_manifest",
                     {"cluster_id": cluster_id})
    if data and "message" in data:
        return data["message"]
    return None


def promote_agent(agent_id: str, target_role: str) -> dict:
    py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
    result = subprocess.run(
        [py, str(SPIKE_DIR / "promote_agent.py"), agent_id, target_role],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        try:
            return json.loads(result.stdout.strip().split("\n")[-1])
        except json.JSONDecodeError:
            return {"ok": False, "error": f"parse error: {result.stdout[:200]}"}
    return {"ok": False, "error": result.stderr[:300] or f"exit {result.returncode}"}


def get_pulse():
    active_edges = []
    live_nodes = []

    try:
        r = subprocess.run(
            ["curl", "-s", "-S", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}",
             "http://127.0.0.1:8800"],
            capture_output=True, text=True,
        )
        bridge_alive = r.returncode == 0 and r.stdout.strip().isdigit()
    except Exception:
        bridge_alive = False

    try:
        r = subprocess.run(
            ["curl", "-s", "-S", "-m", "3", "http://127.0.0.1:7998/health"],
            capture_output=True, text=True,
        )
        authsome_alive = r.returncode == 0 and '"status":"ok"' in r.stdout
    except Exception:
        authsome_alive = False

    try:
        r = subprocess.run(
            ["curl", "-s", "-S", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}",
             "http://127.0.0.1:4000/v1/models"],
            capture_output=True, text=True,
        )
        litellm_alive = r.returncode == 0 and r.stdout.strip().isdigit()
    except Exception:
        litellm_alive = False

    graph_path = SPIKE_DIR / "agent-graph-v2.json"
    if graph_path.exists():
        graph = json.loads(graph_path.read_text())
        for link in graph.get("links", []):
            src_type = ""
            tgt_type = ""
            for n in graph["nodes"]:
                if n["id"] == link["source"]:
                    src_type = n.get("type", "")
                if n["id"] == link["target"]:
                    tgt_type = n.get("type", "")

            if link["kind"] == "listens" and bridge_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})
            if link["kind"] in ("pinned-model", "default-model") and litellm_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})
            if link["kind"] == "authenticates-via" and authsome_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})
            if link["kind"] == "fallback" and litellm_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})

        live_set = set()
        for e in active_edges:
            live_set.add(e["source"])
            live_set.add(e["target"])
        live_nodes = list(live_set)

    roundtrip = {}
    cache_file = SPIKE_DIR / ".roundtrip_cache.json"
    try:
        if cache_file.exists():
            roundtrip = json.loads(cache_file.read_text())
    except Exception:
        pass

    return {"active_edges": active_edges, "live_nodes": live_nodes,
            "bridge_alive": bridge_alive, "authsome_alive": authsome_alive,
            "litellm_alive": litellm_alive,
            "roundtrip": roundtrip.get("ops", {}),
            "reachable_nodes": [n["id"] for n in graph.get("nodes", [])
                               if n.get("reachable")] if graph_path.exists() else []}


def list_clusters() -> list:
    """Return all cluster folders with their project.md front-matter.

    Tries CRM API first (source of truth), falls back to local YAML files.
    """
    # Try CRM API first
    crm_clusters = fetch_clusters_from_crm()
    if crm_clusters:
        return crm_clusters

    # Fallback to local YAML files
    clusters_dir = SPIKE_DIR / "clusters"
    if not clusters_dir.exists():
        return []
    result = []
    for d in sorted(clusters_dir.iterdir()):
        if not d.is_dir():
            continue
        cluster_yaml = d / "cluster.yaml"
        project_md = d / "project.md"
        if not cluster_yaml.exists():
            continue
        entry = {"name": d.name}
        if project_md.exists():
            try:
                text = project_md.read_text()
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end > 0:
                        fm = yaml_safe_load(text[3:end])
                        entry["goal"] = fm.get("goal", "")
                        entry["status"] = fm.get("status", "")
                        entry["handoff_pct"] = fm.get("handoff_pct", 0)
                        entry["data_connectors"] = fm.get("data_connectors", [])
            except Exception:
                pass
        result.append(entry)
    return result


def yaml_safe_load(text: str) -> dict:
    """Minimal YAML front-matter parser — avoids full yaml import for simple cases."""
    result = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
            elif val.isdigit():
                val = int(val)
            result[key] = val
    return result


def build_manifest(cluster_name: str) -> dict | None:
    """Build the agent graph manifest for a cluster.

    Tries CRM API first (source of truth), falls back to local build_live_graph.py.
    """
    # Try CRM API first
    crm_data = fetch_manifest_from_crm(cluster_name)
    if crm_data:
        return _transform_crm_manifest(cluster_name, crm_data)

    # Fallback to local build
    result = subprocess.run(
        [BUILDER_PY, str(SPIKE_DIR / "build_live_graph.py"), "--cluster", cluster_name],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _transform_crm_manifest(cluster_name: str, crm_data: dict) -> dict:
    """Transform CRM API data into graph manifest format (nodes + links)."""
    agents = crm_data.get("agents", {})
    shared = crm_data.get("shared", {})
    config = crm_data.get("cluster_config", {})

    nodes = []
    links = []

    # Shared tools
    for t in shared.get("tools", []):
        nodes.append({"id": f"tool:{t}", "name": t, "kind": "tool", "shared": True,
                       "type": "tool", "state": "built", "gates": {},
                       "contract": {"accepts": ["tool_call"], "emits": ["tool_result"]},
                       "role": "plain", "reachable": False,
                       "artifact": "components/src/forsch/adk_components/tools/*.py"})

    # Shared models
    for m in shared.get("models", []):
        nodes.append({"id": f"model:{m}", "name": m, "kind": "logic", "shared": True,
                       "type": "logic", "state": "built", "gates": {},
                       "contract": {"accepts": [], "emits": []},
                       "role": "plain", "reachable": False,
                       "artifact": "LiteLLM config"})

    # Authsome + connections
    nodes.append({"id": "authsome", "name": "authsome (broker)", "kind": "database",
                   "shared": True, "type": "database", "state": "live", "gates": {},
                   "contract": {"accepts": ["query"], "emits": ["data"]},
                   "role": "plain", "reachable": False, "artifact": "authsome vault"})
    connections = shared.get("connections", {})
    for cid, cname in connections.items():
        nodes.append({"id": f"cred:{cid}", "name": cname, "kind": "database",
                       "shared": True, "type": "database", "state": "built", "gates": {},
                       "contract": {"accepts": ["query"], "emits": ["data"]},
                       "role": "plain", "reachable": False, "artifact": "authsome vault"})
        links.append({"source": "authsome", "target": f"cred:{cid}", "kind": "brokers"})

    # Agents
    for aid, a in agents.items():
        nid = f"agent:{aid}"
        model = a.get("model", "")
        nodes.append({"id": nid, "name": aid, "kind": "agent",
                       "type": "agent", "state": "built",
                       "model": model,
                       "gates": {"L0": True, "L1": True, "L2": True, "L3": True},
                       "contract": {"accepts": ["instruction"], "emits": ["response", "tool_call"]},
                       "role": a.get("role", "plain"), "reachable": False,
                       "workspace": a.get("workspace") or "",
                       "artifact": f"agents/{aid}/src/forsch/agent_{aid}/agent.py"})

        # Link agent to tools
        for t in a.get("tools", []):
            if f"tool:{t}" in [n["id"] for n in nodes]:
                links.append({"source": nid, "target": f"tool:{t}", "kind": "uses"})

        # Link agent to model
        if model and f"model:{model}" in [n["id"] for n in nodes]:
            links.append({"source": nid, "target": f"model:{model}", "kind": "pinned-model"})

        # Channels
        for c in a.get("discord_channels", []):
            cnid = f"chan:{c}"
            if cnid not in [n["id"] for n in nodes]:
                nodes.append({"id": cnid, "name": c, "kind": "intake",
                               "type": "intake", "state": "built", "gates": {},
                               "contract": {"accepts": ["external_message"],
                                            "emits": ["routed_message"]},
                               "role": "plain", "reachable": False,
                               "artifact": "Discord channel config"})
            links.append({"source": nid, "target": cnid, "kind": "listens"})

    return {
        "version": 2,
        "cluster": cluster_name,
        "nodes": nodes,
        "links": links,
        "node_count": len(nodes),
        "link_count": len(links),
        "meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": f"CRM API (forsch_frontiers.sync.agent_graph)",
            "cluster": cluster_name,
        },
    }


def new_cluster(name: str) -> dict:
    """Scaffold a new cluster directory with cluster.yaml + project.md."""
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        return {"ok": False, "error": "invalid cluster name (a-z, 0-9, -, _)"}
    cluster_dir = SPIKE_DIR / "clusters" / name
    if cluster_dir.exists():
        return {"ok": False, "error": f"cluster '{name}' already exists"}
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / "cluster.yaml").write_text(f"# {name} cluster\nname: {name}\ndescription: ''\nmembers: []\nconfig:\n  default_model: gpt-5.5\n")
    (cluster_dir / "project.md").write_text(f"---\ngoal: ''\nstatus: blank\nhandoff_pct: 0\ndata_connectors: []\n---\n# {name}\n\nNew cluster.\n")
    return {"ok": True, "name": name}


def add_agent_to_cluster(cluster_name: str, agent_id: str) -> dict:
    """Append an agent id to a cluster's membership list (reference, not copy)."""
    cluster_yaml = SPIKE_DIR / "clusters" / cluster_name / "cluster.yaml"
    if not cluster_yaml.exists():
        return {"ok": False, "error": f"cluster '{cluster_name}' not found"}
    registry_yaml = SPIKE_DIR / "registry" / "agents" / "agents.yaml"
    if registry_yaml.exists():
        import yaml
        registry = (yaml.safe_load(registry_yaml.read_text()) or {}).get("agents", {})
        if agent_id not in registry:
            return {"ok": False, "error": f"agent '{agent_id}' not in registry"}
    text = cluster_yaml.read_text()
    if f"- {agent_id}" in text:
        return {"ok": True, "name": cluster_name, "agent_id": agent_id, "already_member": True}
    if "members: []" in text:
        new_text = text.replace("members: []", f"members:\n  - {agent_id}")
        cluster_yaml.write_text(new_text)
        return {"ok": True, "name": cluster_name, "agent_id": agent_id}
    lines = text.split("\n")
    new_lines = []
    in_members = False
    appended = False
    for line in lines:
        if line.strip().startswith("members:") and not in_members:
            in_members = True
            new_lines.append(line)
            continue
        if in_members and line.strip().startswith("- "):
            new_lines.append(line)
            continue
        if in_members and not line.strip().startswith("- "):
            new_lines.append(f"  - {agent_id}")
            appended = True
            in_members = False
        new_lines.append(line)
    if in_members and not appended:
        new_lines.append(f"  - {agent_id}")
    cluster_yaml.write_text("\n".join(new_lines) + "\n")
    return {"ok": True, "name": cluster_name, "agent_id": agent_id}


# ── Hubert Chat endpoint ──

def chat_with_hubert(message: str, session_id: str | None = None) -> dict:
    """Send a message to Hubert via hermes chat -q and return the response.

    Loads SOUL.md and rules so Hubert responds as Hubert, not generic Hermes.
    Context prefix tells Hubert he's in the Builder Cockpit.
    """
    context_msg = (
        "[Builder Cockpit context] You are Hubert, responding inside the "
        "Live Agent Graph Builder Cockpit chat sidecar. "
        "The user is interacting with the agent graph visualization. "
        "Stay in character. Be concise. No bullets in chat. "
        "If asked about agents/graph/clusters, reference the live data.\n\n"
        f"User: {message}"
    )
    cmd = ["hermes", "chat", "-q", context_msg, "--quiet", "--source", "tool",
           "-m", "gpt-5.5", "--provider", "custom",
           "-t", "terminal,file,web,skills,search,session_search,memory,todo,delegation"]
    if session_id:
        cmd.extend(["--resume", session_id])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(WS))
        if result.returncode == 0:
            # Parse session info from output
            output = result.stdout.strip()
            new_session_id = None
            for line in output.split("\n"):
                if "session:" in line.lower():
                    new_session_id = line.split("session:")[-1].strip()
                    break
            return {"ok": True, "response": output, "session_id": new_session_id or session_id}
        return {"ok": False, "error": result.stderr[:500] or f"exit {result.returncode}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout after 120s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Box JSON API stubs (cockpit ADK-builder) ──

def _derive_agent_status(agent_id: str) -> str:
    """Derive agent status from file existence + importability (via adk-bridge container)."""
    pkg = WS / "agents" / agent_id / "src" / f"forsch/agent_{agent_id}" / "agent.py"
    if not pkg.exists():
        return "blank"
    # Import check runs inside the adk-bridge container (has google-adk installed)
    try:
        r = subprocess.run(
            ["docker", "exec", "adk-bridge", "python3", "-c",
             f"import sys; sys.path.insert(0, '/workspace/agents/{agent_id}/src'); from forsch.agent_{agent_id}.agent import root_agent; print(root_agent.name)"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return "built"
        return "error"
    except Exception:
        return "error"


def _get_agent_config(agent_id: str) -> dict:
    """Read real agent config from agents.yaml + derive status.

    Uses the factory venv's Python (which has pyyaml) via subprocess to avoid
    depending on system-level pyyaml.
    """
    manifest_path = WS / "agent_specs" / "agents.yaml"
    if not manifest_path.exists():
        return {"ok": False, "error": "agents.yaml not found"}
    py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
    pkg_path = WS / "agents" / agent_id / "src" / f"forsch/agent_{agent_id}" / "agent.py"
    script = f"""import json, yaml, pathlib
raw = yaml.safe_load(open({str(manifest_path)!r})) or {{}}
defaults = raw.get('defaults') or {{}}
agents_raw = raw.get('agents') or {{}}
agent_id = {agent_id!r}
if agent_id not in agents_raw:
    print(json.dumps({{'ok': False, 'error': f'unknown agent: {{agent_id}}'}}))
    raise SystemExit(0)
spec = {{**defaults, **(agents_raw[agent_id] or {{}})}}
tools_raw = spec.get('tools') or []
tools = [t.rsplit('.', 1)[-1] for t in tools_raw]
status = 'built' if pathlib.Path({str(pkg_path)!r}).exists() else 'blank'
print(json.dumps({{'ok': True, 'agent': {{
    'id': agent_id,
    'adk_name': spec.get('adk_name', f'{{agent_id}}_agent'),
    'description': spec.get('description', ''),
    'model': spec.get('model', ''),
    'model_code': spec.get('model_code', ''),
    'instruction': (spec.get('instruction', '') or '').strip(),
    'tools': tools,
    'safety_level': spec.get('safety_level', 'read_only'),
    'purpose': spec.get('purpose', ''),
    'group': spec.get('group', ''),
    'smoke_prompts': spec.get('smoke_prompts') or [],
    'package': spec.get('package', ''),
    'web_entrypoint': spec.get('web_entrypoint', ''),
    'discord_channels': spec.get('discord_channels') or [],
    'status': status,
}}}}))"""
    try:
        r = subprocess.run([py, "-c", script], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
        return {"ok": False, "error": f"config read failed: {r.stderr[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _save_agent_config(params: dict) -> dict:
    """Save agent config to agents.yaml + regenerate both files via editor.update_agent().

    If the agent doesn't exist yet, auto-spawns it first (so the CRM UI's first
    "Save" is also the create step — no separate spawn endpoint needed).
    """
    agent_id = params.get("agent_id", [""])[0]
    if not agent_id:
        return {"ok": False, "error": "missing agent_id"}
    # tools can be: list (direct call), comma-separated string (HTTP form), or None
    tools_val = params.get("tools", [None])
    if isinstance(tools_val, list) and len(tools_val) == 1 and isinstance(tools_val[0], str) and "," in tools_val[0]:
        tools = [t.strip() for t in tools_val[0].split(",") if t.strip()]
    elif isinstance(tools_val, list) and tools_val and tools_val[0] is not None:
        tools = tools_val if isinstance(tools_val[0], list) else tools_val
    else:
        tools = None
    instruction = params.get("instruction", [None])[0]
    model = params.get("model", [None])[0]
    group = params.get("group", [None])[0]
    description = params.get("description", [None])[0]
    patch = {}
    if instruction is not None:
        patch["instruction"] = instruction
    if tools is not None:
        patch["tools"] = tools
    if model is not None:
        patch["model"] = model
    if group is not None:
        patch["group"] = group
    if not patch:
        return {"ok": False, "error": "no fields to update"}

    # Auto-spawn if the agent doesn't exist yet (first save = create)
    mpath = WS / "agent_specs" / "agents.yaml"
    agent_exists = False
    if mpath.exists():
        # Check via builder venv (has ruamel.yaml) — system Python doesn't
        builder_py = str(WS / "builder" / ".venv" / "bin" / "python3")
        if not Path(builder_py).exists():
            builder_py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
        check = subprocess.run(
            [builder_py, "-c",
             f"from ruamel.yaml import YAML; d=YAML().load(open({str(mpath)!r})); "
             f"print('yes' if {agent_id!r} in (d.get('agents') or {{}}) else 'no')"],
            capture_output=True, text=True, cwd=str(WS), timeout=10,
        )
        agent_exists = (check.stdout.strip() == "yes")
    if not agent_exists:
        py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
        spawn_result = subprocess.run(
            [py, str(SPIKE_DIR / "spawn_agent.py"), agent_id,
             "--model", model or "gpt-5.5",
             "--description", description or f"{agent_id} agent"],
            capture_output=True, text=True, cwd=str(WS), timeout=30,
        )
        if spawn_result.returncode != 0:
            return {"ok": False, "error": f"spawn failed: {spawn_result.stderr[:500]}"}

    builder_src = str(WS / "builder" / "src")
    builder_py = str(WS / "builder" / ".venv" / "bin" / "python3")
    if not Path(builder_py).exists():
        builder_py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
    script = (
        f"import json, sys; sys.path.insert(0, {builder_src!r});"
        "from forsch.adk_builder.editor import update_agent;"
        f"r = update_agent({str(WS)!r}, {agent_id!r}, {patch!r});"
        "print(json.dumps(r))"
    )
    try:
        r = subprocess.run(
            [builder_py, "-c", script],
            capture_output=True, text=True, cwd=str(WS), timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
        return {"ok": False, "error": f"save failed: {r.stderr[:500]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "save timed out (30s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _list_agent_tools() -> dict:
    """List real tools from the ADK components directory via AST parsing."""
    import ast
    tools = []
    comp = WS / "components" / "src" / "forsch" / "adk_components"
    if not comp.is_dir():
        return {"ok": True, "tools": []}
    for py in sorted(comp.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        try:
            tree = ast.parse(py.read_text())
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                doc = ast.get_docstring(node) or ""
                summary = doc.strip().splitlines()[0][:90] if doc.strip() else ""
                tools.append({
                    "name": node.name,
                    "summary": summary,
                    "file": str(py),
                    "wireable": True,
                })
    return {"ok": True, "tools": tools}


def _list_agent_models() -> dict:
    """Query LiteLLM proxy for available models, with static fallback."""
    import urllib.request
    key = os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("LITELLM_HERMES_KEY") or ""
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:4000/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = sorted(m["id"] for m in data.get("data", []))
        if models:
            return {"ok": True, "models": models}
    except Exception:
        pass
    return {
        "ok": True,
        "models": [
            "gpt-5.5", "gpt-5.4", "gpt-4.1", "glm-5.2", "glm-5.1",
            "deepseek-v4-pro", "deepseek-v4-flash", "gemini-3-pro-preview",
            "gemini-3-flash-preview", "kimi-k2.6", "kimi-k2.7-code",
            "minimax-m3", "qwen3-coder-480b", "cerebras-120b",
        ],
    }


def _generate_agent(agent_id: str) -> dict:
    """Run Factory apply + verify for an agent. Returns status=built only on verified import."""
    if not agent_id:
        return {"ok": False, "error": "missing agent_id"}
    py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
    manifest = str(WS / "agent_specs" / "agents.yaml")
    env = os.environ.copy()
    components_src = str(WS / "components" / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = components_src + ":" + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = components_src
    # Step 1: Run factory apply (validates + writes package)
    apply_output = ""
    try:
        r = subprocess.run(
            [py, "-m", "forsch.adk_factory.cli", "apply",
             "--agent", agent_id, "--manifest", manifest, "--workspace", str(WS)],
            capture_output=True, text=True, cwd=str(WS), timeout=60, env=env,
        )
        apply_output = r.stdout + r.stderr
        if r.returncode != 0:
            return {"ok": False, "error": f"factory apply failed: {apply_output[:500]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "factory apply timed out (60s)"}
    except Exception as e:
        return {"ok": False, "error": f"factory apply failed: {e}"}
    # Step 2: Verify — check file exists + import works
    status = _derive_agent_status(agent_id)
    pkg = WS / "agents" / agent_id / "src" / f"forsch/agent_{agent_id}" / "agent.py"
    files = []
    if pkg.exists():
        files.append(f"agents/{agent_id}/src/forsch/agent_{agent_id}/agent.py")
    web_yaml = WS / "web_agents" / agent_id / "root_agent.yaml"
    if web_yaml.exists():
        files.append(f"web_agents/{agent_id}/root_agent.yaml")
    # Step 3: Import check for detailed verify info (inside adk-bridge container)
    import_ok = False
    smoke_ok = None
    verify_error = None
    try:
        r2 = subprocess.run(
            ["docker", "exec", "adk-bridge", "python3", "-c",
             f"import sys; sys.path.insert(0, '/workspace/agents/{agent_id}/src'); from forsch.agent_{agent_id}.agent import root_agent; print(root_agent.name)"],
            capture_output=True, text=True, timeout=10,
        )
        if r2.returncode == 0:
            import_ok = True
        else:
            verify_error = r2.stderr[:500] if r2.stderr else "import failed"
    except Exception as e:
        verify_error = str(e)
    return {
        "ok": True,
        "agent": agent_id,
        "status": status,
        "files": files,
        "verify": {
            "import_ok": import_ok,
            "smoke_ok": smoke_ok,
            "error": verify_error,
        },
        "apply_output": apply_output[:500] if apply_output else "",
    }


def _verify_agent(agent_id: str) -> dict:
    """Check agent verification status: file existence + import check."""
    if not agent_id:
        return {"ok": False, "error": "missing agent_id"}
    pkg = WS / "agents" / agent_id / "src" / f"forsch/agent_{agent_id}" / "agent.py"
    web_yaml = WS / "web_agents" / agent_id / "root_agent.yaml"
    package_exists = pkg.exists()
    files = []
    if package_exists:
        files.append(f"agents/{agent_id}/src/forsch/agent_{agent_id}/agent.py")
    if web_yaml.exists():
        files.append(f"web_agents/{agent_id}/root_agent.yaml")
    if not package_exists:
        return {
            "ok": True,
            "agent": agent_id,
            "status": "blank",
            "package_exists": False,
            "import_ok": False,
            "smoke_ok": None,
            "last_verify": None,
            "files": [],
        }
    # Package exists — run import check inside adk-bridge container
    import_ok = False
    smoke_ok = None
    agent_name = None
    verify_error = None
    try:
        r = subprocess.run(
            ["docker", "exec", "adk-bridge", "python3", "-c",
             f"import sys; sys.path.insert(0, '/workspace/agents/{agent_id}/src'); from forsch.agent_{agent_id}.agent import root_agent; print(root_agent.name)"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            import_ok = True
            agent_name = r.stdout.strip()
        else:
            verify_error = r.stderr[:500] if r.stderr else "import failed"
    except Exception as e:
        verify_error = str(e)
    # Determine status
    if import_ok:
        # Check if name matches adk_name from manifest (via factory venv for pyyaml)
        expected_name = f"{agent_id}_agent"
        manifest_path = WS / "agent_specs" / "agents.yaml"
        if manifest_path.exists():
            py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
            script = (
                "import json, yaml;"
                f"raw = yaml.safe_load(open({str(manifest_path)!r})) or {{}};"
                f"spec = (raw.get('agents') or {{}}).get({agent_id!r}) or {{}};"
                "print(spec.get('adk_name', ''))"
            )
            try:
                r = subprocess.run([py, "-c", script], capture_output=True, text=True, timeout=10)
                if r.returncode == 0 and r.stdout.strip():
                    expected_name = r.stdout.strip()
            except Exception:
                pass
        status = "built" if agent_name == expected_name else "error"
        if status == "error":
            verify_error = f"name mismatch: expected '{expected_name}', got '{agent_name}'"
    else:
        status = "error"
    from datetime import datetime, timezone
    last_verify = datetime.now(timezone.utc).isoformat() if import_ok else None
    return {
        "ok": True,
        "agent": agent_id,
        "status": status,
        "package_exists": True,
        "import_ok": import_ok,
        "smoke_ok": smoke_ok,
        "last_verify": last_verify,
        "files": files,
        "error": verify_error,
    }


def _safe_agent_id(agent_id: str) -> str:
    """Validate agent_id contains only safe characters."""
    if not agent_id or not agent_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"invalid agent_id: {agent_id!r}")
    return agent_id


def _list_agent_evalsets(agent_id: str) -> dict:
    """List evalsets for an agent and return last run result."""
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
            evalsets.append({
                "id": path.stem.replace(".evalset", ""),
                "path": str(path.relative_to(SPIKE_DIR)),
                "cases": cases,
            })
    last_path = EVAL_RUNS_DIR / agent_id / "last.json"
    last_run = json.loads(last_path.read_text()) if last_path.exists() else None
    return {"ok": True, "agent_id": agent_id, "evalsets": evalsets, "last_run": last_run}


def _run_agent_eval(agent_id: str, evalset_id: str | None = None) -> dict:
    """Run an eval for an agent. Honest fail if no runner is wired."""
    agent_id = _safe_agent_id(agent_id)
    # First pass: no fake green. If a real runner is not available, fail honestly.
    result = {
        "ok": False,
        "agent_id": agent_id,
        "evalset_id": evalset_id or "default",
        "trajectory_pass": False,
        "final_response_pass": False,
        "score": 0.0,
        "error": "eval runner not wired — install ADK eval or roundtrip_check",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out_dir = EVAL_RUNS_DIR / agent_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last.json").write_text(json.dumps(result, indent=2))
    return result


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SPIKE_DIR), **kwargs)

    def _check_secret(self) -> bool:
        """Return True if the request carries the correct X-Graph-Secret header.

        Fails closed: if GRAPH_SERVER_SECRET is not set, all mutating requests are refused.
        Uses hmac.compare_digest to prevent timing attacks.
        """
        if not GRAPH_SECRET:
            return False  # fail closed — no secret configured means no access
        req_secret = self.headers.get("X-Graph-Secret", "")
        return hmac.compare_digest(req_secret, GRAPH_SECRET)

    def _is_mutating(self, path: str) -> bool:
        """Return True for endpoints that mutate state (require auth + no CORS)."""
        return path in ("/spawn", "/wire", "/save-agent", "/promote",
                        "/new-cluster", "/add-agent", "/chat",
                        "/agent-config", "/agent-generate", "/agent-eval-run")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in ("/pulse", "/pulse/"):
            self._json_response(200, get_pulse())
        elif path in ("/clusters", "/clusters/"):
            self._json_response(200, list_clusters())
        elif path == "/graph-secret":
            # Serve the secret to the browser for same-origin API calls.
            # In CRM embed the proxy injects it server-side; here the browser needs it.
            self._json_response(200, {"secret": GRAPH_SECRET or ""})
        elif path == "/chat-token":
            # Serve the bridge CHAT_TOKEN so the browser can authenticate the Gradio iframe.
            # In CRM embed the proxy injects it server-side; here the browser needs it.
            self._json_response(200, {"token": _chat_token(), "base": CHAT_BASE_URL})
        elif path == "/manifest":
            qs = parse_qs(parsed.query)
            cluster = qs.get("cluster", [None])[0]
            if not cluster:
                self._json_response(400, {"error": "missing ?cluster=name"})
                return
            manifest = build_manifest(cluster)
            if manifest is None:
                self._json_response(404, {"error": f"cluster '{cluster}' not found or build failed"})
                return
            self._json_response(200, manifest)
        elif path == "/models":
            import urllib.request
            try:
                req = urllib.request.Request("http://127.0.0.1:4000/v1/models")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    models = [m["id"] for m in data.get("data", [])]
                    self._json_response(200, {"models": sorted(models)})
            except Exception:
                self._json_response(200, {"models": [
                    "mimo-v2.5", "mimo-v2.5-pro", "gpt-5.5", "gpt-5.4", "gpt-4.1",
                    "deepseek-v4-pro", "deepseek-v4-flash", "glm-5.2",
                    "gemini-3-pro-preview", "gemini-3-flash-preview",
                    "nvidia-deepseek-v4-flash", "qwen3-coder:480b",
                ]})
        elif path in ("/agent-config", "/agent-tools", "/agent-models", "/agent-verify", "/agent-evals") and GRAPH_SECRET and not self._check_secret():
            # Only gate when a secret is configured (prod/CRM embed).
            # Standalone dev mode (no secret) leaves these read-only endpoints open.
            self._json_response(403, {"ok": False, "error": "forbidden: X-Graph-Secret required"})
        elif path == "/agent-config":
            qs = parse_qs(parsed.query)
            agent_id = qs.get("agent_id", [None])[0]
            if not agent_id:
                self._json_response(400, {"ok": False, "error": "missing ?agent_id=<id>"})
                return
            self._json_response(200, _get_agent_config(agent_id))
        elif path == "/agent-tools":
            self._json_response(200, _list_agent_tools())
        elif path == "/agent-models":
            self._json_response(200, _list_agent_models())
        elif path == "/agent-verify":
            qs = parse_qs(parsed.query)
            agent_id = qs.get("agent_id", [None])[0]
            if not agent_id:
                self._json_response(400, {"ok": False, "error": "missing ?agent_id=<id>"})
                return
            self._json_response(200, _verify_agent(agent_id))
        elif path == "/agent-evals":
            qs = parse_qs(parsed.query)
            agent_id = qs.get("agent_id", [None])[0]
            if not agent_id:
                self._json_response(400, {"ok": False, "error": "missing ?agent_id=<id>"})
                return
            try:
                self._json_response(200, _list_agent_evalsets(agent_id))
            except ValueError as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length else ""
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                raw = json.loads(body) if body else {}
                # Normalize to parse_qs shape: {key: [value]}
                params = {k: [v] if not isinstance(v, list) else v for k, v in raw.items()}
            except json.JSONDecodeError:
                self._json_response(400, {"error": "invalid JSON"})
                return
        else:
            params = parse_qs(body)

        if parsed.path == "/spawn":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            agent_id = params.get("id", [None])[0]
            model = params.get("model", ["gpt-5.5"])[0]
            description = params.get("description", [f"{agent_id} agent"])[0] if agent_id else ""

            if not agent_id:
                self._json_response(400, {"error": "missing id"})
                return

            py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
            result = subprocess.run(
                [py, str(SPIKE_DIR / "spawn_agent.py"), agent_id,
                 "--model", model, "--description", description],
                capture_output=True, text=True, cwd=str(WS),
            )
            if result.returncode == 0:
                # Extract workspace path from spawn output
                workspace_path = None
                for line in result.stdout.splitlines():
                    if line.strip().startswith("profile:"):
                        workspace_path = line.split("profile:")[-1].strip().split()[0]
                        break
                resp = {"ok": True, "agent_id": agent_id, "output": result.stdout}
                if workspace_path:
                    resp["workspace"] = workspace_path
                self._json_response(200, resp)
            else:
                self._json_response(500, {"ok": False, "error": result.stderr[:500]})

        elif parsed.path == "/wire":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            source = params.get("source", [None])[0]
            target = params.get("target", [None])[0]
            if not source or not target:
                self._json_response(400, {"error": "missing source or target"})
                return
            # Fallback to local contract_check.py
            result = subprocess.run(
                [sys.executable, str(SPIKE_DIR / "contract_check.py"), source, target],
                capture_output=True, text=True,
            )
            check = json.loads(result.stdout) if result.returncode in (0, 1) else {"valid": False, "error": result.stderr}
            self._json_response(200, check)

        elif parsed.path == "/save-agent":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            agent_id = params.get("agent_id", [None])[0]
            field = params.get("field", [None])[0]
            value = params.get("value", [None])[0]
            if not agent_id or not field:
                self._json_response(400, {"error": "missing agent_id or field"})
                return
            # Map frontend field names to CRM field names
            field_map = {
                "model": "model", "title": "title", "role": "role",
                "status": "status", "safety_level": "safety_level",
            }
            if field not in field_map:
                self._json_response(400, {"error": f"unknown field: {field}"})
                return
            # Deterministic: call CRM update_agent, no LLM in the loop
            result = _crm_post("forsch_frontiers.sync.agent_graph.update_agent", {
                "agent_id": agent_id,
                field_map[field]: value or "",
            })
            if result and result.get("message", {}).get("ok"):
                self._json_response(200, {"ok": True, "agent_id": agent_id, "field": field, "value": value})
            else:
                err = (result or {}).get("message", {}).get("error", "CRM call failed")
                self._json_response(500, {"error": str(err)})

        elif parsed.path == "/models":
            # Fetch model list from LiteLLM proxy
            import urllib.request
            try:
                req = urllib.request.Request("http://127.0.0.1:4000/v1/models")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    models = [m["id"] for m in data.get("data", [])]
                    self._json_response(200, {"models": sorted(models)})
            except Exception:
                # Hardcoded fallback if proxy unreachable
                self._json_response(200, {"models": [
                    "mimo-v2.5", "mimo-v2.5-pro", "gpt-5.5", "gpt-5.4", "gpt-4.1",
                    "deepseek-v4-pro", "deepseek-v4-flash", "glm-5.2",
                    "gemini-3-pro-preview", "gemini-3-flash-preview",
                    "nvidia-deepseek-v4-flash", "qwen3-coder:480b",
                    "groq-compound-mini", "groq-gpt-oss-20b",
                    "groq-llama-4-scout", "groq-llama-8b",
                    "nvidia-llama-vision-11b", "nvidia-llama-vision-90b",
                    "nvidia-nemotron-30b", "mistral-large",
                ]})

        elif parsed.path == "/promote":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            agent_id = params.get("agent_id", [None])[0]
            target_role = params.get("target_role", [None])[0]
            if not agent_id or not target_role:
                self._json_response(400, {"error": "missing agent_id or target_role"})
                return
            result = promote_agent(agent_id, target_role)
            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/new-cluster":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            name = params.get("name", [None])[0]
            if not name:
                self._json_response(400, {"error": "missing name"})
                return
            result = new_cluster(name)
            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/add-agent":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            cluster = params.get("cluster", [None])[0]
            agent_id = params.get("agent_id", [None])[0]
            if not cluster or not agent_id:
                self._json_response(400, {"error": "missing cluster or agent_id"})
                return
            result = add_agent_to_cluster(cluster, agent_id)
            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/chat":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            # Parse JSON body (CRM proxy sends JSON, browser sends form-encoded)
            principal = None
            message = None
            session_id = None
            try:
                json_body = json.loads(body) if body else {}
                principal = json_body.get("principal")
                message = json_body.get("message")
                session_id = json_body.get("session_id")
            except json.JSONDecodeError:
                pass
            # Fallback to form-encoded (browser direct, deprecated but kept for transition)
            if not message:
                message = params.get("message", [None])[0]
                session_id = params.get("session_id", [None])[0]
            if not message:
                self._json_response(400, {"error": "missing message"})
                return
            if not principal:
                principal = "unknown"

            # Rate limit
            if not _check_rate(principal):
                self._json_response(429, {"error": "rate limit exceeded"})
                return

            # Session ownership
            if session_id:
                with _session_lock:
                    entry = _session_owners.get(session_id)
                    if entry:
                        owner, _ = entry
                        if owner != principal:
                            self._json_response(403, {"error": "session owned by another principal"})
                            return

            result = chat_with_hubert(message, session_id)

            # Track session ownership
            if result.get("ok") and result.get("session_id"):
                with _session_lock:
                    _session_owners[result["session_id"]] = (principal, time.time())

            outcome = "ok" if result.get("ok") else f"error: {result.get('error', 'unknown')[:100]}"
            _audit(principal, message, session_id, outcome)
            self._json_response(200 if result.get("ok") else 500, result)

        elif parsed.path == "/agent-config":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            self._json_response(200, _save_agent_config(params))

        elif parsed.path == "/agent-generate":
            if not self._check_secret():
                self._json_response(401, {"error": "unauthorized"})
                return
            agent_id = params.get("agent_id", [None])[0]
            if not agent_id:
                self._json_response(400, {"ok": False, "error": "missing agent_id"})
                return
            self._json_response(200, _generate_agent(agent_id))

        elif parsed.path == "/agent-eval-run":
            if not self._check_secret():
                self._json_response(403, {"ok": False, "error": "forbidden: X-Graph-Secret required"})
                return
            agent_id = params.get("agent_id", [None])[0]
            evalset_id = params.get("evalset_id", [None])[0]
            if not agent_id:
                self._json_response(400, {"ok": False, "error": "agent_id required"})
                return
            try:
                self._json_response(200, _run_agent_eval(agent_id, evalset_id))
            except ValueError as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})

        else:
            self._json_response(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        # CORS: read-only endpoints get pinned origin; mutating endpoints get none
        path = self.path.rstrip("/") or "/"
        if not self._is_mutating(path):
            self.send_header("Access-Control-Allow-Origin", CRM_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Graph-Secret")
        self.end_headers()

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        # CORS: read-only endpoints get pinned origin; mutating endpoints get none
        if not self._is_mutating(self.path.rstrip("/") or "/"):
            self.send_header("Access-Control-Allow-Origin", CRM_ORIGIN)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass  # quiet


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Live Agent Graph server on http://127.0.0.1:{port} (localhost only)")
    server.serve_forever()
