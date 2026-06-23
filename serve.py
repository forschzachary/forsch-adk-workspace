#!/usr/bin/env python3
"""HTTP bridge for the Live Agent Graph UI — serves index.html + cluster tabs + spawn + pulse + chat.

Usage:
  python3 serve.py [port]
"""

import json
import os
import subprocess
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SPIKE_DIR = Path(__file__).resolve().parent
WS = Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/opt/data/workspace/adk"))
FACTORY_PYTHON = WS / "factory" / ".venv" / "bin" / "python3.12"
BUILDER_PY = str(FACTORY_PYTHON) if FACTORY_PYTHON.exists() else sys.executable


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
    """Return all cluster folders with their project.md front-matter."""
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
    """Run build_live_graph.py --cluster <name> and return the manifest."""
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
    """Send a message to Hubert via hermes chat -q and return the response."""
    cmd = ["hermes", "chat", "-q", message, "--quiet", "--source", "tool",
           "--ignore-user-config", "--ignore-rules",
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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SPIKE_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in ("/pulse", "/pulse/"):
            self._json_response(200, get_pulse())
        elif path in ("/clusters", "/clusters/"):
            self._json_response(200, list_clusters())
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
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length else ""
        params = parse_qs(body)

        if parsed.path == "/spawn":
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
                self._json_response(200, {"ok": True, "agent_id": agent_id, "output": result.stdout})
            else:
                self._json_response(500, {"ok": False, "error": result.stderr[:500]})

        elif parsed.path == "/wire":
            source = params.get("source", [None])[0]
            target = params.get("target", [None])[0]
            if not source or not target:
                self._json_response(400, {"error": "missing source or target"})
                return
            result = subprocess.run(
                [sys.executable, str(SPIKE_DIR / "contract_check.py"), source, target],
                capture_output=True, text=True,
            )
            check = json.loads(result.stdout) if result.returncode in (0, 1) else {"valid": False, "error": result.stderr}
            self._json_response(200, check)

        elif parsed.path == "/promote":
            agent_id = params.get("agent_id", [None])[0]
            target_role = params.get("target_role", [None])[0]
            if not agent_id or not target_role:
                self._json_response(400, {"error": "missing agent_id or target_role"})
                return
            result = promote_agent(agent_id, target_role)
            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/new-cluster":
            name = params.get("name", [None])[0]
            if not name:
                self._json_response(400, {"error": "missing name"})
                return
            result = new_cluster(name)
            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/add-agent":
            cluster = params.get("cluster", [None])[0]
            agent_id = params.get("agent_id", [None])[0]
            if not cluster or not agent_id:
                self._json_response(400, {"error": "missing cluster or agent_id"})
                return
            result = add_agent_to_cluster(cluster, agent_id)
            self._json_response(200 if result.get("ok") else 400, result)

        elif parsed.path == "/chat":
            message = params.get("message", [None])[0]
            session_id = params.get("session_id", [None])[0]
            if not message:
                self._json_response(400, {"error": "missing message"})
                return
            result = chat_with_hubert(message, session_id)
            self._json_response(200 if result.get("ok") else 500, result)

        else:
            self._json_response(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass  # quiet


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Live Agent Graph server on http://0.0.0.0:{port}")
    server.serve_forever()
