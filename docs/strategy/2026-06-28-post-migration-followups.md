# Post-Migration State & Documented Debt — forsch-adk-workspace

Date: 2026-06-28. The monorepo migration is complete (`main` = the consolidated tree, ruleset `protect-main` armed). This records the deliberate decisions and known debt so nothing is an undocumented loose end.

## Migration outcome (done)

- One repo, zero embedded repos; `git subtree`-absorbed history preserved.
- uv workspace (`packages/*`, `agents/*`, `clusters/*`), single `uv.lock`, `requires-python >=3.10`.
- `agent_specs/agents.yaml` is the canonical spine; the control-surface registry is a presentation overlay. `screening` materialized (7 tools + shim).
- Server-side gate: ruleset `protect-main` (require-PR + required checks `verify` + `control-plane-approved` + block force-push + restrict deletions + linear history + **empty bypass**). A direct push to `main` is empirically **rejected**.
- Both services re-pointed and healthy: `live-agent-graph` :8888, `adk-api` :8001.
- 10 absorbed standalone remotes archived (read-only, reversible).

## Documented decisions / known debt

### 1. `bridge` Discord token — scrubbed, not rotated (operator's choice)
`bridge` commit `66e32af` carried a Discord bot token in `bridge.env.bak-…`. It was **removed from the monorepo history** via `git-filter-repo` before absorption, so the token is **not** in `forsch-adk-workspace`. The operator chose **not to rotate** it; the live token therefore remains valid and present in the **archived** `forsch-adk-bridge` remote's history. Accepted risk. To fully close: rotate the token in the Discord developer portal.

### 2. Legacy test suites excluded from the gate (intentional)
The `verify` gate runs `pytest` scoped to **`agents/`** (the workspace agents' import-smoke tests). The following are **excluded** because they are not uv workspace members and/or carry pre-existing breakage:
- `bridge/tests`, `builder/tests`, `chat/tests`, `factory/tests` — not workspace members; their deps/conftests are not installed in the workspace venv.
- `packages/adk-components/tests` — hit a hardcoded archived path (`data/shelby_schema.sql`); needs env-var path resolution (a patterns-library fix).

These are tracked as test debt. Re-add each to the gate once it is a workspace member (or has CI-safe, path-independent tests). This does **not** weaken the meaningful gate — `uv lock --check`, `check_structure.py`, `check_bijection.py`, and `uv build` all run as blocking checks.

### 3. GitOps deploy
The box deploys via `/root/.hermes/deploy.sh` (pull-based: fetch → fail-closed guard → `reset --hard origin/main` → `uv sync --frozen` → smoke → restart-or-rollback). The box authors **zero** commits on the source of truth (R-GATE-2). A systemd timer polls as the backstop.

## Next work (unblocked by this migration)

The **agent-factory pattern-contracts spec** (`2026-06-28-factory-contracts-open-requirements.md`) is now unblocked — it lands on the consolidated, gated foundation. R1–R8 + the Builder/Command spine + C1–C4 are decided; the remaining open items are implementation-level (pytest scope, janitor threshold). This is the next design→build effort.
