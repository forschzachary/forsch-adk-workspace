#!/usr/bin/env python3
"""Minimal HTTP bridge for the Live Agent Graph UI — serves index.html + spawn + pulse.

Usage:
  python3 serve.py [--port 8888]
"""

import json
import os
import subprocess
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

SPIKE_DIR = Path(__file__).resolve().parent
WS = Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/opt/data/workspace/adk"))


def promote_agent(agent_id: str, target_role: str) -> dict:
    """Operator-confirmed role promotion. Delegates to promote_agent.py (factory venv)."""
    factory_python = WS / "factory" / ".venv" / "bin" / "python"
    py = str(factory_python) if factory_python.exists() else sys.executable
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
    """Return which edges are 'active' — derived from live health checks.

    Returns {active_edges: [{source, target}], live_nodes: [id]}.
    This is the data that drives directional particles on the graph.
    """
    active_edges = []
    live_nodes = []

    # Bridge health → all agent→channel and agent→model edges are "live"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}",
             "http://127.0.0.1:8800"],
            capture_output=True, text=True,
        )
        bridge_alive = r.returncode == 0 and r.stdout.strip().isdigit()
    except Exception:
        bridge_alive = False

    # Authsome health → credential edges are "live"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-m", "3", "http://127.0.0.1:7998/health"],
            capture_output=True, text=True,
        )
        authsome_alive = r.returncode == 0 and '"status":"ok"' in r.stdout
    except Exception:
        authsome_alive = False

    # LiteLLM health → model edges are "live"
    try:
        r = subprocess.run(
            ["curl", "-sS", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}",
             "http://127.0.0.1:4000/v1/models"],
            capture_output=True, text=True,
        )
        litellm_alive = r.returncode == 0 and r.stdout.strip().isdigit()
    except Exception:
        litellm_alive = False

    # Load the graph to map node IDs
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

            # Agent→channel edges pulse when bridge is alive
            if link["kind"] == "listens" and bridge_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})
            # Agent→model edges pulse when LiteLLM is alive
            if link["kind"] in ("pinned-model", "default-model") and litellm_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})
            # Tool→credential edges pulse when authsome is alive
            if link["kind"] == "authenticates-via" and authsome_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})
            # Model fallback edges pulse when LiteLLM is alive
            if link["kind"] == "fallback" and litellm_alive:
                active_edges.append({"source": link["source"], "target": link["target"]})

        # Mark nodes as live if their edges are active
        live_set = set()
        for e in active_edges:
            live_set.add(e["source"])
            live_set.add(e["target"])
        live_nodes = list(live_set)

    # Round-trip liveness for ops slice (read from cache, populated by cron/manual run)
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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SPIKE_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/pulse":
            self._json_response(200, get_pulse())
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/spawn":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()
            params = parse_qs(body)
            agent_id = params.get("id", [None])[0]
            model = params.get("model", ["gpt-5.5"])[0]
            description = params.get("description", [f"{agent_id} agent"])[0] if agent_id else ""

            if not agent_id:
                self._json_response(400, {"error": "missing id"})
                return

            factory_python = WS / "factory" / ".venv" / "bin" / "python"
            py = str(factory_python) if factory_python.exists() else sys.executable
            result = subprocess.run(
                [py, str(SPIKE_DIR / "spawn_agent.py"), agent_id,
                 "--model", model, "--description", description],
                capture_output=True, text=True, cwd=str(WS),
            )

            if result.returncode == 0:
                self._json_response(200, {"ok": True, "agent_id": agent_id, "output": result.stdout})
            else:
                self._json_response(500, {"ok": False, "error": result.stderr[:500]})
        elif self.path == "/wire":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()
            params = parse_qs(body)
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
        elif self.path == "/promote":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()
            params = parse_qs(body)
            agent_id = params.get("agent_id", [None])[0]
            target_role = params.get("target_role", [None])[0]

            if not agent_id or not target_role:
                self._json_response(400, {"error": "missing agent_id or target_role"})
                return

            result = promote_agent(agent_id, target_role)
            self._json_response(200 if result.get("ok") else 400, result)
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
