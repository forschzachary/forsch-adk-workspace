# Docs directory note

Purpose: cross-agent documentation for the ADK workspace. These docs explain patterns that span more than one repo, so they live outside individual agents.

Structure:

- `ARCHITECTURE.md` - system shape, agent boundaries, shared component pattern, credential flow, and data-flow conventions.
- `RUNBOOK.md` - commands for installing, testing, adding tools/agents, and verifying Authsome/Frappe behavior.
- `STABILITY_GOVERNOR_RUNBOOK.md` - read-only stability audit commands, ADK Web wrapper, Discord route, and safety boundary.
- `STABILITY_ALERT_TRACKING.md` - stability alert schema, current alert ledger, severity guide, and update rules.
- `STABILITY_ARCHITECT_OVERNIGHT_WORKLOG.md` - active supervised evaluation log for the Stability Architect.

Current organization rule: repo-specific details belong in each repo's README or `DIRECTORY.md`; architectural conventions and shared operating procedures belong here.

Read these before continuing project work:

- `LEARNINGS.md` - durable cleanup and runtime lessons.
- `OPEN-QUESTIONS.md` - unresolved project decisions.
- `STABILITY_GOVERNOR_RUNBOOK.md` - Stability Governor usage and safety boundary.
- root `../GIT-DISCIPLINE.md` - repo ownership and commit/push rules.
