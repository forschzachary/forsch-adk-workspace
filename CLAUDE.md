# ADK Agent Workspace — context for Claude (read this first)

You are running on the cloud box **hubertsp6**, in `/root/.hermes/workspace/adk`, as **root**.
This is the workspace for Forsch's **Google ADK agents**. Your job: help Zach design, build, and run agents — well, and lazily (see Working style).

## What this is
- **`agent_specs/agents.yaml` is the SINGLE SOURCE OF TRUTH** for every agent (a `defaults:` block + one block per agent).
- The **Factory** (`forsch.adk_factory`) deterministically generates each agent's package from `agents.yaml`: `agents/<id>/src/forsch/agent_<id>/agent.py` + `web_agents/<id>/root_agent.yaml`.
- The **Builder cockpit** (a node-canvas) edits `agents.yaml` + regenerates. You can also edit by hand.
- The native **adk-bridge** container runs the agents as a **Chainlit chat** surface.

## Layout (each of these is its own nested git repo unless noted)
- `agent_specs/agents.yaml` — the manifest (in the top-level workspace repo)
- `components/` — shared tools `forsch.adk_components.tools.*`; tests in `components/tests/`
- `factory/` — the generator `forsch.adk_factory`
- `builder/` — the cockpit canvas `forsch.adk_builder` (systemd `adk-cockpit`, host `:8780`, Funnel `:8443`) — in the workspace repo
- `bridge/` — the native container `forsch.adk_bridge` (Chainlit chat host `:8800`, Funnel `:10000`)
- `agents/<id>/`, `web_agents/<id>/` — generated; don't hand-edit, regenerate

## Current agents
`stability, assistant, brand, build, social, ops` (the 6 Forsch leads) + **`shelby`** — Zach's wife's personal agent, **v1 scaffold only**: groceries-over-time + trends + Apple Reminders with a read-back receipt. Her tools (`log_groceries`, `get_grocery_log`, `add_reminder`) are **not built yet**, and she's **not on the bridge PYTHONPATH yet** (so not runnable in chat). She's canvas-only for now.

## Common tasks
- **Edit/add an agent:** edit `agent_specs/agents.yaml`, then regenerate:
  `factory/.venv/bin/python -m forsch.adk_factory.cli apply --agent <id>`
- **Run component tests (FROM THE HOST):** `cd components && ./.venv/bin/python -m pytest -q`
- **Make an agent runnable in chat:** add `agents/<id>/src` to `bridge/compose.yaml` PYTHONPATH, then `cd bridge && docker compose up -d`. Code-only change to an already-wired agent → `docker restart adk-bridge`. New pip dep → `docker compose build`.

## GOTCHAS (these have actually bitten us — heed them)
- **`bridge.env` changes need `docker compose up -d` (RECREATE), not `docker restart`** — env loads at container create.
- **`FORSCH_ADK_WORKSPACE` must be set** (compose → `/workspace`; cockpit unit → `/root/.hermes/workspace/adk`). Tools fail-loud if it's missing. **NEVER hardcode `/opt/data/*`** — that's the dead fleet path; it's the bug that started all this.
- The **`hermes` container** bind-mounts this same tree at `/opt/data/workspace/adk` with a different python, so the `components/.venv` only resolves pytest/forsch from the **host** path. Run tests on the host, not inside hermes.
- **ADK SSE** emits `partial=True` deltas then a final `partial=False` event that repeats the full text — when streaming, yield only the deltas.
- A benign OpenTelemetry "context created in a different Context" error fires on standalone `run_async` teardown and on WS close — verify via the live `/chat`, not a standalone harness.
- **Commits here are LOCAL-ONLY** (no GitHub push path). Commit per nested repo with `git -c user.name=Hubert -c user.email=hubert@forsch.local`.

## Stability self-audit tools (recent)
`forsch.adk_components.tools.landmine_audit` → `scan_hardcoded_paths` + `check_env_contract` detect hardcoded-path / config-drift landmines. A plan to wire them into the stability agent + a CI "zero-high" gate is **deferred** (needs a bridge bounce). **Do NOT** reintroduce the deleted `propose_landmine_fixes`/`apply_landmine_fix` — they were cut on purpose (ponytail/YAGNI).

## Working style — lazy but precise (ponytail)
Before building anything: *does this need to exist? does it need to be this complex?* Smallest change that actually works; stdlib before deps; one line before fifty. Verify fixes with **new evidence** (a fresh log line / test result), never by assuming an edit is live (for daemons/containers that means a restart). State assumptions; ask only when genuinely ambiguous.
