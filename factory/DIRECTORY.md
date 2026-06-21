# factory/ — ADK Agent Factory

Deterministic, LLM-free generator. Input: the canonical manifest
`agent_specs/agents.yaml` (the single writable source of truth). Output:
generated ADK artifacts (Slice 1: the `root_agent.yaml` editable surface;
later slices: package, test stub, bridge route).

## Modules (`src/forsch/adk_factory/`)

| Module | Role |
|---|---|
| `models.py` | `AgentSpec` (one resolved manifest entry), `Manifest` (the whole file). |
| `loader.py` | `load_manifest(path) -> Manifest`; merges the top-level `defaults` block into each agent. |
| `renderer.py` | `render_agent(spec) -> {relpath: content}`; Jinja templates. Golden-file-pinned to the live `web_agents/stability/root_agent.yaml` (byte-identical). |
| `validator.py` | `classify_tools(spec, known) -> (known, new)`; an unknown tool is the mint-new-ability signal, not an error. |
| `cli.py` | `plan(manifest_path, agent_id)` — dry-run diff payload, **writes nothing** (the review-gate payload). `apply` deferred to Slice 1b. |

## Run

```bash
export PATH=/root/.local/bin:$PATH
cd factory && uv venv && uv pip install -e ".[dev]"
./.venv/bin/python -m pytest -q   # 4 passed
```

## Design

See `docs/superpowers/specs/2026-06-20-adk-agent-factory-canvas-design.md`
(authored in the Hubert repo) and `docs/AGENT_FACTORY_SPEC.md`.

Slice 1 scope: loader + validator + renderer (`root_agent.yaml`) + `plan`.
Deferred to Slice 1b: `apply` (backup→atomic-write→re-validate→rollback),
`sync_bridge`, package/test rendering, and the 5-agent drift retirement.
