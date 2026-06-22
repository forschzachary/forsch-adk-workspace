# Forsch ADK Builder Cockpit Goal

**Max turns:** 200

## High-level goal

Build the Forsch ADK Builder Cockpit: a sidecar web application for `/opt/data/workspace/adk` that starts as a read-only dashboard and later becomes a guarded builder UI with edit actions.

The cockpit must help Zach and Hubert understand and modify ADK agents as if they were operating from inside a proper builder UI, while avoiding the ambiguity of raw filenames in ADK Web.

## Core problem

Google ADK Web is a runtime conversation and testing surface. It shows agent files and wrappers, but it does not explain:

- what each file does
- whether it is canonical or generated
- whether it is safe to edit
- what depends on it
- what tests prove it still works
- which docs explain its purpose
- whether it belongs to an agent, a shared component, a wrapper, or a bridge route

The cockpit fills that missing builder mental model.

## Required operating posture

Follow strict TDD for all implementation work.

For every behavior:

1. Write the failing test first.
2. Run it and confirm it fails for the expected reason.
3. Write the smallest implementation that makes it pass.
4. Run the specific test and then the relevant suite.
5. Refactor only after green.

Load and follow relevant skills along the way, especially:

- `test-driven-development` for implementation cycles
- `claude-design` for UI/dashboard design work
- `systematic-debugging` if tests or runtime behavior fail in unclear ways
- `hermes-agent` only if modifying Hermes itself, which this task should not require

## Authoritative sources

Use these files as source context:

- `/opt/data/workspace/adk/README.md`
- `/opt/data/workspace/adk/DIRECTORY.md`
- `/opt/data/workspace/adk/docs/ARCHITECTURE.md`
- `/opt/data/workspace/adk/docs/AGENT_FACTORY_SPEC.md`
- `/opt/data/workspace/adk/docs/STABILITY_GOVERNOR_AGENT_DESIGN.md`
- `/opt/data/workspace/adk/agent_specs/agents.yaml`
- `/opt/data/workspace/adk/bridge/bridge_config.yaml`
- all `DIRECTORY.md` files under `/opt/data/workspace/adk`

Also reference Google ADK documentation when ADK behavior is uncertain. Do not guess ADK internals when docs or source can be checked.

## Vocabulary the cockpit must enforce

Use precise nouns in UI and code:

- **agent contract**: canonical agent definition, primarily `agent_specs/agents.yaml`
- **runtime package**: the real agent package under `agents/<name>/`
- **root agent**: the exported ADK object loaded by ADK Runner, usually `root_agent`
- **shared component**: reusable client/tool/schema/test helper under `components/`
- **tool wrapper**: ADK-callable function exposed to agents
- **client**: lower-level API or service client used behind a tool wrapper
- **web wrapper**: thin ADK Web entrypoint under `web_agents/<name>/`
- **bridge route**: Discord/channel routing under `bridge/bridge_config.yaml`
- **quality gate**: tests, evals, import checks, smoke prompts, and stability verdicts
- **doc link**: pointer from a component to canonical markdown explanation

Avoid mushy labels like `agent file`, `the UI`, `config`, or `tools` unless refined by context.

## Phase 1: read-only dashboard

Build a read-only sidecar dashboard. This phase must not implement edit actions.

### Phase 1 deliverables

Create `/opt/data/workspace/adk/builder/` containing a tested Python web app.

Minimum file shape:

```text
builder/
├── DIRECTORY.md
├── pyproject.toml
├── src/forsch/adk_builder/
│   ├── __init__.py
│   ├── app.py
│   ├── collector.py
│   ├── metadata.py
│   ├── models.py
│   └── renderer.py
├── templates/
│   └── index.html
└── tests/
    ├── test_metadata.py
    ├── test_collector.py
    └── test_renderer.py
```

If a flatter layout is chosen for speed, document the reason in `builder/DIRECTORY.md`. Prefer package layout unless there is a strong reason not to.

### Metadata/frontmatter convention

The dashboard needs human-readable metadata for tools, YAML specs, wrappers, and docs.

Implement metadata parsing before UI.

#### Python files

Python files may contain a module-level docstring with a YAML block:

```python
"""
---
display_name: Workspace Inventory
description: Scans the ADK workspace and returns a structured inventory.
doc_link: docs/STABILITY_GOVERNOR_RUNBOOK.md
owner: stability
risk: read_only
kind: tool_wrapper
---
"""
```

The parser must:

- use `ast.get_docstring`, not regex alone
- safely parse YAML frontmatter if present
- return warnings instead of crashing on malformed metadata
- tolerate files with no metadata
- preserve path and line context where practical

#### YAML specs

YAML specs may contain human fields directly:

```yaml
agents:
  stability:
    display_name: Stability Governor
    description: Audits the ADK workspace and reports evidence-backed stability findings.
    doc_link: docs/STABILITY_GOVERNOR_AGENT_DESIGN.md
```

The parser must:

- safely parse YAML
- distinguish required machine fields from human-friendly fields
- warn when display metadata is missing
- never rewrite YAML during Phase 1

#### Markdown docs

Markdown files may later gain frontmatter, but Phase 1 should at least discover and link existing `.md` docs.

### Phase 1 TDD sequence

#### 1. RED: metadata parser tests

Write tests first for:

- valid Python docstring frontmatter parses into metadata model
- Python file without frontmatter returns empty metadata plus no crash
- malformed Python frontmatter returns a warning
- YAML agent spec display fields parse into metadata model
- YAML agent spec without display fields returns warning, not exception

Run tests and verify failure.

#### 2. GREEN: metadata parser implementation

Implement the smallest parser to satisfy those tests.

Then run:

```bash
uv run pytest tests/test_metadata.py -v
uv run pytest tests -q
```

Use the correct `uv` command based on actual project layout.

#### 3. RED: workspace collector tests

Write tests for a temporary fixture workspace that includes:

- `agent_specs/agents.yaml`
- one agent runtime package
- one web wrapper
- one bridge route
- one shared component tool file
- one markdown doc

Expected collector output should include:

- agents
- tools/components
- web wrappers
- bridge routes
- docs
- warnings
- paths
- risk labels
- missing metadata warnings

#### 4. GREEN: collector implementation

Implement collector that walks the workspace and returns one structured model suitable for rendering.

It must be read-only.

Do not import runtime agent modules just to inspect them unless a test explicitly justifies that. Prefer static file and YAML inspection in Phase 1.

#### 5. RED: renderer tests

Write tests that feed collector output into a renderer and assert the HTML contains:

- each agent by stable ID
- the agent contract path
- runtime package path
- web wrapper path if present
- bridge route if present
- tool display names/descriptions
- warning badges for missing metadata
- links to docs where available
- clear read-only banner

#### 6. GREEN: dashboard app/UI

Build a sidecar web app that serves the dashboard.

Preferred stack:

- FastAPI or Starlette
- Jinja2 templates
- static CSS embedded or served from local static files
- no external network dependencies for UI assets

Dashboard design requirements:

- dense but readable
- explicit `READ ONLY` status
- strong left navigation by agent/component
- central panel showing agent contract, package, wrappers, routes, tools, docs, gates
- warning panel for missing metadata and drift risks
- glossary panel using the vocabulary above
- clear affordance for future edit actions, but disabled in Phase 1
- responsive enough to use on a laptop screen

#### 7. Phase 1 verification

Run tests.

Start the server locally and verify with browser tools:

- page loads
- no console errors
- screenshot has no obvious clipping or overlap
- read-only banner is visible
- data matches current workspace

Record exact commands and results in the final response.

## Phase 2: guarded builder cockpit with edit actions

Only begin Phase 2 after Phase 1 is complete and verified.

Phase 2 adds guarded write actions. All writes must target canonical sources, not random generated files.

### Phase 2 edit actions

Implement these actions TDD-first:

1. **Add tool to agent**
   - UI button/form: add a selected tool wrapper to an agent contract.
   - Backend updates `agent_specs/agents.yaml` only.
   - Then runs validation/tests.

2. **Edit instruction**
   - UI form: edit canonical instruction source.
   - Prefer `instruction_file` if present; otherwise make explicit whether using `instruction_inline`.
   - Must not edit generated wrappers directly.

3. **Generate web wrapper**
   - UI button: generate or refresh `web_agents/<name>/` from canonical spec/factory template.
   - Must show preview/diff before writing unless test plan explicitly permits controlled temp-workspace writes.

4. **Run smoke test**
   - UI button: run configured smoke prompt or import check for an agent.
   - This may be read-only and can be implemented before write actions if useful.

### Phase 2 safety rules

Every write action must include:

- backup before write
- atomic write pattern where practical
- schema validation before and after write
- post-edit test/verification command
- rollback on failed validation unless rollback itself is unsafe
- UI display of what changed and what command verified it
- clear error if workspace is dirty in the target repo

Never write to secrets, `.env`, `.venv`, caches, SQLite DBs, or ADK session files.

Never restart live bridge/services unless explicitly authorized by Zach.

Never patch Google ADK itself.

### Phase 2 TDD sequence

For each action:

1. RED: endpoint/action test against temp workspace.
2. GREEN: minimal backend implementation.
3. RED: renderer/UI affordance test.
4. GREEN: UI wiring.
5. Verify success and failure paths.
6. Refactor while tests remain green.

## Adversarial pass: failure modes to guard against

Design and tests should defend against:

- stale UI data after files change
- missing or malformed frontmatter
- YAML comments or ordering destroyed by naive rewrites
- bridge route and agent spec disagreeing
- web wrapper imports pointing at missing runtime package
- tools listed in spec but absent from component package
- tools discovered in package but undocumented
- generated/temp ADK files being mistaken for canonical files
- dirty git worktree before write action
- accidental import side effects while collecting metadata
- network dependency in dashboard rendering
- UI implying edit actions are live before they are implemented
- test commands passing because they did not run anything meaningful

## Current parallel-work constraint

It is acceptable for another agent to work on `bridge/` while this task works on `builder/`, provided:

- Phase 1 dashboard remains read-only.
- This task does not modify `bridge/bridge_config.yaml` without explicit permission.
- If bridge routes change externally, refresh collector output and report drift.
- Treat `agent_specs/agents.yaml` and `bridge/bridge_config.yaml` as interface files. Avoid concurrent edits unless explicitly coordinated.

## Definition of done

### Phase 1 done

- `builder/` exists with package code, tests, docs, and dashboard template.
- Metadata parser is tested.
- Workspace collector is tested.
- Renderer/app is tested.
- Dashboard runs locally.
- Browser verification completed.
- Dashboard is read-only.
- Missing metadata is reported as warnings, not hidden.

### Phase 2 done

- Guarded edit actions exist and are tested.
- Each action writes only canonical files.
- Each action has backup/validation/rollback behavior.
- UI shows results and verification evidence.
- Smoke test action works from the cockpit.
- All relevant tests pass.

## Final reporting requirements

When reporting progress, include:

- phase and step completed
- tests added
- tests run and exact result
- files changed
- verification performed
- blockers or risks
- next recommended step

If blocked, say exactly what is blocking progress and stop. Do not pretend a missing file, missing dependency, or failed test passed.
