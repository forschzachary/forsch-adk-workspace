# Assistant agent directory note

Purpose: independent ADK repo for the personal assistant lead agent.

Structure:

- `pyproject.toml` - package metadata for `forsch-agent-assistant`.
- `src/forsch/agent_assistant/agent.py` - current ADK `Agent` stub and future graph entrypoint.
- `tests/` - assistant-agent unit tests.
- `evals/` - assistant-agent evaluation datasets and scenarios.
- `README.md` - setup/run notes for this repo.

Expected scope: calendar, email, task routing, scheduling, reminders, and coordination workflows that use shared credential-backed tools rather than local secrets.

Git ownership: this directory is the `forschzachary/forsch-agent-assistant` repo for the personal assistant lead agent. Commit and push agent package, test, README, and eval changes here. Calendar, email, reminders, and task-routing behavior belongs here; shared credential clients belong in `forsch-adk-components`. Do not track `.venv/`, `.pytest_cache/`, `__pycache__/`, `.env`, `.adk/`, SQLite DBs, or generated state.
