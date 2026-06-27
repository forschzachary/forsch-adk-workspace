#!/usr/bin/env python3
"""Spawn a blank ADK agent from the graph — the write path.

Usage:
  python3 spawn_agent.py <agent_id> [--model MODEL] [--description DESC]

Creates:
  agents/<id>/          — package dir with pyproject.toml + agent.py
  web_agents/<id>/      — web wrapper
  agent_specs/agents.yaml entry (appended)

Then re-runs build_live_graph.py to show the new node in the graph.
"""

import json
import os
import sys
from pathlib import Path
from textwrap import dedent

from workspace_resolver import workspace_root, profile_home

WS = workspace_root() / "adk"

AGENT_PY_TEMPLATE = '''"""agent_{id}_agent — blank agent (spawned from Live Agent Graph).

State: blank → building (this file exists) → built (on bridge PYTHONPATH) → live (smoke passes).
"""

from __future__ import annotations

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = (
    os.environ.get("ADK_LITELLM_KEY_{id_upper}")
    or os.environ.get("LITELLM_HERMES_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or os.environ.get("LITELLM_API_KEY")
)
_LITELLM_MODEL = os.environ.get("FORSCH_ADK_MODEL", "openai/{model}")

{id}_model = LiteLlm(
    model=_LITELLM_MODEL,
    api_base=_LITELLM_BASE_URL,
    api_key=_LITELLM_API_KEY,
)

root_agent = Agent(
    name="{id}_agent",
    model={id}_model,
    description="{description}",
    instruction="""{instruction}""",
    tools=[],
)

agent = root_agent
'''

WEB_AGENT_PY = '''"""ADK Web wrapper for the packaged {id} agent."""

from forsch.agent_{id}.agent import root_agent

agent = root_agent
'''

WEB_AGENT_YAML = """agent_class: LlmAgent
name: {id}_agent
description: {description}
instruction: |
{instruction_indented}
model_code:
  name: forsch.agent_{id}.agent.{id}_model
tools:
"""

PYPROJECT_TOML = """[project]
name = "forsch-agent-{id}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.10"
dependencies = [
    "forsch-adk-components>=0.1.0",
    "google-adk>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/forsch"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
"""

README_MD = """# {id} agent

Forsch ADK agent — spawned from Live Agent Graph.

## Setup

```bash
uv pip install -e .
```

## Run

```bash
python -m forsch.agent_{id}.agent
```
"""

DIRECTORY_MD = """# {title} agent directory note

Purpose: independent ADK repo for the {id} agent.

Structure:

- `pyproject.toml` - package metadata for `forsch-agent-{id}`.
- `src/forsch/agent_{id}/agent.py` - ADK Agent definition.
- `tests/` - unit tests.
- `README.md` - setup/run notes.

Git ownership: this directory is the `forschzachary/forsch-agent-{id}` repo.
"""

AGENTS_YAML_ENTRY = """
  {id}:
    package: forsch.agent_{id}.agent
    attr: root_agent
    adk_name: {id}_agent
    description: {description}
    model_code: forsch.agent_{id}.agent.{id}_model
    web_entrypoint: web_agents/{id}
    discord_channels: []
    safety_level: read_only
    purpose: '{description}'
    instruction: |
{instruction_indented}
    tools: []
    smoke_prompts:
      - Introduce yourself and describe your role for Forsch.
    model: {model}
"""

DEFAULT_INSTRUCTION = """You are a blank agent spawned from the Live Agent Graph. You can receive messages and reply. Your capabilities will grow as tools and instructions are added."""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 spawn_agent.py <agent_id> [--model MODEL] [--description DESC]", file=sys.stderr)
        sys.exit(1)

    agent_id = sys.argv[1]
    model = "gpt-5.5"
    description = f"{agent_id} agent"

    # Parse optional flags
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif args[i] == "--description" and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        else:
            i += 1

    # Validate agent_id
    if not agent_id.isidentifier():
        print(f"Error: agent_id '{agent_id}' must be a valid Python identifier", file=sys.stderr)
        sys.exit(1)

    # Check it doesn't already exist
    agent_dir = WS / "agents" / agent_id
    if agent_dir.exists():
        print(f"Error: agent '{agent_id}' already exists at {agent_dir}", file=sys.stderr)
        sys.exit(1)

    web_dir = WS / "web_agents" / agent_id
    if web_dir.exists():
        print(f"Error: web_agent '{agent_id}' already exists at {web_dir}", file=sys.stderr)
        sys.exit(1)

    # Check agents.yaml doesn't already have this entry
    agents_yaml = WS / "agent_specs" / "agents.yaml"
    content = agents_yaml.read_text()
    if f"  {agent_id}:" in content:
        print(f"Error: agent '{agent_id}' already in agents.yaml", file=sys.stderr)
        sys.exit(1)

    title = agent_id.replace("_", " ").title()
    id_upper = agent_id.upper()
    instruction = DEFAULT_INSTRUCTION
    instruction_indented = "\n".join(f"      {line}" for line in instruction.splitlines())

    # ── Create agent package ──
    pkg_dir = agent_dir / "src" / "forsch" / f"agent_{agent_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (agent_dir / "pyproject.toml").write_text(
        PYPROJECT_TOML.format(id=agent_id, description=description)
    )
    (agent_dir / "README.md").write_text(README_MD.format(id=agent_id))
    (agent_dir / "DIRECTORY.md").write_text(
        DIRECTORY_MD.format(id=agent_id, title=title)
    )
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "agent.py").write_text(
        AGENT_PY_TEMPLATE.format(
            id=agent_id,
            id_upper=id_upper,
            model=model,
            description=description,
            instruction=instruction,
        )
    )

    # ── Create web wrapper ──
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "agent.py").write_text(WEB_AGENT_PY.format(id=agent_id))
    (web_dir / "root_agent.yaml").write_text(
        WEB_AGENT_YAML.format(
            id=agent_id,
            description=description,
            instruction_indented=instruction_indented,
        )
    )
    (web_dir / "DIRECTORY.md").write_text(
        f"# {title} web agent directory note\n\nWeb wrapper for the {agent_id} agent.\n"
    )

    # ── Append to agents.yaml ──
    entry = AGENTS_YAML_ENTRY.format(
        id=agent_id,
        description=description,
        instruction_indented=instruction_indented,
        model=model,
    )
    with open(agents_yaml, "a") as f:
        f.write(entry)

    # ── Create per-agent profile home ──
    # Single source of truth: workspace_resolver.profile_home() (reads
    # AGENT_PROFILES_ROOT, else HERMES_HOME/profiles). Do NOT hardcode the path —
    # a literal is namespace-fragile (host vs container) and was the lost-work bug.
    phome = profile_home(agent_id)
    if not phome.exists():
        phome.mkdir(parents=True, exist_ok=True)
        (phome / "home").mkdir(exist_ok=True)
        (phome / "memory").mkdir(exist_ok=True)
        (phome / "README").write_text(
            f"# {agent_id} profile home\n\n"
            f"Per-agent runtime home for the {agent_id} agent.\n"
            f"Created: {__import__('datetime').datetime.now().isoformat()}\n\n"
            f"## Structure\n\n"
            f"- `home/` — intended as the agent's $HOME (creds, config, state)\n"
            f"- `memory/` — persistent memory store\n\n"
            f"## Runtime binding\n\n"
            f"Resolve this path via `workspace_resolver.profile_home('{agent_id}')`.\n"
            f"NOTE: the Discord bridge currently runs agents in-process, so $HOME\n"
            f"is NOT auto-bound per agent — code must use the resolver explicitly.\n"
            f"Per-agent HOME isolation requires running agents as subprocesses.\n"
        )
        print(f"  profile:  {phome} (new)")
    else:
        print(f"  profile:  {phome} (exists — not clobbered)")

    # ── Record workspace on FF Agent in CRM ──
    try:
        import urllib.request
        crm_api_key = (Path(os.environ.get("HERMES_HOME", "/opt/data")) / "secrets" / "frappe-admin-api-key").read_text().strip()
        payload = json.dumps({
            "agent_id": agent_id,
            "workspace": str(profile_home),
        }).encode()
        req = urllib.request.Request(
            "https://crm.forschfrontiers.com/api/method/forsch_frontiers.sync.agent_graph.update_agent",
            data=payload,
            headers={
                "Authorization": f"token {crm_api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("message", {}).get("ok"):
                print(f"  recorded: workspace on FF Agent '{agent_id}'")
            else:
                print(f"  record:   CRM returned {result.get('message', {}).get('error', 'unknown')}", file=sys.stderr)
    except Exception as e:
        print(f"  record:   CRM unreachable — {e}", file=sys.stderr)

    print(f"✓ Spawned agent '{agent_id}'")
    print(f"  package:  {agent_dir}")
    print(f"  web:      {web_dir}")
    print(f"  manifest: {agents_yaml} (appended)")
    print(f"  model:    {model}")
    print(f"  state:    blank → building (agent.py exists, gates pending)")

    # ── Rebuild graph ──
    graph_builder = WS / "live-agent-graph" / "build_live_graph.py"
    factory_python = WS / "factory" / ".venv" / "bin" / "python"
    if graph_builder.exists():
        import subprocess
        py = str(factory_python) if factory_python.exists() else sys.executable
        result = subprocess.run(
            [py, str(graph_builder)],
            capture_output=True, text=True, cwd=str(WS),
        )
        if result.returncode == 0:
            out_path = WS / "live-agent-graph" / "agent-graph-v2.json"
            out_path.write_text(result.stdout)
            print(f"  graph:    regenerated ({out_path})")
        else:
            print(f"  graph:    rebuild failed — {result.stderr[:200]}", file=sys.stderr)


if __name__ == "__main__":
    main()
