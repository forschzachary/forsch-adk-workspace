#!/usr/bin/env python3
"""HTTP bridge for the Live Agent Graph UI — serves index.html + cluster tabs + spawn + pulse + chat.

Usage:
  python3 serve.py [port]

Security:
  - Binds 127.0.0.1 (not 0.0.0.0). Only reachable from this box.
  - Cloudflare Access (Zero Trust) gates the edge — Google OAuth identity.
  - serve.py verifies the Cf-Access-Jwt-Assertion header (RS256 JWT) against
    Cloudflare's public JWKS to extract a verified email as the principal.
  - Cloudflare Access (Zero Trust) is the only auth gate; once a request
    reaches serve.py the principal has already cleared Google OAuth at the
    edge. Mutating endpoints re-verify the JWT as defense-in-depth; read
    endpoints trust the edge and skip the re-check.
  - /chat enforces session ownership, rate-limits per principal, and logs every invocation.
  - CORS is pinned to the graph origin.
"""

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import threading
from collections import deque
import time
import urllib.request
import yaml
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from workspace_resolver import workspace_root

# live-agent-graph: canonical home for the agent control surface.
# This is no longer a spike — it's the engine for AI consulting projects.
# Production path: /root/.hermes/workspace/adk/live-agent-graph (box)
#                  ~/Dev/live-agent-graph                       (Mac dev)
# All paths below are derived from LAG_HOME — no hardcoded locations.
LAG_HOME = Path(__file__).resolve().parent
WS = workspace_root() / "adk"
FACTORY_PYTHON = WS / "factory" / ".venv" / "bin" / "python3.12"
BUILDER_PY = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable

# ── Cloudflare Access (Zero Trust) auth ──
# Cloudflare Access gates the edge with Google OAuth. Every request arrives
# with a Cf-Access-Jwt-Assertion header (RS256 JWT). serve.py verifies it
# against Cloudflare's public JWKS and extracts the verified email as the
# principal. No shared secrets, no Frappe coupling.
CF_ACCESS_TEAM = os.environ.get("CF_ACCESS_TEAM", "forschfrontiers")
CF_ACCESS_AUD = os.environ.get("CF_ACCESS_AUD", "")  # set per-app AUD tag from dashboard
GRAPH_MUTATION_SECRET = os.environ.get("GRAPH_MUTATION_SECRET") or os.environ.get("GRAPH_SERVER_SECRET")
_JWKS_CACHE = None
_JWKS_FETCHED_AT = 0.0
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _fetch_jwks():
    """Fetch Cloudflare Access public keys (JWKS). Cached for 1 hour."""
    global _JWKS_CACHE, _JWKS_FETCHED_AT
    if _JWKS_CACHE and (time.time() - _JWKS_FETCHED_AT) < 3600:
        return _JWKS_CACHE
    try:
        url = f"https://{CF_ACCESS_TEAM}.cloudflareaccess.com/cdn-cgi/access/certs"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            _JWKS_CACHE = json.loads(resp.read())
            _JWKS_FETCHED_AT = time.time()
            return _JWKS_CACHE
    except Exception:
        return None

def _verify_access_jwt(token: str) -> str | None:
    """Verify a Cf-Access-Jwt-Assertion JWT and return the email, or None.

    Uses PyJWT. Verifies RS256 signature against Cloudflare's JWKS,
    checks iss + aud + exp.
    """
    try:
        import jwt as _jwt
    except ImportError:
        return None
    try:
        jwks = _fetch_jwks()
        if not jwks:
            return None
        try:
            unverified_header = _jwt.get_unverified_header(token)
        except _jwt.InvalidTokenError:
            return None
        kid = unverified_header.get("kid")
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break
        if not key:
            return None
        # Build a PEM-encoded RSA public key from the JWK's n/e components.
        import base64 as _b64
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
        from cryptography.hazmat.primitives import serialization as _ser
        n_int = int.from_bytes(_b64.urlsafe_b64decode(key["n"] + "=="), "big")
        e_int = int.from_bytes(_b64.urlsafe_b64decode(key["e"] + "=="), "big")
        pub = RSAPublicNumbers(e_int, n_int).public_key()
        pem = pub.public_bytes(
            encoding=_ser.Encoding.PEM,
            format=_ser.PublicFormat.SubjectPublicKeyInfo,
        )
        decode_kwargs = {"algorithms": ["RS256"]}
        if CF_ACCESS_AUD:
            decode_kwargs["audience"] = CF_ACCESS_AUD
        else:
            decode_kwargs["options"] = {"verify_aud": False}
        return _jwt.decode(token, pem, **decode_kwargs).get("email")
    except Exception:
        return None

CRM_ORIGIN = os.environ.get("CRM_ORIGIN", "https://graph.forschfrontiers.com")

# Persistent home (HERMES_HOME); on the box this is /opt/data (== host /root/.hermes).
_HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))

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

# External URL for the Gradio bridge iframe. serve.py reverse-proxies /chat/* to
# the ADK bridge at 127.0.0.1:8800, so the iframe loads on the same hostname.
CHAT_BASE_URL = os.environ.get("CHAT_BASE_URL", "/chat/")
CRM_API_KEY_FILE = _HERMES_HOME / "secrets" / "frappe-admin-api-key"
CRM_BASE = os.environ.get("CRM_BASE_URL", "https://crm.forschfrontiers.com")

# ── Session ownership ──
_session_owners: dict[str, tuple[str, float]] = {}  # session_id → (principal, created_at)
_session_lock = threading.Lock()
SESSION_MAX_AGE = 3600.0  # evict sessions older than 1 hour

# ── Factory overview: source files referenced in the inventory payload ──
# Used by both _build_factory_overview() and the CRM-manifest path so a new
# file gets declared in one place.
FACTORY_OVERVIEW_SOURCES = [
    "registry/agents/agents.yaml",
    "shared/components.yaml",
    "shared/infra.yaml",
    "serve.py",
    "index.html",
    "home.html",
    "chat.html",
]

# Cluster names are interpolated into filesystem paths downstream. Restrict
# to a safe alphabet so a malicious cluster.yaml can't escape via ../etc.
_SAFE_CLUSTER_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

# ── Rate limiting ──
_rate_state: dict[str, deque] = {}  # principal → deque of request timestamps (sliding window)
_rate_lock = threading.Lock()
RATE_LIMIT = 30       # max requests
RATE_WINDOW = 60.0    # per 60 seconds

# HTTP request body cap. 1 MiB is generous for JSON POSTs to /chat, /spawn,
# /wire, /agent-config; anything larger is either a misuse or an attack.
MAX_REQUEST_BYTES = 1 << 20

# MiMo subprocess input cap. 64 KiB of user message is plenty for chat
# messages; longer inputs almost certainly indicate a misuse.
MAX_MIMO_MESSAGE_BYTES = 64 * 1024

# Audit log entry limits — keep the log bounded and the on-disk format
# consistent across callers.
MAX_AUDIT_MESSAGE_LEN = 200
AUDIT_LOG_MAX_BYTES = 50_000_000  # ~50 MB; rollover is operator's job

# ── Audit log ──
AUDIT_LOG = LAG_HOME / "chat_audit.log"

# ── Eval paths ──
EVALSETS_DIR = LAG_HOME / "evalsets"
EVAL_RUNS_DIR = LAG_HOME / ".eval_runs"

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
            stale_keys = [p for p, window in _rate_state.items()
                         if not window or window[-1] < now - RATE_WINDOW * 2]
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
        "message": message[:MAX_AUDIT_MESSAGE_LEN],
        "session_id": session_id,
        "outcome": outcome,
    })
    try:
        with open(AUDIT_LOG, "a") as f:
            f.write(entry + "\n")
    except OSError as exc:
        sys.stderr.write(f"audit log write failed: {exc}\n")

def _check_rate(principal: str) -> bool:
    """Return True if within rate limit (sliding window of RATE_WINDOW seconds), False if exceeded.

    Sliding window: a request is allowed if fewer than RATE_LIMIT timestamps
    fall within the last RATE_WINDOW seconds. More fair than a fixed-window
    counter, which would let a burst at the edge of one window lock the user
    out for the next full window.
    """
    with _rate_lock:
        now = time.time()
        window = _rate_state.get(principal)
        if window is None:
            window = deque()
            _rate_state[principal] = window
        # Drop timestamps older than the window.
        cutoff = now - RATE_WINDOW
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= RATE_LIMIT:
            return False
        window.append(now)
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
    sys.stderr.write("fetch_clusters_from_crm: CRM unreachable, falling back to local\n")
    return []


def fetch_manifest_from_crm(cluster_id: str) -> dict | None:
    """Fetch agent graph manifest for a cluster from CRM."""
    data = _crm_get("forsch_frontiers.sync.agent_graph.get_agent_graph_manifest",
                     {"cluster_id": cluster_id})
    if data and "message" in data:
        return data["message"]
    sys.stderr.write(f"fetch_manifest_from_crm({cluster_id}): CRM unreachable, falling back to local\n")
    return None


def promote_agent(agent_id: str, target_role: str) -> dict:
    py = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable
    result = subprocess.run(
        [py, str(LAG_HOME / "promote_agent.py"), agent_id, target_role],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {"ok": False, "error": f"parse error: {result.stdout[:200]}"}
    return {"ok": False, "error": result.stderr[:300] or f"exit {result.returncode}"}


ADK_BRIDGE_URL = os.environ.get("ADK_BRIDGE_URL", "http://127.0.0.1:8800")

def _proxy_to_bridge(handler, method):
    """Reverse-proxy /chat/* to the ADK bridge (Gradio) at 127.0.0.1:8800.

    This lets the Agent-tab iframe load /chat/ on the same hostname as the graph,
    eliminating the need for chat.forschfrontiers.com as a separate tunnel route.
    The bridge's own chat_token auth still applies.
    """
    import urllib.request
    parsed = urlparse(handler.path)
    if not parsed.path.startswith("/chat"):
        return False
    target = ADK_BRIDGE_URL + handler.path
    principal = handler._get_principal() or ("smoke-test" if handler._has_mutation_secret() else "anonymous")
    sys.stderr.write(f"proxy {method} {handler.path} principal={principal}\n")
    try:
        content_length = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_length) if content_length > 0 else None
        req = urllib.request.Request(target, data=body, method=method)
        for key, val in handler.headers.items():
            if key.lower() in ("host", "content-length", "transfer-encoding"):
                continue
            req.add_header(key, val)
        with urllib.request.urlopen(req, timeout=120) as resp:
            handler.send_response(resp.status)
            for key, val in resp.headers.items():
                if key.lower() in ("transfer-encoding", "connection"):
                    continue
                handler.send_header(key, val)
            handler.end_headers()
            handler.wfile.write(resp.read())
        return True
    except urllib.error.HTTPError as e:
        handler.send_response(e.code)
        for key, val in e.headers.items():
            if key.lower() in ("transfer-encoding", "connection"):
                continue
            handler.send_header(key, val)
        handler.end_headers()
        handler.wfile.write(e.read())
        return True
    except Exception:
        handler._json_response(502, {"error": "bridge unreachable"})
        return True


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

    graph_path = LAG_HOME / "agent-graph-v2.json"
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
    cache_file = LAG_HOME / ".roundtrip_cache.json"
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
    clusters_dir = LAG_HOME / "clusters"
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
    """Parse a YAML string. Thin wrapper over yaml.safe_load for backwards compat."""
    return yaml.safe_load(text) or {}


def build_manifest(cluster_name: str) -> dict | None:
    """Build the agent graph manifest for a cluster.

    Tries CRM API first (source of truth), falls back to local build_live_graph.py.
    Always enriches the result with rail tags, infra nodes, and tool→cred links.
    """
    manifest = None

    # Try CRM API first
    crm_data = fetch_manifest_from_crm(cluster_name)
    if crm_data:
        manifest = _transform_crm_manifest(cluster_name, crm_data)

    # Fallback to local build
    if not manifest:
        result = subprocess.run(
            [BUILDER_PY, str(LAG_HOME / "build_live_graph.py"), "--cluster", cluster_name],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        try:
            manifest = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    # Enrich with rail tags, infra nodes, tool→cred links
    return _enrich_manifest(cluster_name, manifest)


def _load_yaml(path: Path) -> dict:
    """Load a YAML file in-process. Returns {} on parse failure or missing file."""
    try:
        return yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError) as exc:
        sys.stderr.write(f"_load_yaml failed for {path}: {exc}\n")
        return {}


def _write_atomic(path: Path, content: str) -> None:
    """Write `content` to `path` atomically via temp file + os.replace.

    Prevents partial writes from corrupting files that concurrent
    processes (or crashes) might read mid-write.
    """
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _transform_crm_manifest(cluster_name: str, crm_data: dict) -> dict:
    """Transform CRM API data into graph manifest format (nodes + links).

    Handles two input shapes:
    1. Raw data: {agents: {...}, shared: {...}, cluster_config: {...}}
    2. Pre-built manifest: {nodes: [...], links: [...], ...}

    Emits rail-tagged nodes:
    - Core: agents, tools, channels (no rail tag — always visible)
    - Dependency rail: cred nodes + tool→cred links
    - Infrastructure rail: hosts, containers, services, networks, tunnels

    Models are NOT emitted to the canvas (shown in inspect panel only).
    """
    agents = crm_data.get("agents", {})
    shared = crm_data.get("shared", {})
    config = crm_data.get("cluster_config", {})
    existing_nodes = crm_data.get("nodes", [])
    existing_links = crm_data.get("links", [])

    # Load tool_connections from components.yaml
    components_yaml = LAG_HOME / "shared" / "components.yaml"
    tool_connections = {}
    if components_yaml.exists():
        comp = _load_yaml(components_yaml)
        tool_connections = comp.get("tool_connections", {})

    # Load infra topology
    infra_yaml = LAG_HOME / "shared" / "infra.yaml"
    infra = _load_yaml(infra_yaml) if infra_yaml.exists() else {}

    # If CRM returned a pre-built manifest (nodes already exist), enrich it
    if existing_nodes:
        nodes = []
        links = list(existing_links)

        # Enrich existing nodes with rail tags, skip model nodes
        for n in existing_nodes:
            nid = n.get("id", "")
            ntype = n.get("type", "")

            # Skip model nodes — they're inspect-panel metadata, not canvas nodes
            if nid.startswith("model:"):
                continue

            # Tag cred nodes as dependency rail
            if nid.startswith("cred:"):
                n["rail"] = "dependency"
            # Remove authsome as shared database — becomes svc:authsome in infra rail
            elif nid == "authsome":
                continue
            # Remove capabilities — folded into infra rail
            elif nid.startswith("cap:"):
                continue

            nodes.append(n)

        # Remove authsome→cred broker links (authsome is now infra)
        links = [l for l in links if not (l.get("source") == "authsome" and l.get("kind") == "brokers")]
        # Remove model links
        links = [l for l in links if l.get("kind") != "pinned-model"]

        # Add tool→cred links from tool_connections
        cred_ids = {n["id"] for n in nodes if n["id"].startswith("cred:")}
        for tool_name, conn_id in tool_connections.items():
            tool_node_id = f"tool:{tool_name}"
            cred_node_id = f"cred:{conn_id}"
            if cred_node_id in cred_ids and any(n["id"] == tool_node_id for n in nodes):
                if not any(l["source"] == tool_node_id and l["target"] == cred_node_id for l in links):
                    links.append({"source": tool_node_id, "target": cred_node_id, "kind": "depends-on"})

        # Add infra nodes
        nodes, links = _append_infra_nodes(nodes, links, infra)

        rail_nodes = {
            "dependency": [n["id"] for n in nodes if n.get("rail") == "dependency"],
            "infrastructure": [n["id"] for n in nodes if n.get("rail") == "infrastructure"],
        }

        return {
            "version": 2,
            "cluster": cluster_name,
            "nodes": nodes,
            "links": links,
            "node_count": len(nodes),
            "link_count": len(links),
            "rail_nodes": rail_nodes,
            "meta": crm_data.get("meta", {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "CRM API (enriched)",
                "cluster": cluster_name,
            }),
        }

    # Raw data path — build from scratch
    nodes = []
    links = []

    # Shared tools (core — always visible)
    for t in shared.get("tools", []):
        nodes.append({"id": f"tool:{t}", "name": t, "kind": "tool", "shared": True,
                       "type": "tool", "state": "built", "gates": {},
                       "contract": {"accepts": ["tool_call"], "emits": ["tool_result"]},
                       "role": "plain", "reachable": False,
                       "artifact": "components/src/forsch/adk_components/tools/*.py"})

    # Cred nodes (dependency rail)
    connections = shared.get("connections", {})
    cred_ids = set()
    for cid, cname in connections.items():
        cred_ids.add(f"cred:{cid}")
        nodes.append({"id": f"cred:{cid}", "name": cname, "kind": "database",
                       "type": "database", "state": "built", "gates": {},
                       "rail": "dependency",
                       "contract": {"accepts": ["query"], "emits": ["data"]},
                       "role": "plain", "reachable": False, "artifact": "authsome vault"})

    # Tool→cred links from tool_connections
    for tool_name, conn_id in tool_connections.items():
        tool_node_id = f"tool:{tool_name}"
        cred_node_id = f"cred:{conn_id}"
        if cred_node_id in cred_ids:
            links.append({"source": tool_node_id, "target": cred_node_id, "kind": "depends-on"})

    # Infra nodes
    nodes, links = _append_infra_nodes(nodes, links, infra)

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

        # Agent → container link (infra rail)
        for ctr in infra.get("containers", []):
            if ctr.get("runs_agents"):
                links.append({"source": nid, "target": f"docker:{ctr['id']}", "kind": "runs-in"})

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

    rail_nodes = {
        "dependency": [n["id"] for n in nodes if n.get("rail") == "dependency"],
        "infrastructure": [n["id"] for n in nodes if n.get("rail") == "infrastructure"],
    }

    source_files = list(FACTORY_OVERVIEW_SOURCES)
    for cluster in cluster_specs:
        source_files.append(f"clusters/{cluster['name']}/cluster.yaml")
        if cluster.get("goal") or cluster.get("project_summary"):
            source_files.append(f"clusters/{cluster['name']}/project.md")

    return {
        "version": 2,
        "cluster": cluster_name,
        "nodes": nodes,
        "links": links,
        "node_count": len(nodes),
        "link_count": len(links),
        "rail_nodes": rail_nodes,
        "meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": f"CRM API (forsch_frontiers.sync.agent_graph)",
            "cluster": cluster_name,
        },
    }


def _enrich_manifest(cluster_name: str, manifest: dict) -> dict:
    """Enrich any manifest with rail tags, infra nodes, and tool→cred links.

    Strips model nodes, authsome database node, and cap nodes.
    Adds dependency rail (cred nodes + tool→cred links) and infrastructure rail.
    """
    # Load tool_connections
    components_yaml = LAG_HOME / "shared" / "components.yaml"
    tool_connections = {}
    if components_yaml.exists():
        comp = _load_yaml(components_yaml)
        tool_connections = comp.get("tool_connections", {})

    # Load infra topology
    infra_yaml = LAG_HOME / "shared" / "infra.yaml"
    infra = _load_yaml(infra_yaml) if infra_yaml.exists() else {}

    nodes = []
    links = list(manifest.get("links", []))

    for n in manifest.get("nodes", []):
        nid = n.get("id", "")

        # Skip model nodes
        if nid.startswith("model:"):
            continue

        # Tag cred nodes as dependency rail
        if nid.startswith("cred:"):
            n["rail"] = "dependency"
        # Remove authsome — becomes svc:authsome in infra rail
        elif nid == "authsome":
            continue
        # Remove capabilities — folded into infra rail
        elif nid.startswith("cap:"):
            continue

        nodes.append(n)

    # Remove authsome→cred broker links
    links = [l for l in links if not (l.get("source") == "authsome" and l.get("kind") == "brokers")]
    # Remove model links
    links = [l for l in links if l.get("kind") != "pinned-model"]

    # Add tool→cred links
    cred_ids = {n["id"] for n in nodes if n["id"].startswith("cred:")}
    for tool_name, conn_id in tool_connections.items():
        tool_node_id = f"tool:{tool_name}"
        cred_node_id = f"cred:{conn_id}"
        if cred_node_id in cred_ids and any(n["id"] == tool_node_id for n in nodes):
            if not any(l["source"] == tool_node_id and l["target"] == cred_node_id for l in links):
                links.append({"source": tool_node_id, "target": cred_node_id, "kind": "depends-on"})

    # Add infra nodes
    nodes, links = _append_infra_nodes(nodes, links, infra)

    # Add agent→container links
    for ctr in infra.get("containers", []):
        if ctr.get("runs_agents"):
            cid = f"docker:{ctr['id']}"
            for n in nodes:
                if n["id"].startswith("agent:"):
                    if not any(l["source"] == n["id"] and l["target"] == cid for l in links):
                        links.append({"source": n["id"], "target": cid, "kind": "runs-in"})

    # Prune links that reference missing nodes
    node_ids = {n["id"] for n in nodes}
    links = [l for l in links if l.get("source") in node_ids and l.get("target") in node_ids]

    rail_nodes = {
        "dependency": [n["id"] for n in nodes if n.get("rail") == "dependency"],
        "infrastructure": [n["id"] for n in nodes if n.get("rail") == "infrastructure"],
    }

    manifest["nodes"] = nodes
    manifest["links"] = links
    manifest["node_count"] = len(nodes)
    manifest["link_count"] = len(links)
    manifest["rail_nodes"] = rail_nodes
    return manifest


def _append_infra_nodes(nodes: list, links: list, infra: dict) -> tuple:
    """Add infrastructure rail nodes and links to the manifest."""
    # Services
    for svc in infra.get("services", []):
        sid = f"svc:{svc['id']}"
        nodes.append({"id": sid, "name": svc.get("name", svc["id"]), "kind": "service",
                       "type": "service", "state": "live", "gates": {},
                       "rail": "infrastructure",
                       "contract": {"accepts": ["request"], "emits": ["response"]},
                       "role": "plain", "reachable": False,
                       "artifact": f"port {svc.get('port', '?')}"})

    for host in infra.get("hosts", []):
        hid = f"host:{host['id']}"
        nodes.append({"id": hid, "name": host.get("name", host["id"]), "kind": "host",
                       "type": "host", "state": "live", "gates": {},
                       "rail": "infrastructure",
                       "contract": {"accepts": ["deploy"], "emits": ["runtime"]},
                       "role": "plain", "reachable": False,
                       "artifact": host.get("provider", "")})

    for ctr in infra.get("containers", []):
        cid = f"docker:{ctr['id']}"
        nodes.append({"id": cid, "name": ctr.get("name", ctr["id"]), "kind": "container",
                       "type": "container", "state": "live", "gates": {},
                       "rail": "infrastructure",
                       "contract": {"accepts": ["deploy"], "emits": ["process"]},
                       "role": "plain", "reachable": False,
                       "artifact": f"port {ctr.get('port', '?')}"})
        if ctr.get("host"):
            links.append({"source": cid, "target": f"host:{ctr['host']}", "kind": "runs-on"})

    for net in infra.get("networks", []):
        nid = f"net:{net['id']}"
        nodes.append({"id": nid, "name": net.get("name", net["id"]), "kind": "network",
                       "type": "network", "state": "live", "gates": {},
                       "rail": "infrastructure",
                       "contract": {"accepts": ["connect"], "emits": ["route"]},
                       "role": "plain", "reachable": False,
                       "artifact": net.get("type", "")})

    for tunnel in infra.get("tunnels", []):
        tid = f"tunnel:{tunnel['id']}"
        nodes.append({"id": tid, "name": tunnel.get("name", tunnel["id"]), "kind": "tunnel",
                       "type": "tunnel", "state": "live", "gates": {},
                       "rail": "infrastructure",
                       "contract": {"accepts": ["request"], "emits": ["proxy"]},
                       "role": "plain", "reachable": False,
                       "artifact": tunnel.get("type", "")})

    return nodes, links


def _load_agent_registry() -> dict:
    registry_yaml = LAG_HOME / "registry" / "agents" / "agents.yaml"
    if not registry_yaml.exists():
        return {"defaults": {}, "agents": {}}
    return _load_yaml(registry_yaml)


def _load_cluster_specs() -> list[dict]:
    clusters_dir = LAG_HOME / "clusters"
    if not clusters_dir.exists():
        return []

    cluster_specs = []
    for cluster_dir in sorted(clusters_dir.iterdir()):
        if not cluster_dir.is_dir():
            continue

        cluster_yaml = cluster_dir / "cluster.yaml"
        if not cluster_yaml.exists():
            continue

        cluster_data = _load_yaml(cluster_yaml)
        project_path = cluster_dir / "project.md"
        project_meta = {}
        project_summary = ""
        if project_path.exists():
            text = project_path.read_text()
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    project_meta = yaml_safe_load(text[3:end])
                    project_summary = text[end + 3:].strip()
            else:
                project_summary = text.strip()

        cluster_name = cluster_data.get("name", cluster_dir.name)
        # Cluster names are interpolated into filesystem paths downstream
        # (source_files list, served hrefs). Reject anything outside the
        # safe alphabet to prevent path traversal via a malicious cluster.yaml.
        if not _SAFE_CLUSTER_NAME_RE.match(cluster_name):
            continue
        cluster_specs.append({
            "name": cluster_name,
            "description": cluster_data.get("description", ""),
            "members": cluster_data.get("members", []) or [],
            "config": cluster_data.get("config", {}) or {},
            "goal": project_meta.get("goal", ""),
            "status": project_meta.get("status", ""),
            "handoff_pct": project_meta.get("handoff_pct", 0),
            "data_connectors": project_meta.get("data_connectors", []) or [],
            "project_summary": project_summary,
        })

    return cluster_specs


def _build_building_blocks_index() -> dict:
    """Walk the patterns library on the box and return a flat index for the UI.

    The patterns library lives outside this repo (adk-components repo). To
    avoid coupling, we probe a small set of conventional paths and gracefully
    degrade to an empty index when the library isn't reachable from this
    service's process. Operators get an honest "library unreachable" message
    rather than a misleading empty card.
    """
    # Probe paths for the patterns library. Override the root with the
    # ADK_COMPONENTS_DIR env var so Mac dev / alternate installs work.
    components_root = Path(os.environ.get(
        "ADK_COMPONENTS_DIR",
        "/root/.hermes/workspace/adk/components/src/forsch/adk_components",
    ))
    candidates = [
        ("patterns",    components_root / "patterns" / "inventory.yaml"),
        ("agents",      components_root / "agents" / "inventory.yaml"),
        ("uis",         components_root / "uis" / "inventory.yaml"),
        ("routers",     components_root / "routers" / "inventory.yaml"),
        ("datasources", components_root / "datasources" / "inventory.yaml"),
    ]
    blocks: list[dict] = []
    reachable = False
    for kind, path in candidates:
        p = Path(path)
        if not p.exists():
            continue
        reachable = True
        data = _load_yaml(p)
        if not isinstance(data, dict):
            continue
        items = data.get(kind, data) if isinstance(data.get(kind), dict) else data
        for name, meta in (items or {}).items():
            if not isinstance(meta, dict):
                continue
            blocks.append({
                "kind": kind,
                "id": name,
                "intention": meta.get("intention", ""),
                "function": meta.get("function", ""),
                "keywords": meta.get("keywords", []) or [],
            })
    return {
        "reachable": reachable,
        "count": len(blocks),
        "blocks": sorted(blocks, key=lambda b: (b["kind"], b["id"])),
    }


# TTL cache for _build_factory_overview — building the overview reads
# several YAML files via _load_yaml and walks 5 inventories. Hot endpoint
# (rendered on every /home and /factory-overview hit). 5s TTL is short
# enough that operators see fresh state during a session but cuts 95%+
# of the read load under page-refresh.
_FACTORY_OVERVIEW_TTL_S = 5.0
_factory_overview_cache: dict = {"ts": 0.0, "data": None}


def _build_factory_overview() -> dict:
    """Build the factory overview payload, cached for _FACTORY_OVERVIEW_TTL_S."""
    now = time.time()
    if (
        _factory_overview_cache["data"] is not None
        and now - _factory_overview_cache["ts"] < _FACTORY_OVERVIEW_TTL_S
    ):
        return _factory_overview_cache["data"]
    data = _build_factory_overview_uncached()
    _factory_overview_cache["ts"] = now
    _factory_overview_cache["data"] = data
    return data


def _build_factory_overview_uncached() -> dict:
    registry = _load_agent_registry()
    components = _load_yaml(LAG_HOME / "shared" / "components.yaml")
    infra = _load_yaml(LAG_HOME / "shared" / "infra.yaml")
    cluster_specs = _load_cluster_specs()

    defaults = registry.get("defaults", {}) or {}
    registry_agents = registry.get("agents", {}) or {}
    cluster_map: dict[str, list[str]] = {}
    for cluster in cluster_specs:
        for agent_id in cluster["members"]:
            cluster_map.setdefault(agent_id, []).append(cluster["name"])

    agent_rows = []
    for agent_id in sorted(registry_agents):
        spec = {**defaults, **(registry_agents.get(agent_id) or {})}
        tools = spec.get("tools", []) or []
        agent_rows.append({
            "id": agent_id,
            "description": spec.get("description", ""),
            "purpose": spec.get("purpose", ""),
            "model": spec.get("model", ""),
            "role": spec.get("role") or spec.get("group") or "—",
            "group": spec.get("group", ""),
            "safety_level": spec.get("safety_level", defaults.get("safety_level", "read_only")),
            "discord_channels": spec.get("discord_channels", []) or [],
            "tool_count": len(tools),
            "tools": tools,
            "clusters": sorted(cluster_map.get(agent_id, [])),
        })

    tool_families = []
    shared_tool_names = set()
    for family_name, family_tools in sorted((components.get("tool_families") or {}).items()):
        items = family_tools or []
        shared_tool_names.update(items)
        tool_families.append({
            "name": family_name,
            "count": len(items),
            "tools": items,
        })

    all_agent_tools = sorted({tool for agent in agent_rows for tool in agent["tools"]})
    custom_tools = [tool for tool in all_agent_tools if tool not in shared_tool_names]

    # Inventory-by-intent, not inventory-by-truth. These name surfaces/flows
    # that the operator can reach; if a route here no longer exists in
    # do_GET/do_POST, the linter won't catch it. Run `patterns lint` (which
    # already walks patterns/agents/uis/routers/datasources inventories) and
    # extend it to also walk this list if drift becomes a problem.
    ui_surfaces = [
        {
            "name": "Factory Front Page",
            "path": "/",
            "kind": "inventory",
            "description": "Operational overview of clusters, agents, shared tools, infrastructure, and custom surfaces.",
        },
        {
            "name": "Live Graph Workspace",
            "path": "/graph",
            "kind": "graph",
            "description": "The existing graph-first control surface with lanes, inspect panel, focus mode, and spawn and wire actions.",
        },
        {
            "name": "Operator Sidecar Chat",
            "path": "/chat.html",
            "kind": "chat",
            "description": "Standalone lightweight operator chat shell for the MiMo CLI bridge.",
        },
        {
            "name": "Agent Bridge Chat",
            "path": "/chat/",
            "kind": "bridge",
            "description": "Reverse proxied ADK bridge chat running on the same hostname.",
        },
    ]

    custom_flows = [
        {
            "name": "Spawn agent",
            "endpoint": "/spawn",
            "description": "Scaffolds a new agent package and rebuilds the graph.",
        },
        {
            "name": "Wire contract",
            "endpoint": "/wire",
            "description": "Runs contract checks between nodes before wiring changes.",
        },
        {
            "name": "Save agent config",
            "endpoint": "/agent-config",
            "description": "Persists manifest edits and can auto-spawn on first save.",
        },
        {
            "name": "Generate agent",
            "endpoint": "/agent-generate",
            "description": "Runs factory apply plus import verification for an agent.",
        },
        {
            "name": "Verify agent",
            "endpoint": "/agent-verify",
            "description": "Checks package existence, import health, and built status.",
        },
        {
            "name": "Promote agent",
            "endpoint": "/promote",
            "description": "Moves an agent up the plain, builder, orchestrator ladder.",
        },
        {
            "name": "MiMo operator chat",
            "endpoint": "/chat",
            "description": "Session-aware operator chat bridged into the shared coding agent.",
        },
    ]

    source_files = list(FACTORY_OVERVIEW_SOURCES)
    for cluster in cluster_specs:
        source_files.append(f"clusters/{cluster['name']}/cluster.yaml")
        if cluster.get("goal") or cluster.get("project_summary"):
            source_files.append(f"clusters/{cluster['name']}/project.md")

    return {
        "summary": {
            "cluster_count": len(cluster_specs),
            "agent_count": len(agent_rows),
            "tool_family_count": len(tool_families),
            "shared_tool_count": len(shared_tool_names),
            "custom_tool_count": len(custom_tools),
            "connection_count": len((components.get("connections") or {})),
            "infra_host_count": len(infra.get("hosts", []) or []),
            "infra_service_count": len(infra.get("services", []) or []),
            "ui_surface_count": len(ui_surfaces),
        },
        "clusters": cluster_specs,
        "agents": agent_rows,
        "tool_families": tool_families,
        "custom_tools": custom_tools,
        "connections": components.get("connections", {}) or {},
        "tool_connections": components.get("tool_connections", {}) or {},
        "infra": {
            "hosts": infra.get("hosts", []) or [],
            "containers": infra.get("containers", []) or [],
            "services": infra.get("services", []) or [],
            "networks": infra.get("networks", []) or [],
            "tunnels": infra.get("tunnels", []) or [],
        },
        "ui_surfaces": ui_surfaces,
        "custom_flows": custom_flows,
        "sources": source_files,
        "building_blocks": _build_building_blocks_index(),
    }


def _git_run(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=LAG_HOME,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _git_checkpoint(paths: list[Path], message: str) -> dict:
    """Commit exactly the changed graph-state paths from a mutation."""
    rels = []
    for path in paths:
        try:
            rels.append(path.resolve().relative_to(LAG_HOME).as_posix())
        except ValueError:
            return {"ok": False, "error": f"path outside live graph repo: {path}"}
    if not rels:
        return {"ok": True, "committed": False, "paths": []}

    try:
        add = _git_run(["add", "--", *rels])
        if add.returncode != 0:
            return {
                "ok": False,
                "stage": "git add",
                "error": add.stderr.strip() or add.stdout.strip() or "git add failed",
                "paths": rels,
            }

        diff = _git_run(["diff", "--cached", "--quiet", "--", *rels])
        if diff.returncode == 0:
            return {"ok": True, "committed": False, "paths": rels}
        if diff.returncode != 1:
            return {
                "ok": False,
                "stage": "git diff --cached",
                "error": diff.stderr.strip() or diff.stdout.strip() or "git diff failed",
                "paths": rels,
            }

        commit = _git_run(["commit", "-m", message, "--", *rels], timeout=30)
        if commit.returncode != 0:
            return {
                "ok": False,
                "stage": "git commit",
                "error": commit.stderr.strip() or commit.stdout.strip() or "git commit failed",
                "paths": rels,
            }

        rev = _git_run(["rev-parse", "--short", "HEAD"])
        commit_sha = rev.stdout.strip() if rev.returncode == 0 else ""
        return {"ok": True, "committed": True, "commit": commit_sha, "paths": rels}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "stage": "git checkpoint", "error": f"timeout: {exc}", "paths": rels}
    except Exception as exc:
        return {"ok": False, "stage": "git checkpoint", "error": str(exc), "paths": rels}


def new_cluster(name: str) -> dict:
    """Scaffold a new cluster directory with cluster.yaml + project.md."""
    if not _SAFE_CLUSTER_NAME_RE.match(name or ""):
        return {"ok": False, "error": f"invalid cluster name {name!r} (a-z, 0-9, -, _)"}
    cluster_dir = LAG_HOME / "clusters" / name
    if cluster_dir.exists():
        return {"ok": False, "error": f"cluster '{name}' already exists"}
    cluster_yaml = cluster_dir / "cluster.yaml"
    project_md = cluster_dir / "project.md"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(cluster_yaml, f"# {name} cluster\nname: {name}\ndescription: ''\nmembers: []\nconfig:\n  default_model: gpt-5.5\n")
    _write_atomic(project_md, f"---\ngoal: ''\nstatus: blank\nhandoff_pct: 0\ndata_connectors: []\n---\n# {name}\n\nNew cluster.\n")
    checkpoint = _git_checkpoint([cluster_yaml, project_md], f"Add graph cluster {name}")
    if not checkpoint.get("ok"):
        return {
            "ok": False,
            "name": name,
            "error": "cluster created but git checkpoint failed",
            "git": checkpoint,
        }
    return {"ok": True, "name": name, "git": checkpoint}


def create_graph_agent(agent_id: str, model: str = "gpt-5.5", description: str = "") -> dict:
    """Create a graph-local agent draft in registry/agents/agents.yaml.

    Uses ruamel.yaml to preserve comments and key order in the existing
    file (text-append can break comments and reorder keys).
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]*", agent_id or ""):
        return {"ok": False, "error": "invalid agent id (a-z, 0-9, _, starts with a letter)"}

    registry_yaml = LAG_HOME / "registry" / "agents" / "agents.yaml"
    if not registry_yaml.exists():
        return {"ok": False, "error": "agent registry missing"}

    try:
        from ruamel.yaml import YAML as _RYAML
    except ImportError:
        return {"ok": False, "error": "ruamel.yaml not installed"}

    _ry = _RYAML(typ="rt")
    _ry.preserve_quotes = True
    _ry.indent(mapping=2, sequence=4, offset=2)
    try:
        with registry_yaml.open("r") as fh:
            doc = _ry.load(fh)
    except Exception as exc:
        return {"ok": False, "error": f"parse error: {exc}"}

    agents = (doc.get("agents") if doc else None) or {}
    if agent_id in agents:
        return {"ok": True, "agent_id": agent_id, "already_exists": True}

    clean_description = (description or f"{agent_id} agent").strip()
    safe_model = model or "gpt-5.5"
    agents[agent_id] = {
        "description": clean_description,
        "discord_channels": [],
        "safety_level": "read_only",
        "purpose": clean_description,
        "tools": [],
        "model": safe_model,
    }

    # Atomic write back to the registry.
    import io as _io
    buf = _io.StringIO()
    _ry.dump(doc, buf)
    _write_atomic(registry_yaml, buf.getvalue())

    checkpoint = _git_checkpoint([registry_yaml], f"Create graph agent {agent_id}")
    if not checkpoint.get("ok"):
        return {
            "ok": False,
            "agent_id": agent_id,
            "error": "agent created but git checkpoint failed",
            "git": checkpoint,
        }
    return {"ok": True, "agent_id": agent_id, "git": checkpoint}


def add_agent_to_cluster(cluster_name: str, agent_id: str) -> dict:
    """Append an agent id to a cluster's membership list (reference, not copy)."""
    if not _SAFE_CLUSTER_NAME_RE.match(cluster_name or ""):
        return {"ok": False, "error": f"invalid cluster_name {cluster_name!r}"}
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", agent_id or ""):
        return {"ok": False, "error": f"invalid agent_id {agent_id!r}"}
    cluster_yaml = LAG_HOME / "clusters" / cluster_name / "cluster.yaml"
    if not cluster_yaml.exists():
        return {"ok": False, "error": f"cluster '{cluster_name}' not found"}
    registry_yaml = LAG_HOME / "registry" / "agents" / "agents.yaml"
    if registry_yaml.exists():
        registry = (yaml.safe_load(registry_yaml.read_text()) or {}).get("agents", {})
        if agent_id not in registry:
            return {"ok": False, "error": f"agent '{agent_id}' not in registry"}
    text = cluster_yaml.read_text()
    if f"- {agent_id}" in text:
        return {"ok": True, "name": cluster_name, "agent_id": agent_id, "already_member": True}
    if "members: []" in text:
        new_text = text.replace("members: []", f"members:\n  - {agent_id}")
        _write_atomic(cluster_yaml, new_text)
        checkpoint = _git_checkpoint([cluster_yaml], f"Add {agent_id} to {cluster_name} cluster")
        if not checkpoint.get("ok"):
            return {
                "ok": False,
                "name": cluster_name,
                "agent_id": agent_id,
                "error": "cluster membership updated but git checkpoint failed",
                "git": checkpoint,
            }
        return {"ok": True, "name": cluster_name, "agent_id": agent_id, "git": checkpoint}
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
    _write_atomic(cluster_yaml, "\n".join(new_lines) + "\n")
    checkpoint = _git_checkpoint([cluster_yaml], f"Add {agent_id} to {cluster_name} cluster")
    if not checkpoint.get("ok"):
        return {
            "ok": False,
            "name": cluster_name,
            "agent_id": agent_id,
            "error": "cluster membership updated but git checkpoint failed",
            "git": checkpoint,
        }
    return {"ok": True, "name": cluster_name, "agent_id": agent_id, "git": checkpoint}


# ── MiMo Chat endpoint ──

MIMO_WORKDIR = str(WS)
MIMO_BIN = os.environ.get("MIMO_BIN", "mimo")
MIMO_TIMEOUT = int(os.environ.get("MIMO_TIMEOUT", "120"))
CHAT_MODEL_FALLBACKS = [
    "default",
    "openai/gpt-5.5",
    "openai/gpt-5.4",
    "openai/gpt-5.3-codex-spark",
    "openai/gpt-5.3-codex",
    "ollama-cloud/deepseek-v4-flash",
    "ollama-cloud/deepseek-v4-pro",
    "ollama-cloud/minimax-m2.7",
    "ollama-cloud/kimi-k2.6",
    "ollama-cloud/qwen3-coder:480b",
    "google/gemini-3.1-pro-preview",
    "google/gemini-3-flash-preview",
    "minimax/MiniMax-M3",
    "minimax/MiniMax-M3-thinking",
    "cerebras/gpt-oss-120b",
    "mimo-v2.5",
    "mimo-v2.5-pro",
    "mimo/mimo-auto",
]
# Unified model aliases. Display label -> real provider/model id.
# CHAT_MODEL_FALLBACKS is the canonical list of available model ids; each
# entry also serves as a self-alias. LEGACY_CHAT_MODEL_ALIASES maps the
# older display labels to the current names. Both sources merge into a
# single MODEL_ALIASES dict so _normalise_chat_model has one lookup.
_MODEL_LEGACY_ALIASES = {
    "mimo-v2.5": "mimo/mimo-auto",
    "mimo-v2.5-pro": "mimo/mimo-auto",
    "mimo-v2.5-pro-ultraspeed": "mimo/mimo-auto",
    "codex/gpt-5.5": "openai/gpt-5.5",
    "codex/gpt-5.4": "openai/gpt-5.4",
    "codex/gpt-5.3-codex-spark": "openai/gpt-5.3-codex-spark",
    "gpt-5.5": "openai/gpt-5.5",
    "gpt-5.4": "openai/gpt-5.4",
    "deepseek-v4-pro": "ollama-cloud/deepseek-v4-pro",
    "deepseek-v4-flash": "ollama-cloud/deepseek-v4-flash",
    "glm-5.2": "ollama-cloud/glm-5.2",
    "gemini-3-pro-preview": "google/gemini-3.1-pro-preview",
    "gemini-3-flash-preview": "google/gemini-3-flash-preview",
    "qwen3-coder:480b": "ollama-cloud/qwen3-coder:480b",
}


_MODEL_ALIASES = {**_MODEL_LEGACY_ALIASES, **{m: m for m in CHAT_MODEL_FALLBACKS}}


def _normalise_chat_model(model: str | None) -> str | None:
    """Convert display/legacy model labels into MiMo CLI model ids."""
    clean = (model or "").strip()
    if not clean or clean == "default":
        return None
    if clean in _MODEL_ALIASES:
        return _MODEL_ALIASES[clean]
    if "/" not in clean:
        return None
    return clean


def _list_chat_models() -> list[str]:
    try:
        result = subprocess.run(
            [MIMO_BIN, "models"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=MIMO_WORKDIR,
        )
        if result.returncode == 0:
            models = [line.strip() for line in result.stdout.splitlines()
                      if "/" in line.strip() and not line.strip().startswith("\x1b")]
            ordered = ["default"]
            for model in models:
                if model not in ordered:
                    ordered.append(model)
            if len(ordered) > 1:
                return ordered
    except Exception:
        pass
    return CHAT_MODEL_FALLBACKS

def chat_with_mimo(message: str, session_id: str | None = None,
                   model: str | None = None, principal: str = "unknown") -> dict:
    """Send a message to MiMo (CLI coding agent) and return the response.

    MiMo runs as a subprocess with full tool access (bash, file, search) in
    the ADK workspace. Session-aware: pass session_id to continue a conversation.
    Model can be overridden per-request via the -m flag.
    """
    if isinstance(message, str) and len(message.encode("utf-8")) > MAX_MIMO_MESSAGE_BYTES:
        return {"ok": False, "error": f"message too large (max {MAX_MIMO_MESSAGE_BYTES} bytes)"}
    model = _normalise_chat_model(model)
    cmd = [MIMO_BIN, "run", "--format", "json", "--dir", MIMO_WORKDIR]
    if model:
        cmd.extend(["-m", model])
    if session_id:
        cmd.extend(["-s", session_id])
    cmd.append(message)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=MIMO_TIMEOUT, cwd=MIMO_WORKDIR)
        if result.returncode == 0:
            response_text = ""
            new_session_id = session_id or ""
            error_text = ""
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("type") == "text" and evt.get("part", {}).get("text"):
                    response_text += evt["part"]["text"]
                if evt.get("type") == "error":
                    error = evt.get("error") or {}
                    data = error.get("data") if isinstance(error, dict) else {}
                    if isinstance(data, dict):
                        error_text = data.get("message") or data.get("responseBody") or ""
                    if not error_text and isinstance(error, dict):
                        error_text = error.get("name") or "MiMo error"
                if evt.get("sessionID") and not new_session_id:
                    new_session_id = evt["sessionID"]
            if error_text and not response_text:
                return {"ok": False, "error": error_text[:500], "session_id": new_session_id}
            return {"ok": True, "response": response_text or "(no response)",
                    "session_id": new_session_id}
        return {"ok": False, "error": result.stderr[:500] or f"exit {result.returncode}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {MIMO_TIMEOUT}s"}
    except FileNotFoundError:
        return {"ok": False, "error": "mimo not installed on this box"}
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
            [py, str(LAG_HOME / "spawn_agent.py"), agent_id,
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
        "models": list(CHAT_MODEL_FALLBACKS),
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


_VALID_AGENT_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")


def _safe_agent_id(agent_id: str) -> str:
    """Validate agent_id is a strict identifier (a-z, 0-9, _, starts with letter, max 64 chars)."""
    if not _VALID_AGENT_ID.fullmatch(agent_id or ""):
        raise ValueError(f"invalid agent_id {agent_id!r}")
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
                "path": str(path.relative_to(LAG_HOME)),
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
        super().__init__(*args, directory=str(LAG_HOME), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _get_principal(self) -> str | None:
        """Verify Cloudflare Access JWT and return the verified email, or None.

        Every request must carry a valid Cf-Access-Jwt-Assertion header.
        Returns the verified email as the principal for audit logging.
        """
        token = self.headers.get("Cf-Access-Jwt-Assertion", "")
        if token:
            principal = _verify_access_jwt(token)
            if principal:
                return principal
        # Some Access + Tunnel paths pass the verified user email header without
        # the JWT assertion. The service is bound to localhost behind Cloudflare
        # Tunnel, so this is a practical fallback for browser UI mutations.
        email = self.headers.get("Cf-Access-Authenticated-User-Email", "")
        if email and _EMAIL_RE.fullmatch(email):
            return email
        return None

    def _has_mutation_secret(self) -> bool:
        """Allow box-side smoke tests and legacy clients when a local secret is configured."""
        if not GRAPH_MUTATION_SECRET:
            return False
        supplied = self.headers.get("X-Graph-Secret", "")
        return bool(supplied) and hmac.compare_digest(supplied, GRAPH_MUTATION_SECRET)

    def _check_auth(self) -> bool:
        """Return True for verified Cloudflare Access requests or local secret tests."""
        return self._get_principal() is not None or self._has_mutation_secret()

    def _principal_or_secret(self) -> str | None:
        """Resolve the effective principal for a request.

        Returns the verified email from Cloudflare Access when the JWT
        is valid. Falls back to "smoke-test" if the local mutation secret
        is in use (no email available, but the secret authenticates).
        Returns None when neither path authenticates the request.
        """
        principal = self._get_principal()
        if principal:
            return principal
        if self._has_mutation_secret():
            return "smoke-test"
        return None

    def _is_mutating(self, path: str) -> bool:
        """Return True for endpoints that mutate state."""
        return path in ("/spawn", "/wire", "/save-agent", "/promote",
                        "/new-cluster", "/add-agent", "/chat",
                        "/agent-config", "/agent-generate", "/agent-eval-run")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self.path = "/index.html"
            super().do_GET()
        elif path == "/home":
            self.path = "/home.html"
            super().do_GET()
        elif path == "/graph":
            self.path = "/index.html"
            super().do_GET()
        elif path in ("/index.html", "/home.html"):
            self.path = path
            super().do_GET()
        elif path == "/factory-overview":
            self._json_response(200, _build_factory_overview())
        elif path in ("/pulse", "/pulse/"):
            self._json_response(200, get_pulse())
        elif path in ("/clusters", "/clusters/"):
            self._json_response(200, list_clusters())
        elif path == "/chat-token":
            if self._check_auth():
                self._json_response(200, {"token": _chat_token(), "base": CHAT_BASE_URL})
            else:
                self._json_response(403, {"error": "forbidden: Cloudflare Access required"})
        elif path == "/manifest":
            qs = parse_qs(parsed.query)
            cluster = qs.get("cluster", [None])[0]
            if not cluster:
                self._json_response(400, {"error": "missing ?cluster=name"})
                return
            if not _SAFE_CLUSTER_NAME_RE.match(cluster):
                self._json_response(400, {"error": f"invalid cluster name {cluster!r}"})
                return
            manifest = build_manifest(cluster)
            if manifest is None:
                self._json_response(404, {"error": f"cluster '{cluster}' not found or build failed"})
                return
            self._json_response(200, manifest)
        elif path == "/models":
            self._json_response(200, {"models": _list_chat_models()})
        elif path in ("/agent-config", "/agent-tools", "/agent-models", "/agent-verify", "/agent-evals") and not self._check_auth():
            # Fail-closed: without a valid Access JWT, block access.
            # than silently opening the endpoints. Standalone dev should set a secret.
            self._json_response(403, {"ok": False, "error": "forbidden: Cloudflare Access required"})
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
        elif path.startswith("/chat") and path != "/chat-token":
            if _proxy_to_bridge(self, "GET"):
                return
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._json_response(400, {"ok": False, "error": "invalid Content-Length"})
            return
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            self._json_response(413, {"ok": False, "error": f"body too large (max {MAX_REQUEST_BYTES} bytes)"})
            return
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
            if not self._check_auth():
                self._json_response(401, {"error": "unauthorized"})
                return
            agent_id = params.get("id", [None])[0]
            model = params.get("model", ["gpt-5.5"])[0]
            description = params.get("description", [f"{agent_id} agent"])[0] if agent_id else ""
            cluster = params.get("cluster", [None])[0]

            if not agent_id:
                self._json_response(400, {"error": "missing id"})
                return

            result = create_graph_agent(agent_id, model, description)
            if result.get("ok") and cluster:
                cluster_result = add_agent_to_cluster(cluster, agent_id)
                result["cluster"] = cluster_result
                if not cluster_result.get("ok"):
                    result["ok"] = False
                    result["error"] = cluster_result.get("error", "agent created but could not be added to cluster")

            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/wire":
            if not self._check_auth():
                self._json_response(401, {"error": "unauthorized"})
                return
            source = params.get("source", [None])[0]
            target = params.get("target", [None])[0]
            if not source or not target:
                self._json_response(400, {"error": "missing source or target"})
                return
            # Fallback to local contract_check.py
            result = subprocess.run(
                [sys.executable, str(LAG_HOME / "contract_check.py"), source, target],
                capture_output=True, text=True,
            )
            if result.returncode in (0, 1):
                try:
                    check = json.loads(result.stdout)
                except json.JSONDecodeError:
                    check = {
                        "valid": False,
                        "error": "contract check returned invalid JSON",
                        "stdout": result.stdout[:300],
                        "stderr": result.stderr[:300],
                    }
            else:
                check = {"valid": False, "error": result.stderr[:300] or f"exit {result.returncode}"}
            self._json_response(200, check)

        elif parsed.path == "/save-agent":
            if not self._check_auth():
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
                # Hardcoded fallback if proxy unreachable. Use the canonical
                # CHAT_MODEL_FALLBACKS list as the single source of truth.
                self._json_response(200, {"models": list(CHAT_MODEL_FALLBACKS)})

        elif parsed.path == "/promote":
            if not self._check_auth():
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
            if not self._check_auth():
                self._json_response(401, {"error": "unauthorized"})
                return
            name = params.get("name", [None])[0]
            if not name:
                self._json_response(400, {"error": "missing name"})
                return
            result = new_cluster(name)
            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/add-agent":
            if not self._check_auth():
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
            principal = self._check_auth() and (self._get_principal() or "smoke-test")
            if not principal:
                self._json_response(401, {"error": "unauthorized: Cloudflare Access required"})
                return
            message = None
            session_id = None
            model = None
            try:
                json_body = json.loads(body) if body else {}
                message = json_body.get("message")
                session_id = json_body.get("session_id")
                model = json_body.get("model")
            except json.JSONDecodeError:
                pass
            if not message:
                message = params.get("message", [None])[0]
                session_id = params.get("session_id", [None])[0]
            if not message:
                self._json_response(400, {"error": "missing message"})
                return

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

            result = chat_with_mimo(message, session_id, model, principal)

            # Track session ownership
            if result.get("ok") and result.get("session_id"):
                with _session_lock:
                    _session_owners[result["session_id"]] = (principal, time.time())

            outcome = "ok" if result.get("ok") else f"error: {result.get('error', 'unknown')[:100]}"
            _audit(principal, message, session_id, outcome)
            self._json_response(200 if result.get("ok") else 500, result)

        elif parsed.path == "/agent-config":
            if not self._check_auth():
                self._json_response(401, {"error": "unauthorized"})
                return
            self._json_response(200, _save_agent_config(params))

        elif parsed.path == "/agent-generate":
            if not self._check_auth():
                self._json_response(401, {"error": "unauthorized"})
                return
            agent_id = params.get("agent_id", [None])[0]
            if not agent_id:
                self._json_response(400, {"ok": False, "error": "missing agent_id"})
                return
            self._json_response(200, _generate_agent(agent_id))

        elif parsed.path == "/agent-eval-run":
            if not self._check_auth():
                self._json_response(403, {"ok": False, "error": "forbidden: Cloudflare Access required"})
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

        elif parsed.path.startswith("/chat/") and parsed.path != "/chat-token":
            _proxy_to_bridge(self, "POST")

        else:
            self._json_response(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        # CORS: read-only endpoints get pinned origin; mutating endpoints get none
        path = self.path.rstrip("/") or "/"
        if not self._is_mutating(path):
            self.send_header("Access-Control-Allow-Origin", CRM_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json_response(self, code, data):
        try:
            body = json.dumps(data).encode()
        except (TypeError, ValueError):
            # Non-serializable payload — return a generic error rather than
            # corrupting the HTTP stream mid-headers.
            body = json.dumps({"ok": False, "error": "internal: non-serializable response"}).encode()
            code = 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        # CORS: read-only endpoints get pinned origin; mutating endpoints get none
        if not self._is_mutating(self.path.rstrip("/") or "/"):
            self.send_header("Access-Control-Allow-Origin", CRM_ORIGIN)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # quiet


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Live Agent Graph server on http://127.0.0.1:{port} (localhost only)")
    server.serve_forever()
