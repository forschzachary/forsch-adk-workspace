# Ops web entrypoint directory note

Purpose: expose the packaged ops agent to `adk web` without duplicating agent logic.

Structure:

- `agent.py` - imports `root_agent` from `forsch.agent_ops.agent` and aliases it as `agent` for ADK Web UI discovery.

Current organization rule: do not put business logic here. Edit the ops graph in `/opt/data/workspace/adk/agents/ops/` instead.
