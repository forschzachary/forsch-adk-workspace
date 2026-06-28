# Reference Library + Orchestrator Profile — Design Spec

> Date: 2026-06-28 · Repo: `forsch-adk-workspace` · Status: **for review**
> Scope: make Hubert (the MiMo orchestrator) a reference-first, factory-disciplined builder, and make the inputs to the agents he *builds* fully transparent and operator-controlled.

## 1. Goal

One sentence: **give the factory orchestrator a local, version-controlled reference library + a tool to read it, rewrite his profile so he builds repeatable agents reference-first, and make the instruction inputs to every built agent visible and operator-owned.**

This is one unit of work, but it splits cleanly into **two layers** that must not be conflated:

- **Layer A — the Orchestrator (Hubert/MiMo).** The thing Zach chats with to *build* agents. Tuned for: reference the right docs, follow the factory + gate discipline, produce repeatable agents.
- **Layer B — the Built Agents** (stability, assistant, brand, …). What Hubert produces. Their inputs must be transparent and operator-controlled — Zach is "strictly in charge of what the ADK agents are fed."

## 2. Current state (grounded — verified on the box)

- **Hubert/MiMo** runs as `mimocode` via `serve.py:chat_with_mimo()` with `cwd = WS` (the monorepo root, `workspace_root()/"adk"`). mimocode is Claude-Code-lineage and its cwd is exactly where `CLAUDE.md` lives, so `<root>/CLAUDE.md` (4.3 KB) is almost certainly Hubert's standing instruction set today. **⚠️ This is the linchpin assumption for Component 3 and is verified as planning task 0 before any profile is written** (see §11) — if mimocode keys off a different file (an `AGENTS.md`, a config field, a `--system-prompt`), Component 3 simply targets that file instead; the design is otherwise unchanged. No reference tool, no factory-orchestration profile exists today.
- **Built agents** get their instruction from `factory/renderer.py:compose_instruction(spec, workspace_root)` = `load_preamble(spec.group)` + `"\n\n"` + the agent's `agent_specs` `instruction:` job. `load_preamble` reads `preambles/<group>.md`. Today exactly one preamble exists: `preambles/hubert-team-lead.md` (1.3 KB — Hubert persona + evidence discipline). **This group-preamble layer was invisible to the operator.** It is wired and load-bearing (referenced by `renderer.py`, `cli.py`, `models.py`, the registry, the graph) — it is **not** retired.
- **Reference docs:** `docs/` holds *house* docs (`ARCHITECTURE.md`, `AGENT_FACTORY_SPEC.md`, `adk-vocabulary-map.html`, …) — Forsch-specific conventions. There are **no external framework docs** (ADK, Gradio, LiteLLM, MCP, uv, MiMo) anywhere locally.
- **Tool pattern:** tools are Python functions decorated with `@tool(family=…, safety=…)` from `packages/adk-components/src/forsch/adk_components/patterns/tool_decorator.py`, living under `…/adk_components/tools/`, catalogued in `…/patterns/inventory.yaml`.
- **Gate:** every change lands by PR → required checks (`verify` + `control-plane-approved`) → merge → `deploy.sh` pulls. `verify` runs `uv lock --check`, `check_structure.py`, `check_bijection.py`, `uv build`, and `pytest agents`. `docs/` is allowlisted in `repo_manifest.yaml`.

## 3. Architecture — four components across the two layers

| # | Component | Layer | Where |
|---|---|---|---|
| 1 | Reference library (the wiki-fied docs) | A | `docs/reference/<source>/` |
| 2 | Reference tool (`search_reference` / `read_reference`) | A | `…/adk_components/tools/reference_tools.py` |
| 3 | Orchestrator profile (Hubert) | A | `<root>/CLAUDE.md` + `<root>/CRITICALRULES.md` |
| 4 | Built-agent input transparency | B | `preambles/README.md` + `agent_specs` (documented, kept operator-owned) |

Clean boundaries: **1 is data**, **2 is access to that data**, **3 is the orchestrator's behavior** (consumes 2), **4 is making layer-B inputs legible** (independent of 1–3).

## 4. Component 1 — Reference library (`docs/reference/`)

### Layout
```
docs/reference/
  INDEX.md            # human + agent entry point: one line per source, what it covers
  MANIFEST.yaml       # machine record: per-source {url, method, fetched_utc, files, bytes}
  adk/        adk-llms-full.md            INDEX.md
  mcp/        mcp-llms-full.md            INDEX.md
  litellm/    litellm-llms-full.md        INDEX.md
  gradio/     gradio-llms.md              INDEX.md
  uv/         uv-<page>.md (×~40)         INDEX.md
  mimo/       mimo-cli.md                 INDEX.md
```

### Sources + fetch method (all verified reachable 2026-06-28)
| Source | Method | URL | Size |
|---|---|---|---|
| Google ADK (Python) | `llms-full.txt` (one file) | `https://adk.dev/llms-full.txt` | ~3.0 MB |
| MCP | `llms-full.txt` | `https://modelcontextprotocol.io/llms-full.txt` | ~1.9 MB |
| LiteLLM | `llms-full.txt` | `https://docs.litellm.ai/llms-full.txt` | ~540 KB |
| Gradio | inline `llms.txt` (full docs in one file) | `https://www.gradio.app/llms.txt` | ~282 KB |
| uv | crawl `llms.txt` index → ~40 `*/index.md` pages → concat | `https://docs.astral.sh/uv/llms.txt` | ~moderate |
| MiMo CLI | assemble from `mimo --help` + subcommand help (acp, mcp, run, providers, agent, debug) | local CLI | small |

Total ≈ 5.7 MB of markdown.

### `MANIFEST.yaml` schema
```yaml
generated_utc: "2026-06-28T..."        # stamped by the refresh script
sources:
  adk:
    url: https://adk.dev/llms-full.txt
    method: llms-full
    fetched_utc: "..."
    files: [adk/adk-llms-full.md]
    bytes: 3145728
  uv:
    url: https://docs.astral.sh/uv/llms.txt
    method: crawl-index
    fetched_utc: "..."
    files: [uv/uv-projects.md, ...]
    bytes: ...
```

### `scripts/refresh_reference.sh`
Idempotent re-fetch of every source into `docs/reference/`, rewriting each file + regenerating `MANIFEST.yaml` and per-source `INDEX.md`. Re-runnable any time to refresh the wikis (so they never silently rot). Exit non-zero if any source returns non-200 or empty, so a stale fetch is loud, not silent. Run manually; lands via a normal PR.

### Gate / bijection
Lives under the already-allowlisted `docs/`, so `check_structure.py` / `check_bijection.py` do not flag it. ~5.7 MB of markdown is fine in plain git (diffs cleanly, versioned, offline, gate-protected). No git-LFS.

## 5. Component 2 — Reference tool

`packages/adk-components/src/forsch/adk_components/tools/reference_tools.py`:

```python
@tool(family="reference", safety="read_only")
def search_reference(query: str, source: str | None = None) -> dict:
    """Search the local reference wikis (docs/reference/) for `query`.
    Optionally restrict to one source (adk|mcp|litellm|gradio|uv|mimo).
    Returns ranked hits: {source, file, heading, snippet}. Bounded output."""

@tool(family="reference", safety="read_only")
def read_reference(path: str, section: str | None = None) -> dict:
    """Return the content of a reference file under docs/reference/.
    Optionally just one markdown section (by heading). Bounded output."""
```

- **Search backend:** ripgrep over `docs/reference/` (already on the box); fall back to Python scan if `rg` is absent. Group hits by file, attach the nearest preceding `#`/`##` heading + a snippet window.
- **Path safety:** resolve `path` under `docs/reference/` and reject anything that escapes it (no `..`, no absolute paths). `read_only` safety tier.
- **Output bounds:** cap total bytes returned (e.g. ≤ 24 KB) and number of hits (e.g. ≤ 25) so a query can't blow the agent's context; say "N more hits — narrow the query" when truncated.
- **Registration:** add to `…/patterns/inventory.yaml` under family `reference` so any agent (Hubert first) can call it.
- **Workspace root:** resolve `docs/reference/` via `FORSCH_ADK_WORKSPACE` (the existing `workspace_resolver`), never a hardcoded path.

## 6. Component 3 — Orchestrator profile (Hubert)

Hubert's standing instructions = `<root>/CLAUDE.md` (what mimocode reads). Restructure into a small `CLAUDE.md` that `@`-imports a canonical **`CRITICALRULES.md`** (the detailed profile), so there is **one** authoritative, version-controlled file the operator owns. Sections:

1. **Identity** — Hubert as factory orchestrator. Seeds from the existing `hubert-team-lead.md` persona + evidence discipline (kept verbatim where good: "done requires NEW evidence", "never fabricate", "no intros").
2. **The ADK workspace model** — distilled from `docs/ARCHITECTURE.md` + `AGENT_FACTORY_SPEC.md` + the vocabulary map: agents/clusters/tools/datasources/routers, `agent_specs/agents.yaml` as the spine, the factory, the bridge, the graph.
3. **How to build a repeatable agent** — the factory CLI (`adk_factory apply --agent <id>`), what's generated vs hand-edited, the preamble+instruction model (Layer B), wiring to the bridge, regeneration.
4. **The gate discipline (iron laws)** — box authors zero commits; every change is a PR through `verify` + `control-plane-approved`; never force-push `main`; never commit secrets (`.serve-env`, `bridge.env`); no-fluff bijection (only what's on the graph).
5. **Reference-first** — *before building or answering an ADK/Gradio/LiteLLM/MCP/uv/MiMo question, call `search_reference`.* Includes the catalog of the six wikis and when each applies.
6. **Anti-fabrication** — cite what was read (a path/value/log), not what was assumed; the GitHub org is `forschzachary`.

This file is the operator's control surface for Hubert; editing it = tuning Hubert.

## 7. Component 4 — Built-agent input transparency (Layer B)

The operator must be able to see and own **everything fed to a built agent**. The real input is `preambles/<group>.md` + `agent_specs[<id>].instruction`. Make that legible:

- **`preambles/README.md`** — document the group-preamble mechanism: every built agent's final instruction = its group preamble + its `agent_specs` job; list existing groups → preamble files; state that these two files are the *only* things fed to a built agent and both are operator-owned and gate-protected.
- **Keep `hubert-team-lead.md`** (wired, load-bearing) — optionally rename to `<group>.md` clarity if the group name differs, but no behavior change in this unit.
- **No UI work in this unit.** Surfacing preamble + instruction in the builder cockpit is noted as a follow-up; here we make it transparent in-repo (docs) so nothing is hidden.

## 8. Data flow (Hubert building an agent)

```
operator: "add a finance lead that reads our P&L"
  → Hubert (CRITICALRULES profile) recognizes a build task
  → search_reference("ADK agent tool FunctionTool", source="adk")   # reference-first
  → read_reference("adk/adk-llms-full.md", section="Tools")
  → edits agent_specs/agents.yaml (+ a group preamble if new)
  → runs factory apply  →  PR through the gate  →  merge  →  deploy
  → reports with evidence (the PR, the green checks)
```

## 9. Testing

- **`reference_tools`** (pytest, a workspace member so it runs in `verify`):
  - `search_reference("workspace")` returns ≥1 hit with `{source,file,heading,snippet}`.
  - `source=` filter restricts results to that source.
  - `read_reference` returns content; `section=` returns just that heading's body.
  - path-traversal (`../../etc/passwd`, absolute paths) is rejected.
  - output respects the byte/hit cap (truncation flagged).
- **`refresh_reference.sh`** — manual: run twice, second run is a no-op diff except timestamps; non-200/empty source exits non-zero.
- **Profiles** (CLAUDE.md / CRITICALRULES.md / preambles/README.md) — content, not code: validated by operator review + a live `/chat` smoke ("what does search_reference give you?" → Hubert lists the six wikis).

## 10. Decisions (locked unless operator objects)

1. **Refresh script:** yes — `scripts/refresh_reference.sh`, not a one-shot fetch.
2. **Plain git** for the ~5.7 MB markdown — no LFS.
3. **`hubert-team-lead.md`: KEPT** (correction from the design chat — it is wired into `renderer.py` for built agents, not a stray Hubert preamble). Its persona *seeds* the orchestrator profile; the built-agent preamble layer is documented, not removed.
4. **Spec location:** `docs/strategy/` (matches the repo's existing strategy/spec docs), not `docs/superpowers/specs/`.
5. **Profile shape:** `CLAUDE.md` stays small and `@`-imports a canonical `CRITICALRULES.md`.

## 11. Open / deferred

- **Planning task 0 (blocking Component 3):** confirm the exact file/mechanism mimocode reads for standing instructions (expected `<root>/CLAUDE.md`; verify empirically — inspect the `mimo` CLI/help/config or a live `/chat` probe). The profile work targets whatever that file actually is.
- Surfacing per-agent `preamble + instruction` in the builder cockpit UI (Layer-B control) — follow-up, not this unit.
- Exact uv crawl page list — enumerated during planning from the live `llms.txt`.
- Whether MiMo grows a non-`CLAUDE.md` system-prompt hook later — out of scope; today CLAUDE.md is the lever.

## 12. Rollout (each a PR through the gate, then deploy + smoke)

- **PR 1 — Reference library:** `docs/reference/**` + `MANIFEST.yaml` + `scripts/refresh_reference.sh`.
- **PR 2 — Reference tool:** `reference_tools.py` + tests + `inventory.yaml` registration.
- **PR 3 — Profiles:** `CRITICALRULES.md` + `CLAUDE.md` rewrite + `preambles/README.md`.

Sequenced so the tool ships after the data it reads, and the profile ships after the tool it references.
