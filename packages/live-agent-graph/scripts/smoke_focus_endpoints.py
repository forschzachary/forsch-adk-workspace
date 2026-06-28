#!/usr/bin/env python3
"""Smoke test for focus-mode endpoints. Run from the spike directory."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = os.environ.get("GRAPH_BASE", "http://127.0.0.1:8888")
SECRET = os.environ.get("GRAPH_SERVER_SECRET")
if not SECRET:
    secret_file = Path(os.environ.get("HERMES_HOME", "/opt/data")) / "graph-server-secret"
    if secret_file.exists():
        SECRET = secret_file.read_text().strip()


def get(path: str, secret: bool = False):
    headers = {}
    if secret and SECRET:
        headers["X-Graph-Secret"] = SECRET
    req = urllib.request.Request(BASE + path, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read())


def main() -> int:
    checks = [
        ("/pulse", False),
        ("/clusters", False),
        ("/manifest?cluster=ops", False),
        ("/agent-tools", True),
        ("/agent-models", True),
        ("/agent-config?agent_id=ops", True),
        ("/agent-verify?agent_id=ops", True),
        ("/agent-evals?agent_id=ops", True),
    ]
    failures = 0
    for path, needs_secret in checks:
        try:
            status, data = get(path, needs_secret)
            ok = status == 200 and not (isinstance(data, dict) and data.get("ok") is False)
            print(f"{path}: {status} {'OK' if ok else 'BAD'}")
            if not ok:
                print(json.dumps(data, indent=2)[:800])
                failures += 1
        except Exception as exc:
            print(f"{path}: ERROR {exc}")
            failures += 1
    return failures


if __name__ == "__main__":
    sys.exit(main())
