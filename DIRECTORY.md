# Social agent directory note

Purpose: independent ADK repo for the social media lead agent.

Structure:

- `pyproject.toml` - package metadata for `forsch-agent-social`.
- `src/forsch/agent_social/agent.py` - current ADK `Agent` stub and future graph entrypoint.
- `tests/` - social-agent unit tests.
- `evals/` - social-agent evaluation datasets and scenarios.
- `README.md` - setup/run notes for this repo.

Expected scope: post planning, engagement tracking, analytics, content calendar support, and future social-platform integrations routed through shared components/Authsome.

Git ownership: this directory is the `forschzachary/forsch-agent-social` repo for the social media lead agent. Commit and push agent package, test, README, and eval changes here. Posting, engagement, analytics, and content-calendar behavior belongs here; shared platform clients belong in `forsch-adk-components`. Do not track `.venv/`, `.pytest_cache/`, `__pycache__/`, `.env`, `.adk/`, SQLite DBs, or generated state.
