# Builder Cockpit — Phase 1 status (read-only dashboard)

**Status: Phase 1 COMPLETE and browser-verified (2026-06-20).** Built strict-TDD
(every test watched RED before GREEN). 28 tests green.

## What exists (`builder/`)

| Module | Role | Tests |
|---|---|---|
| `src/forsch/adk_builder/metadata.py` | parse YAML frontmatter from Python docstrings (`ast.get_docstring`); map agents.yaml `purpose`→description, `safety_level`→risk. Warn-not-crash. | 7 |
| `src/forsch/adk_builder/collector.py` | read-only static walk → `Workspace` model (agents joined from contract+pkg+wrapper+route+tools+metadata, shared tools, docs, bridge routes). Surfaces drift + missing metadata. No runtime imports. | 9 |
| `src/forsch/adk_builder/renderer.py` | `render_dashboard(workspace)` → self-contained HTML (Jinja2, autoescaping). | 9 |
| `src/forsch/adk_builder/app.py` | Starlette `create_app(workspace_root)`; re-collects per request (no stale cache); GET-only. | 3 |
| `templates/index.html` | dashboard: READ ONLY banner, left nav, per-agent cards, warning/drift panel, docs, glossary, disabled Phase-2 buttons. | — |

Run: `cd builder && .venv/bin/python -m pytest tests -q` → **28 passed**.
Serve: `PYTHONPATH=src FORSCH_ADK_WORKSPACE=<workspace> .venv/bin/python -m forsch.adk_builder.app` (127.0.0.1:8765).

## Verification (against the LIVE workspace)

Rendered the real `/opt/data/workspace/adk`: **1 agent** (stability), **5 components**
(stability_audit, authsome_client, crm_tools, frappe_client, stability_tools),
**16 docs**, **6 bridge routes**, **11 warnings**, 12KB HTML. Browser: 200, no console
errors, READ ONLY banner visible, grid layout correct (240px + main, no overlap),
data matches the workspace. The cockpit correctly surfaces the **5-agent drift**
(ops/social/brand/assistant/build routed in the bridge but absent from the agent
contract — only `stability` has a contract).

## Two real bugs caught by running against the live workspace (each fixed TDD)

1. Crashed on scalar bridge entries (`dm_fallback: assistant` under `agents:`) → guard non-dict, skip.
2. Tool scan recursed into nested `.venv`/`site-packages` (11426 junk "tools", 5.8MB HTML) → skip installed-dep/cache dirs. Real workspace now: 5 tools, 12KB.

## ⚠️ Push blocker (needs Zach)

All Phase-1 commits are **local-only on the box** (not pushed to GitHub) — this host
has no GitHub credential path: `GITHUB_TOKEN` unset, no `gh`, no `~/.git-credentials`,
**Authsome CLI not installed** (daemon up at :7998, but no `authsome` binary). See
`docs/OPEN-QUESTIONS.md`. To push: install Authsome CLI / set `GITHUB_TOKEN` / install
`gh`, then `git push origin main`.

## Next: Phase 2 (guarded edit actions)

add-tool / edit-instruction / generate-web-wrapper / run-smoke-test, each with
backup → atomic write → validate → rollback. Primitives are TDD-able against temp
dirs without touching the live workspace.
