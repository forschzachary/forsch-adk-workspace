# Stability Governor Runbook

Purpose: run the read-only stability governor without changing source, restarting services, installing dependencies, or touching production state.

## Deterministic Audit

From the components repo:

```bash
cd /opt/data/workspace/adk/components
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  ./.venv/bin/python scripts/stability_audit.py --skip-services
```

This returns JSON with:

- `workspace` - compact directory/file inventory.
- `git` - branch and porcelain status for ADK repos.
- `agents` - import validation for configured agent packages.
- `services` - local HTTP health checks when not skipped.
- `summary` - dirty repo count, failed imports, failed services.

## Full Local Audit

```bash
cd /opt/data/workspace/adk/components
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  ./.venv/bin/python scripts/stability_audit.py
```

This also checks:

- Authsome: `http://127.0.0.1:7998/health`
- LiteLLM: `http://127.0.0.1:4000/health/readiness`

## ADK Web

```bash
cd /opt/data/workspace/adk
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  components/.venv/bin/adk web web_agents
```

Open ADK Web and select the `stability` wrapper. `web_agents/stability/root_agent.yaml` is the editable surface; `agents/stability/src/forsch/agent_stability/agent.py` is the runtime package.

## Discord

The bridge routes `#team-stability` to `forsch.agent_stability.agent:root_agent` through `bridge/bridge_config.yaml`.

## Safety Boundary

The stability governor is read-only. It can collect evidence and recommend the smallest safe next action. It must not repair, install, restart, delete, migrate, or rewrite anything without a separate explicit task.
