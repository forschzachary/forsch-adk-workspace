# Brand agent directory note

Purpose: independent ADK repo for the brand and marketing lead agent.

Structure:

- `pyproject.toml` - package metadata for `forsch-agent-brand`.
- `src/forsch/agent_brand/agent.py` - current ADK `Agent` stub and future graph entrypoint.
- `tests/` - brand-agent unit tests.
- `evals/` - brand-agent evaluation datasets and scenarios.
- `README.md` - setup/run notes for this repo.

Expected scope: positioning, messaging, campaign planning, content review, design feedback, and marketing workflows that may read CRM context through shared components.

Git ownership: this directory is the `forschzachary/forsch-agent-brand` repo for the brand and marketing lead agent. Commit and push agent package, test, README, and eval changes here. Positioning, messaging, and marketing-review behavior belongs here; shared business-context clients belong in `forsch-adk-components`. Do not track `.venv/`, `.pytest_cache/`, `__pycache__/`, `.env`, `.adk/`, SQLite DBs, or generated state.
