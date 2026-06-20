# Ops agent directory note

Purpose: independent ADK repo for the infrastructure and operations lead agent.

Structure:

- `pyproject.toml` - package metadata for `forsch-agent-ops`.
- `src/forsch/agent_ops/agent.py` - current ADK `Agent` stub and likely first graph entrypoint.
- `tests/` - ops-agent unit tests.
- `evals/` - ops-agent evaluation datasets and scenarios.
- `README.md` - setup/run notes for this repo.

Expected scope: service health checks, deployment state, incident triage, and the first read-only Frappe CRM watchdog using shared Authsome/Frappe clients from `components`.

Git ownership: this directory is the `forschzachary/forsch-agent-ops` repo for the infrastructure and operations lead agent. Commit and push agent package, test, README, and eval changes here. Shared CRM/service health helpers belong in `forsch-adk-components`; ops-specific orchestration stays here. Do not track `.venv/`, `.pytest_cache/`, `__pycache__/`, `.env`, `.adk/`, SQLite DBs, or generated state.
