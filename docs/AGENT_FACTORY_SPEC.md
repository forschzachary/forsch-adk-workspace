# ADK Agent Factory Spec

## Goal

Turn new-agent creation from hand-written Python into a repeatable factory flow:

1. Zach describes the agent in plain language or edits one YAML spec.
2. A generator validates the spec against known components, tools, models, routes, and eval requirements.
3. The generator emits or updates the agent repo, ADK Web wrapper, editable YAML surface, tests, docs, and Discord bridge route.
4. ADK Web becomes the workshop for testing and editing behavior.
5. The Python runtime remains ADK-native, package-based, testable, and deployable.

This keeps vibe coding focused on the agent contract instead of letting a coding assistant scatter state across `agent.py`, bridge config, README files, and half-real ADK patterns. Friday energy, but with guardrails. Annoying. Necessary.

## Current State

The workspace already has the right bones:

```text
/opt/data/workspace/adk/
├── agents/              # independent repos: assistant, brand, build, ops, social
├── bridge/              # Discord -> ADK Runner bridge with channel routing
├── components/          # shared tools, clients, models, tests
├── docs/                # architecture and runbooks
└── web_agents/          # ADK Web entrypoints, currently ops only
```

Current strengths:

- Agents are independent packages, which is correct.
- Shared tools live in `forsch-adk-components`, which is correct.
- Authsome and LiteLLM are centralized, which is correct.
- Discord bridge already uses ADK `Runner` rather than pretending to be an agent runtime, which is correct.
- `web_agents/ops/root_agent.yaml` proves the editable ADK Web surface pattern.

Current weaknesses:

- Agent definitions are mostly hand-written and uneven. Ops has tools and a `root_agent`; others are minimal stubs with only `agent`.
- Model setup is duplicated in each agent file.
- The bridge route config is manually maintained and can drift from agent packages.
- Only ops has a Web UI wrapper and YAML surface.
- There is no canonical agent manifest, so vibe coding has no single file to edit.
- Tests check pieces, not the whole generated contract.

## Target Architecture

Add a factory layer:

```text
/opt/data/workspace/adk/
├── agent_specs/
│   ├── DIRECTORY.md
│   ├── agents.yaml                 # registry of all generated agents
│   └── schemas/
│       └── agent_spec.schema.json
├── factory/
│   ├── DIRECTORY.md
│   ├── pyproject.toml
│   ├── src/forsch/adk_factory/
│   │   ├── __init__.py
│   │   ├── cli.py                  # `adk-factory ...`
│   │   ├── loader.py               # load + normalize specs
│   │   ├── validator.py            # schema + workspace checks
│   │   ├── renderer.py             # Jinja templates -> files
│   │   ├── inventory.py            # discover tools/models/components
│   │   └── sync_bridge.py          # update bridge_config.yaml
│   ├── templates/
│   │   ├── agent.py.j2
│   │   ├── pyproject.toml.j2
│   │   ├── README.md.j2
│   │   ├── DIRECTORY.md.j2
│   │   ├── test_agent.py.j2
│   │   ├── web_agent.py.j2
│   │   └── root_agent.yaml.j2
│   └── tests/
└── generated/
    └── last_plan.json              # optional dry-run artifact
```

The key is `agent_specs/agents.yaml`. Everything else follows from it.

## Agent Spec Format

Example:

```yaml
version: 1
workspace: /opt/data/workspace/adk

defaults:
  model:
    provider: litellm
    name_env: FORSCH_ADK_MODEL
    default_name: openai/gpt-5.5
    base_url_env: LITELLM_BASE_URL
    default_base_url: http://127.0.0.1:4000/v1
    api_key_env_priority:
      - LITELLM_HERMES_KEY
      - LITELLM_API_KEY
      - LITELLM_MASTER_KEY
  python: ">=3.11"
  package_namespace: forsch
  component_dependency: forsch-adk-components

agents:
  ops:
    status: active
    repo_path: agents/ops
    package: forsch.agent_ops
    export_attr: root_agent
    adk_name: ops_agent
    display_name: Ops
    description: Infrastructure and operations lead for Forsch.
    instruction_file: instructions/ops.md
    tools:
      - forsch.adk_components.tools.get_crm_health_snapshot
      - forsch.adk_components.tools.list_recent_crm_leads
    discord:
      channels:
        - "#team-ops"
      dm_fallback: false
    web:
      enabled: true
      editable_yaml: true
    evals:
      smoke_prompts:
        - "check CRM health and summarize what matters"
        - "what should I inspect if the CRM is down?"
      required_tool_names:
        - get_crm_health_snapshot
    docs:
      owner: ops
      responsibility: deployment, monitoring, incident triage, business telemetry

  research:
    status: draft
    repo_path: agents/research
    package: forsch.agent_research
    export_attr: root_agent
    adk_name: research_agent
    display_name: Research
    description: Research and source-grounding lead for Forsch.
    instruction_inline: |
      You are the research lead for Forsch. Find primary sources, separate facts from interpretation, and cite where claims came from.
    tools:
      - forsch.adk_components.tools.web_search
    discord:
      channels:
        - "#team-research"
    web:
      enabled: true
      editable_yaml: true
    evals:
      smoke_prompts:
        - "find the latest ADK docs for custom tools"
```

Rules:

- `agents.<name>` is the stable ID used by bridge routing and sessions.
- `adk_name` is the ADK runtime agent name.
- `package` controls Python import path.
- `export_attr` should converge on `root_agent` for every agent.
- `instruction_file` is preferred over inline instructions once an agent grows.
- `tools` must reference importable Python callables or approved ADK built-ins after validation.
- `discord.channels` is source-of-truth for `bridge/bridge_config.yaml`.
- `web.enabled` is source-of-truth for `web_agents/<name>/`.

## Generator Commands

Installable CLI:

```bash
cd /opt/data/workspace/adk/factory
uv pip install --python ../components/.venv/bin/python -e .
```

Commands:

```bash
adk-factory validate agent_specs/agents.yaml
adk-factory plan agent_specs/agents.yaml
adk-factory generate agent_specs/agents.yaml --agent ops
adk-factory generate agent_specs/agents.yaml --all
adk-factory sync-bridge agent_specs/agents.yaml
adk-factory smoke agent_specs/agents.yaml --agent ops
```

Behavior:

- `validate`: schema checks, import checks, duplicate channel checks, package/path consistency, required files.
- `plan`: prints create/update/no-op per file without writing.
- `generate`: writes agent package, tests, README, DIRECTORY.md, web wrapper, YAML surface.
- `sync-bridge`: rewrites the generated `agents:` block in bridge config while preserving hand-owned settings.
- `smoke`: imports each generated agent and runs a minimal ADK Runner turn with fake or live mode depending on config.

## Generated Agent Runtime

Every generated `agent.py` should look structurally like this:

```python
"""Generated ADK agent definition for ops."""

from __future__ import annotations

from google.adk import Agent

from forsch.adk_components.models import make_litellm_model
from forsch.adk_components.tools import get_crm_health_snapshot, list_recent_crm_leads

ops_model = make_litellm_model()

root_agent = Agent(
    name="ops_agent",
    model=ops_model,
    description="Infrastructure and operations lead for Forsch.",
    instruction=(
        "You are the ops team lead for Forsch. Focus on infrastructure health, "
        "deployment state, incident triage, and read-only business telemetry."
    ),
    tools=[get_crm_health_snapshot, list_recent_crm_leads],
)

agent = root_agent
```

Important change: model construction moves into components:

```python
# components/src/forsch/adk_components/models/litellm.py
from __future__ import annotations

import os

from google.adk.models.lite_llm import LiteLlm


def make_litellm_model(
    model_env: str = "FORSCH_ADK_MODEL",
    default_model: str = "openai/gpt-5.5",
    base_url_env: str = "LITELLM_BASE_URL",
    default_base_url: str = "http://127.0.0.1:4000/v1",
) -> LiteLlm:
    """Build the shared ADK LiteLLM model from environment config."""
    api_key = (
        os.environ.get("LITELLM_HERMES_KEY")
        or os.environ.get("LITELLM_API_KEY")
        or os.environ.get("LITELLM_MASTER_KEY")
    )
    return LiteLlm(
        model=os.environ.get(model_env, default_model),
        api_base=os.environ.get(base_url_env, default_base_url),
        api_key=api_key,
    )
```

That removes duplicated LiteLLM glue from every agent.

## Generated ADK Web Surface

For each `web.enabled` agent:

```text
web_agents/<name>/
├── DIRECTORY.md
├── agent.py
└── root_agent.yaml
```

`agent.py`:

```python
"""ADK Web entrypoint for the ops agent."""

from forsch.agent_ops.agent import root_agent

agent = root_agent
```

`root_agent.yaml` mirrors the spec:

```yaml
agent_class: LlmAgent
name: ops_agent
description: Infrastructure and operations lead for Forsch.
instruction: |
  You are the ops team lead for Forsch...
model_code:
  name: forsch.agent_ops.agent.ops_model
tools:
  - name: forsch.adk_components.tools.get_crm_health_snapshot
  - name: forsch.adk_components.tools.list_recent_crm_leads
```

This gives two surfaces:

- Python package: runtime truth.
- YAML: editable ADK Web teaching and design surface.

The factory must prevent drift by regenerating both from the same spec.

## Bridge Sync

Current bridge config is hand-owned. Keep the runtime settings hand-owned, but generate the agent route block.

Target file split:

```text
bridge/
├── bridge_config.yaml          # human-owned runtime config
└── bridge_agents.generated.yaml # factory-owned routes
```

Or, if keeping one file, use markers:

```yaml
agents:
  # BEGIN GENERATED AGENT ROUTES
  ops:
    agent_package: forsch.agent_ops.agent
    agent_attr: root_agent
    channels:
      - "#team-ops"
  # END GENERATED AGENT ROUTES

  dm_fallback: assistant
```

Better: separate files. Less cute, fewer accidents.

Bridge loader change:

```python
base = _load_config("bridge_config.yaml")
routes = _load_config("bridge_agents.generated.yaml")
config = merge_bridge_config(base, routes)
```

The factory owns `bridge_agents.generated.yaml`; humans own token env, session DB, streaming, logging.

## Vibe Coding Flow

This is the workflow Zach should use:

1. Describe the agent in plain language.
2. Coding assistant edits `agent_specs/agents.yaml` and optional `agent_specs/instructions/<name>.md`.
3. Run `adk-factory validate`.
4. Run `adk-factory plan`.
5. Run `adk-factory generate --agent <name>`.
6. Run smoke tests.
7. Open ADK Web:

```bash
cd /opt/data/workspace/adk
components/.venv/bin/adk web --host 0.0.0.0 --port 8000 web_agents
```

8. Iterate in Web UI and fold useful changes back into the spec/instruction file.
9. Sync Discord bridge routes.
10. Restart bridge service.

The assistant is allowed to vibe on instructions and tool selection. It is not allowed to invent ADK framework code outside the templates unless explicitly asked.

## Validation Gates

`adk-factory validate` should fail if:

- An agent ID is not slug-safe.
- `repo_path` escapes the workspace.
- `package` does not match `repo_path` and generated package path.
- `tools` cannot be imported.
- Tool callables have missing type hints or missing docstrings.
- Two agents claim the same Discord channel.
- `dm_fallback` points at a missing agent.
- `export_attr` is not `root_agent` for newly generated agents.
- `web.editable_yaml` is true but no YAML can be generated.
- An existing file has local edits and would be overwritten without `--force`.

`adk-factory smoke` should check:

- `python -c "from forsch.agent_<name>.agent import root_agent"` succeeds.
- `root_agent.name` equals `adk_name`.
- ADK Web wrapper imports.
- Generated YAML parses.
- Bridge generated config parses.
- Optional live Runner turn works when credentials are present.

## What Needs To Change Now

### 1. Add the agent factory package

Create `/opt/data/workspace/adk/factory` as its own package. It can be one repo or part of the workspace repo. I would make it its own repo only if it gets reused outside this ADK workspace; otherwise keep it local for now.

Dependencies:

```toml
[project]
name = "forsch-adk-factory"
requires-python = ">=3.11"
dependencies = [
  "jinja2>=3.1",
  "pydantic>=2",
  "pyyaml>=6",
  "google-adk[extensions]>=2.3",
]

[project.scripts]
adk-factory = "forsch.adk_factory.cli:main"
```

### 2. Move shared model setup into components

Right now every agent repeats LiteLLM env parsing. Move that into `forsch.adk_components.models.make_litellm_model`.

Then generated agents use:

```python
from forsch.adk_components.models import make_litellm_model
```

### 3. Standardize exports

Every agent should export both:

```python
root_agent = Agent(...)
agent = root_agent
```

Current build/brand/social/assistant mostly export only `agent`. Bridge config should converge on `root_agent` for all of them.

### 4. Create specs for the five existing agents

Backfill `agent_specs/agents.yaml` from the current workspace:

- assistant
- brand
- build
- ops
- social

Ops gets real tools. The others can start as minimal specs, but should still get generated web wrappers and YAML.

### 5. Generate Web UI wrappers for every agent

Current Web UI coverage is ops only. Add:

```text
web_agents/assistant/
web_agents/brand/
web_agents/build/
web_agents/social/
```

Each gets `agent.py`, `root_agent.yaml`, and `DIRECTORY.md`.

### 6. Split bridge runtime config from generated route config

Change `bridge_config.yaml` so humans own bridge runtime settings and the factory owns channel routes. This is where drift will otherwise breed. It always does.

### 7. Add tests for generated contracts

Each generated agent should get a test like:

```python
def test_root_agent_contract():
    from forsch.agent_ops.agent import root_agent

    assert root_agent.name == "ops_agent"
    assert root_agent.description
```

Factory tests should snapshot generated files for a sample spec.

### 8. Add a docs runbook

Add `docs/AGENT_FACTORY_RUNBOOK.md` with the exact flow:

```bash
adk-factory validate agent_specs/agents.yaml
adk-factory plan agent_specs/agents.yaml
adk-factory generate agent_specs/agents.yaml --agent <name>
adk-factory smoke agent_specs/agents.yaml --agent <name>
components/.venv/bin/adk web web_agents
```

## Implementation Order

### Phase 1: Stabilize the source of truth

- Add `agent_specs/agents.yaml`.
- Add shared `make_litellm_model` in components.
- Normalize all existing agents to `root_agent` + `agent`.
- Add web wrappers/YAML for all five existing agents.

### Phase 2: Build the factory CLI

- Implement loader and Pydantic spec models.
- Implement validator.
- Implement renderer with Jinja templates.
- Implement dry-run plan output.
- Add tests using a temporary workspace.

### Phase 3: Bridge generation

- Add generated route config.
- Update bridge loader to merge runtime config and generated routes.
- Generate routes from `agents.yaml`.
- Add duplicate channel detection.

### Phase 4: Vibe coding guardrails

- Add `agent_specs/instructions/*.md` files.
- Add a `docs/VIBE_CODING_AGENTS.md` guide.
- Add an assistant prompt template:

```text
You are editing a Forsch ADK agent spec. Only modify agent_specs/agents.yaml and instruction files unless asked. Do not invent ADK APIs. After edits, run adk-factory validate, plan, generate, and smoke.
```

### Phase 5: Real ADK Web loop

- Launch ADK Web against `web_agents`.
- Test each generated agent manually.
- Fold good UI edits back into the spec.
- Decide whether YAML or Python remains the stronger source for each graph type.

## Opinionated Calls

- Specs first. Python second. If Python is the source of truth, vibe coding will sprawl.
- Keep agents independent. Do not introduce agent-to-agent imports just because generation makes it easy.
- Generate boring files. Hand-write only tools, instructions, and special workflows.
- Treat ADK Web as the workshop, not production.
- Keep Discord dumb. The bridge routes and streams. It should not know agent logic.
- Make Authsome and LiteLLM invisible to agent authors through shared components.

## Open Questions

1. Should the factory create GitHub repos for new agents automatically, or only scaffold local packages first?
2. Should generated agents default to `root_agent` only, or keep `agent = root_agent` forever for ADK Web compatibility?
3. Do we want one `agents.yaml` registry, or one file per agent under `agent_specs/agents/<name>.yaml`? I prefer one registry until it gets annoying.
4. Should Web UI edits be treated as disposable experiments, or should we build an importer that converts edited YAML back into specs?
5. Should channel names or Discord IDs be canonical? Names are readable; IDs survive renames. Production wants IDs.

## Immediate Next Move

Build Phase 1. It gives the biggest payoff without committing to a complicated factory too early:

- `agent_specs/agents.yaml`
- shared LiteLLM model helper
- normalized `root_agent` exports
- generated-ish web wrappers for all existing agents
- bridge route split plan

Then implement the CLI after the shape proves itself in ADK Web.
