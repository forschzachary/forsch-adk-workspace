# Website agent directory note

Purpose: independent ADK repo for Zach's personal website launch lead.

Structure:

- `pyproject.toml` - package metadata for `forsch-agent-website`.
- `src/forsch/agent_website/agent.py` - generated ADK `root_agent`.
- `tests/` - website-agent import and contract tests.
- `evals/` - website-agent evaluation datasets and scenarios.
- `README.md` - setup/run notes for this repo.

Expected scope: SEO, accessibility, CTA, proof, content, metadata, and
go-live planning for Zach's owned personal brand surfaces.

Git ownership: this directory is the `forschzachary/forsch-agent-website`
repo for the website launch lead agent. Website-specific behavior belongs
here; shared growth tools belong in `forsch-adk-components`. Do not track
`.venv/`, `.pytest_cache/`, `__pycache__/`, `.env`, `.adk/`, SQLite DBs, or
generated state.
