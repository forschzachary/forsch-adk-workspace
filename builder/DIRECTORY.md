# ADK Builder directory note

Purpose: a small **library** exposing the manifest-editing + agent-promotion
primitives used across the workspace. The `forsch.adk_builder` name is kept for
its importers; the interactive cockpit UI (canvas, PTY terminal, `adk-cockpit`
systemd service, `:8443` funnel) was **removed 2026-07-01** — it was an
agent-built side-project and exposed a root shell on the public funnel.

Structure:

- `pyproject.toml` - package + test deps (ruamel.yaml + pyyaml).
- `src/forsch/adk_builder/editor.py` - `update_agent()`: apply a patch to
  `agent_specs/agents.yaml` and regenerate. Imported by
  `packages/live-agent-graph/serve.py` (save-agent-config) and the `forsch` CLI.
- `src/forsch/adk_builder/promote.py` - `promote_agent()` + patch helpers.
  Imported by the `forsch` CLI (`operator`, `main`, `goal_engine.actuators`).
- `tests/test_promote.py` - tests for the promotion helpers.

Not a uv workspace member (its own `pyproject`/`uv.lock`); `serve.py` runs it via
`builder/.venv` on the box.
