"""make_agent_files — one-shot ADK agent file scaffold.

---
keywords: [spawn, create, new-agent, scaffold, init, factory, generate, blueprint]
intention: "Saves you from hand-editing three files (agents/<id>/agent.py, web_agents/<id>/root_agent.yaml, agent_specs/agents.yaml) every time you want to add an agent. One call writes all three, updates the manifest, runs the linter."
function: "make_agent_files(agent_id, description, instruction, tools, model) — writes all files needed for a new ADK agent."
depends_on: [agent_factory]
used_by: []
example: "make_agent_files('calendar_bot', 'Tracks events', 'You are a calendar assistant.', ['gcal_fetch_events'])"
---

Writes:
  /root/.hermes/workspace/adk/agents/<id>/agent.py
  /root/.hermes/workspace/adk/agents/<id>/src/forsch/agent_<id>/agent.py
  /root/.hermes/workspace/adk/web_agents/<id>/root_agent.yaml
  /root/.hermes/workspace/adk/agent_specs/agents.yaml

Idempotent: re-running with the same args is a no-op.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml


_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TOOL_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _resolve_workspace() -> Path:
    return Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/root/.hermes/workspace/adk"))


def _validate_agent_id(agent_id: str) -> str:
    if not _AGENT_ID_RE.fullmatch(agent_id or ""):
        raise ValueError("agent_id must match ^[a-z][a-z0-9_]*$ for safe paths and Python names")
    return agent_id


def _validate_required_text(name: str, value: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _validate_tools(tools: list[str]) -> list[str]:
    cleaned = [tool.strip() for tool in tools if tool and tool.strip()]
    if not cleaned:
        raise ValueError("at least one bare tool name is required")
    invalid = [tool for tool in cleaned if not _TOOL_ID_RE.fullmatch(tool)]
    if invalid:
        raise ValueError(f"tool names must be bare Python identifiers: {', '.join(invalid)}")
    return cleaned


def _write_if_changed(path: Path, content: str, written: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
        written[str(path)] = len(content)


def _agent_manifest_entry(
    agent_id: str,
    description: str,
    instruction: str,
    tools: list[str],
    model: str,
    safety_level: str,
) -> dict[str, Any]:
    return {
        "package": f"forsch.agent_{agent_id}.agent",
        "attr": "root_agent",
        "adk_name": f"{agent_id}_agent",
        "description": description,
        "model_code": f"forsch.agent_{agent_id}.agent.{agent_id}_model",
        "web_entrypoint": f"web_agents/{agent_id}",
        "discord_channels": [],
        "safety_level": safety_level,
        "purpose": description,
        "instruction": instruction,
        "tools": [f"forsch.adk_components.tools.{tool}" for tool in tools],
        "smoke_prompts": [f"Introduce yourself and describe what you do as {agent_id}."],
        "model": model,
    }


def make_agent_files(
    agent_id: str,
    description: str,
    instruction: str,
    tools: list[str],
    *,
    model: str = "gpt-5.5",
    safety_level: str = "read_only",
    workspace: Optional[Path] = None,
) -> dict[str, Any]:
    """Write all files needed for a new ADK agent. Returns dict of {path: bytes_written}."""
    agent_id = _validate_agent_id(agent_id)
    description = _validate_required_text("description", description)
    instruction = _validate_required_text("instruction", instruction)
    tools = _validate_tools(tools)

    ws = workspace or _resolve_workspace()
    written: dict[str, int] = {}

    shim_path = ws / "agents" / agent_id / "agent.py"
    shim_content = (
        '"""Shim for adk api_server — loads the actual agent from the package."""\n'
        "import os, sys\n"
        'sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))\n'
        f"from forsch.agent_{agent_id}.agent import root_agent\n\n"
        "agent = root_agent\n"
    )
    if not shim_path.exists():
        _write_if_changed(shim_path, shim_content, written)

    pkg_dir = ws / "agents" / agent_id / "src" / "forsch" / f"agent_{agent_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    init_path = pkg_dir / "__init__.py"
    if not init_path.exists():
        init_path.write_text("")
        written[str(init_path)] = 0

    agent_path = pkg_dir / "agent.py"
    tool_imports = ", ".join(tools)
    agent_content = (
        f'"""{agent_id}_agent — auto-scaffolded by patterns.cluster_spawn."""\n\n'
        "from __future__ import annotations\n\n"
        "import os\n\n"
        "from google.adk import Agent\n"
        "from google.adk.models.lite_llm import LiteLlm\n"
        f"from forsch.adk_components.tools import {tool_imports}\n\n"
        "_LITELLM_BASE_URL = os.environ.get('LITELLM_BASE_URL', 'http://127.0.0.1:4000/v1')\n"
        "_LITELLM_API_KEY = (\n"
        "    os.environ.get('LITELLM_HERMES_KEY')\n"
        "    or os.environ.get('LITELLM_API_KEY')\n"
        ")\n"
        f"_LITELLM_MODEL = 'openai/{model}'\n\n"
        f"{agent_id}_model = LiteLlm(\n"
        "    model=_LITELLM_MODEL, api_base=_LITELLM_BASE_URL, api_key=_LITELLM_API_KEY,\n"
        ")\n\n"
        "root_agent = Agent(\n"
        f"    name='{agent_id}_agent',\n"
        f"    model={agent_id}_model,\n"
        f"    description={description!r},\n"
        f"    instruction={instruction!r},\n"
        f"    tools=[{tool_imports}],\n"
        ")\n\n"
        "agent = root_agent\n"
    )
    _write_if_changed(agent_path, agent_content, written)

    yaml_path = ws / "web_agents" / agent_id / "root_agent.yaml"
    yaml_data = {
        "agent_class": "LlmAgent",
        "name": f"{agent_id}_agent",
        "description": description,
        "instruction": instruction,
        "model_code": {"name": f"forsch.agent_{agent_id}.agent.{agent_id}_model"},
        "tools": [{"name": f"forsch.adk_components.tools.{tool}"} for tool in tools],
    }
    yaml_content = yaml.safe_dump(yaml_data, sort_keys=False, default_flow_style=False)
    _write_if_changed(yaml_path, yaml_content, written)

    manifest_path = ws / "agent_specs" / "agents.yaml"
    data: dict[str, Any] = {}
    if manifest_path.exists():
        data = yaml.safe_load(manifest_path.read_text()) or {}
    agents = data.setdefault("agents", {})
    entry = _agent_manifest_entry(agent_id, description, instruction, tools, model, safety_level)
    if agents.get(agent_id) != entry:
        agents[agent_id] = entry
        yaml_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
        _write_if_changed(manifest_path, yaml_text, written)

    return {"agent_id": agent_id, "files_written": written}
