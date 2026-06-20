# ADK workspace directory note

Purpose: top-level workspace for Forsch Google ADK agent development. This directory organizes one shared component package, five independent team-lead agent repos, and cross-agent documentation.

Structure:

- `components/` - shared Python package (`forsch-adk-components`) for reusable tools, models, and testing helpers. Authsome and Frappe clients belong here.
- `agents/` - parent folder for independent agent repositories. Each child agent owns its own package, tests, evals, and git history.
- `docs/` - cross-agent architecture and runbook documentation that applies to the whole ADK workspace.
- `README.md` - human overview and getting-started notes for the workspace.

Current organization rule: shared integration code goes in `components`; domain instructions and agent-specific tools stay inside the matching `agents/<name>` repo. Agents should not import from each other.
