# Web agents directory note

Purpose: ADK Web UI entrypoint directory. The `adk web` command expects each visible app to be a child folder containing a top-level `agent.py` or `root_agent.yaml`, while our real agents live as independent Python packages under `agents/`.

Structure:

- `ops/agent.py` - thin wrapper that imports the real ops graph from `agents/ops/src/forsch/agent_ops/agent.py`.
- `stability/agent.py` - thin wrapper that imports the real stability governor from `agents/stability/src/forsch/agent_stability/agent.py`.
- `*/root_agent.yaml` - editable ADK Web surfaces that mirror selected runtime agents.

Current organization rule: keep this directory thin. Real agent code stays in the independent agent repos; this folder only exposes selected agents to the ADK UI.
