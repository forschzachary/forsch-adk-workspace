#!/usr/bin/env python3
"""Minimal HTTP bridge for the Live Agent Graph UI — serves index.html + handles spawn POST.

Usage:
  python3 serve.py [--port 8888]
"""

import json
import os
import subprocess
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SPIKE_DIR = Path(__file__).resolve().parent
WS = Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/opt/data/workspace/adk"))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SPIKE_DIR), **kwargs)

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
        else:
            self._json_response(404, {"error": "not found"})

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # quiet


if __name__ == "__main__":
    import os
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Live Agent Graph server on http://0.0.0.0:{port}")
    server.serve_forever()
