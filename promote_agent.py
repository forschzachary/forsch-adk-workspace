#!/usr/bin/env python3
"""Operator-confirmed role promotion. Runs in factory venv (has yaml).

Usage:
  python3 promote_agent.py <agent_id> <target_role>
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from workspace_resolver import workspace_root

WS = Path(sys.argv[1]) if len(sys.argv) > 3 else workspace_root() / "adk"
LAG_HOME = WS / "live-agent-graph"


def promote(agent_id: str, target_role: str) -> dict:
    agents_yaml = WS / "agent_specs" / "agents.yaml"
    if not agents_yaml.exists():
        return {"ok": False, "error": "agents.yaml not found"}

    data = yaml.safe_load(agents_yaml.read_text()) or {}
    agents = data.get("agents", {})
    if agent_id not in agents:
        return {"ok": False, "error": f"agent '{agent_id}' not in agents.yaml"}

    agent = agents[agent_id]
    current_role = agent.get("role", "plain")

    valid_promotions = {"plain": "builder", "builder": "orchestrator"}
    if current_role == target_role:
        return {"ok": True, "noop": True, "agent_id": agent_id, "role": current_role}
    expected_next = valid_promotions.get(current_role)
    if target_role != expected_next:
        return {"ok": False, "error": f"invalid promotion: {current_role} → {target_role} (expected {current_role} → {expected_next})"}

    if current_role == "plain" and target_role == "builder":
        if not agent.get("tools"):
            return {"ok": False, "error": "plain→builder requires at least one tool (L1)"}

    agent["role"] = target_role
    agents_yaml.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    # Log
    log_file = LAG_HOME / ".promotion_log.jsonl"
    entry = {
        "agent_id": agent_id,
        "from_role": current_role,
        "to_role": target_role,
        "operator": "operator",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Rebuild graph
    result = subprocess.run(
        [sys.executable, str(LAG_HOME / "build_live_graph.py")],
        capture_output=True, text=True, cwd=str(WS),
    )
    if result.returncode != 0:
        return {"ok": False, "error": f"graph rebuild failed: {result.stderr[:200]}"}

    return {"ok": True, "agent_id": agent_id, "from_role": current_role, "to_role": target_role}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 promote_agent.py <agent_id> <target_role>", file=sys.stderr)
        sys.exit(1)

    agent_id = sys.argv[1]
    target_role = sys.argv[2]
    result = promote(agent_id, target_role)
    print(json.dumps(result))
    sys.exit(0 if result.get("ok") else 1)
