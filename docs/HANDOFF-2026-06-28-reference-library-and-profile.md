# Handoff — 2026-06-28 — Reference Library + Orchestrator Profile (+ session context)

> Box **hubertsp6**, repo `/root/.hermes/workspace/adk` (`forschzachary/forsch-adk-workspace`), `origin/main` canonical + gated. All work below is **merged to `main` + deployed**. The Mac checkout `/Users/zacharyforsch/Dev/live-agent-graph` is the OLD archived repo — do not edit it.

## TL;DR

Built (one unit, three PRs through the gate) a **reference library + reference tool + an orchestrator-profile overhaul** so the factory orchestrator (Hubert/MiMo) builds agents reference-first. Earlier in the same session: shipped per-cluster chat persistence, and did a full workspace cleanup (~1.4 GB reclaimed, branches down to `main`). Everything is live and verified.

## Current system state (verified live)

- **Services healthy:** `live-agent-graph` :8888 (systemd, active), `adk-api` :8001 (systemd, active), `adk-bridge` :8800 (docker, Up), `adk-cockpit` :8780 (systemd, active).
- **Gate armed:** ruleset `protect-main` (id 18233366), empty bypass, required checks `verify` + `control-plane-approved`. Direct push to `main` is rejected. Box authors zero commits; `deploy.sh` pulls (`reset --hard origin/main` → `uv sync --frozen --all-packages` → smoke → restart/rollback; systemd timer polls).
- **HEAD on main:** `aca9214` (at handoff time).
- **Branches:** just `main` locally + on origin (stale branches cleaned).

## What landed this session

### A. Reference library + orchestrator profile (the headline)
Spec: `docs/strategy/2026-06-28-reference-library-and-orchestrator-profile-design.md` (PR #20).

- **PR #21 — Reference library.** `docs/reference/<source>/` = local, version-controlled copies of the docs the orchestrator needs: `adk`, `mcp`, `litellm` (`llms-full.txt` each), `gradio` (inline `llms.txt`), `uv` (crawled ~54-page index), `mimo` (from `mimo --help`). ~7 MB markdown under the allowlisted `docs/`. Producer: `scripts/refresh_reference.sh` (re-runnable, fails loud, writes `MANIFEST.yaml` + per-source `INDEX.md`). **Never hand-edit `docs/reference/` — regenerate.**
- **PR #22 — Reference tool.** `packages/adk-components/src/forsch/adk_components/tools/reference_tools.py` — `@tool(family="reference", safety="read_only")`: `search_reference(query, source?)` (ripgrep + **Python fallback because `rg` is NOT installed**) and `read_reference(path, section?)` (path-traversal-safe). Bounded output. Exported in `tools/__init__.py`. 11 hermetic tests in `packages/adk-components/tests/test_reference_tools.py`.
- **PR #24 — Orchestrator profile.** Overhauled the pre-migration `<repo>/CLAUDE.md` into "Hubert the factory orchestrator" (identity + evidence discipline, reference-first, build-a-repeatable-agent loop, the gate as iron law). Added `preambles/README.md` documenting Layer B. **Verified live:** `mimo run --dir <repo> "..."` had Hubert cite `docs/reference/` + `search_reference` + "box authors zero commits."

### B. Earlier this session (also live)
- **Chat feature (PR #18):** per-cluster chat persistence in `packages/live-agent-graph/index.html` (localStorage `lag-chat-v1:<cluster>`, 200-msg cap), tool-call collapse + `hubert-show-tools` toggle, red `✕ failed` marker.
- **Cleanup (PR #19 + ops):** removed 2 tracked `.pyc`; reclaimed ~1.4 GB (`adk-backups` 2.0G→676M, kept only the authoritative tar + wow-guild bundle + child-heads); deleted stale branches + caches.

## Pending / deferred / known debt

1. **Factory-contracts pattern spec (the next big effort).** `docs/strategy/2026-06-28-factory-contracts-open-requirements.md` (R1–R8 + 6 patterns, C1–C4 decided) is unblocked by the migration but NOT yet built. This is the natural next design→build.
2. **`packages/adk-components/tests` not in the `verify` gate.** Gate runs `pytest agents`. adk-components tests (incl. the new `test_reference_tools.py`) are local evidence only; the broken `shelby` test (hardcoded `data/shelby_schema.sql` path) blocks adding the whole suite. Fix that path → can add to the gate.
3. **Legacy suites excluded from gate** (`bridge/builder/chat/factory/tests`) — not workspace members; pre-existing debt.
4. **`rg` not installed on the box** — `search_reference` uses its Python fallback (works). `apt install ripgrep` would speed it up. Cosmetic.
5. **Parent `AGENTS.md` outside the repo:** `/root/.hermes/workspace/AGENTS.md` (box-level Hermes/LiteLLM/Authsome context) is also fed to Hubert and is NOT gate-controlled. Left as-is, documented in `CLAUDE.md` §6.
6. **bridge Discord token:** scrubbed from monorepo history, **not rotated** (operator's explicit choice). Still live in the archived `forsch-adk-bridge` remote.
7. **Landmine-audit wiring** into the stability agent + a CI "zero-high" gate is deferred (needs a bridge bounce). Do NOT reintroduce the deleted `propose_landmine_fixes`/`apply_landmine_fix`.

## Key facts & gotchas (load-bearing — verified this session)

- **How Hubert is fed:** mimocode walks UP from cwd reading instruction files — prefers `AGENTS.md` (21× in the binary), then `CLAUDE.md` (10×). Hubert's stack = `<repo>/CLAUDE.md` (ADK profile, gated) + `/root/.hermes/workspace/AGENTS.md` (box context, ungated). A standalone `CRITICALRULES.md` would NOT auto-load → profile lives in `CLAUDE.md`.
- **Two layers:** (A) orchestrator = `CLAUDE.md`; (B) built agents = `preambles/<group>.md` (prepended by `factory/renderer.py:compose_instruction`) + `agents.yaml` `instruction:`. `group: hubert-team-lead` (agents `assistant`, `build`) → `preambles/hubert-team-lead.md` (WIRED — don't retire).
- **Workspace-root resolver trap:** `workspace_resolver.workspace_root()` reads `FORSCH_WORKSPACE`/`HERMES_HOME` and returns the workspace **parent**. The ADK **repo root** is `FORSCH_ADK_WORKSPACE` (compose → `/workspace`; cockpit → `/root/.hermes/workspace/adk`). For repo-relative paths use `FORSCH_ADK_WORKSPACE`.
- **`factory/`, `builder/`, `bridge/`, `chat/` are NOT uv workspace members** (members are `packages/*`, `agents/*`, `clusters/*`). Factory CLI: `factory/.venv/bin/python -m forsch.adk_factory.cli apply --agent <id>`.
- **`uv` is at `/root/.local/bin/uv`**, not on the non-interactive PATH. Run component tests: `uv run --with pytest python -m pytest packages/adk-components/tests/<file> -q`.
- **Editing box files from a Mac/Claude session:** scp file → scratchpad → Read/Edit → scp back → branch → PR → merge → deploy. Box PAT lacks `workflow` scope — pushes touching `.github/workflows/` need the Mac `gh auth token`.
- **MiMo invocation** (`serve.py:chat_with_mimo`): `mimo run --format json --dir MIMO_WORKDIR [-m model] [-s session] <message>`; `MIMO_WORKDIR = workspace_root()/"adk"`. `mimo run` first calls are slow (cold) — give them >90 s.
- Never hardcode `/opt/data/*` (dead fleet path; the hermes container bind-mounts the tree there). `bridge.env` changes need `docker compose up -d` (recreate), not restart. ADK SSE: yield only `partial=True` deltas.

## How to operate (the loop)

1. Edit on the box (or scp from Mac). 2. `git checkout -b <branch> main`, commit, `git push origin <branch>`. 3. `gh pr create …`. 4. Wait for `verify` + `control-plane-approved` (routine PRs pass in ~20–30 s). 5. `gh pr merge <n> --rebase --delete-branch`. 6. `/root/.hermes/deploy.sh` (or wait for the timer). 7. **Verify with new evidence** (a fresh log/test/200), never assume.

## Where things are

- Spec + strategy docs: `docs/strategy/2026-06-28-*.md`
- Reference library: `docs/reference/` · refresh: `scripts/refresh_reference.sh`
- Reference tool: `packages/adk-components/src/forsch/adk_components/tools/reference_tools.py`
- Orchestrator profile: `<repo>/CLAUDE.md` · Layer-B doc: `preambles/README.md`
- Backups (authoritative rollback): `/root/adk-backups/adk-pre-monorepo-2026-06-28.tar.gz` (+ wow-guild bundle, child-heads)
- Memory (Mac): `~/.claude/projects/-Users-zacharyforsch-Dev-live-agent-graph/memory/` (`monorepo-consolidation-decision.md`, `reference-library-and-orchestrator-profile.md`)
