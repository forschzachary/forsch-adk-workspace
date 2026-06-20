# ADK workspace directory note

Purpose: top-level workspace for Forsch Google ADK agent development. This directory organizes one shared component package, five independent team-lead agent repos, and cross-agent documentation.

Structure:

- `components/` - shared Python package (`forsch-adk-components`) for reusable tools, models, and testing helpers. Authsome and Frappe clients belong here.
- `agents/` - parent folder for independent agent repositories. Each child agent owns its own package, tests, evals, and git history.
- `docs/` - cross-agent architecture and runbook documentation that applies to the whole ADK workspace.
- `README.md` - human overview and getting-started notes for the workspace.

Current organization rule: shared integration code goes in `components`; domain instructions and agent-specific tools stay inside the matching `agents/<name>` repo. Agents should not import from each other.

Read first:

- `GIT-DISCIPLINE.md` - repository ownership, ignored state, and commit/push rules.
- `CURRENT-STATE.md` - latest verified source/runtime state and resume instructions.
- `docs/LEARNINGS.md` - durable lessons from the cleanup.
- `docs/OPEN-QUESTIONS.md` - decisions not settled yet.

Git discipline: this directory is its own workspace/orchestration repo and contains nested repos. Do not treat a clean root status as proof nested packages are clean. Check the owning repo before editing, and do not leave important work local-only.
