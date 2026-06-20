# Agents directory note

Purpose: parent folder for independent ADK team-lead agent repositories. This folder itself is organizational; the child directories are the real repos.

Structure:

- `build/` - product and engineering agent.
- `brand/` - brand and marketing agent.
- `ops/` - infrastructure and operations agent.
- `assistant/` - personal assistant agent.
- `social/` - social media agent.
- `stability/` - read-only stability governor.

Each agent directory follows the same package shape: `pyproject.toml`, `README.md`, `src/forsch/agent_<name>/agent.py`, `tests/`, and `evals/`.

Current organization rule: agents can depend on `forsch-adk-components`, but should not import from sibling agents. Shared tools graduate into `components`; domain-specific behavior stays in the owning agent.
