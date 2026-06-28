# Stability agent directory note

Purpose: standalone ADK package for the read-only stability governor.

Structure:

- `src/forsch/agent_stability/agent.py` - runtime ADK agent definition.
- `tests/` - import and behavior smoke tests.
- `evals/` - future evaluation prompts for stability audits.

Ownership rule: this agent reports evidence and safe next actions only. Mutating repair workflows belong in later agents or explicit human-approved tasks.

Git ownership: this directory is the `forschzachary/forsch-agent-stability` repo. Commit and push agent package, test, README, and eval changes here. Shared inspection helpers belong in `forsch-adk-components`, not this repo. Do not track `.venv/`, `.pytest_cache/`, `__pycache__/`, `.env`, or generated state.
