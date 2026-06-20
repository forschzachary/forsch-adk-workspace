# Stability Agent

Read-only stability governor for the Forsch ADK workspace.

The agent can inspect workspace structure, git state, configured agent imports, and local service health. It must not edit source, restart services, install packages, or perform destructive operations.

## Local Run

Run the deterministic read-only audit without calling a model:

```bash
cd /opt/data/workspace/adk/components
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  ./.venv/bin/python scripts/stability_audit.py --skip-services
```

Run the full local audit, including Authsome and LiteLLM health probes:

```bash
cd /opt/data/workspace/adk/components
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  ./.venv/bin/python scripts/stability_audit.py
```

Use ADK Web through the wrapper:

```bash
cd /opt/data/workspace/adk
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  components/.venv/bin/adk web web_agents
```

Discord route: `#team-stability` via `bridge/bridge_config.yaml`.
