"""Agent·Logic specialist tools — agent config, model info, ADK reference."""

from __future__ import annotations

import os
from pathlib import Path

import yaml


_WORKSPACE = Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/root/.hermes/workspace/adk"))
_AGENTS_YAML = _WORKSPACE / "agent_specs" / "agents.yaml"
_AGENTS_DIR = _WORKSPACE / "agents"


def list_agents() -> dict:
    """List all agents in the ADK workspace."""
    agents = []
    if _AGENTS_DIR.exists():
        for entry in sorted(_AGENTS_DIR.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                agents.append(entry.name)
    return {"status": "ok", "agents": agents, "count": len(agents)}


def get_agent_config(agent_id: str) -> dict:
    """Read an agent's config from agents.yaml."""
    if not _AGENTS_YAML.exists():
        return {"status": "error", "message": "agents.yaml not found"}
    with open(_AGENTS_YAML, "r") as f:
        data = yaml.safe_load(f) or {}
    agents = data.get("agents", {})
    if agent_id not in agents:
        return {"status": "error", "message": f"agent '{agent_id}' not found"}
    return {"status": "ok", "agent_id": agent_id, "config": agents[agent_id]}


def update_agent_config(agent_id: str, field: str, value: str) -> dict:
    """Update a single field in an agent's agents.yaml entry."""
    if not _AGENTS_YAML.exists():
        return {"status": "error", "message": "agents.yaml not found"}
    with open(_AGENTS_YAML, "r") as f:
        data = yaml.safe_load(f) or {}
    agents = data.get("agents", {})
    if agent_id not in agents:
        return {"status": "error", "message": f"agent '{agent_id}' not found"}
    old_value = agents[agent_id].get(field)
    agents[agent_id][field] = value
    with open(_AGENTS_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return {
        "status": "ok",
        "agent_id": agent_id,
        "field": field,
        "old_value": old_value,
        "new_value": value,
    }


def get_model_info(model: str) -> dict:
    """Query the LiteLLM proxy for available models."""
    import urllib.request
    import json

    base_url = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    api_key = (
        os.environ.get("LITELLM_MASTER_KEY")
        or os.environ.get("LITELLM_API_KEY")
        or ""
    )
    try:
        req = urllib.request.Request(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            models = json.loads(resp.read())
        available = [m.get("id", "") for m in models.get("data", [])]
        match = [m for m in available if model.lower() in m.lower()]
        return {"status": "ok", "query": model, "matches": match, "total_models": len(available)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_adk_reference(topic: str) -> dict:
    """Return ADK reference info for a given topic."""
    references = {
        "agent": {
            "summary": "ADK Agent is the core building block. Define name, model, instruction, tools.",
            "key_fields": ["name", "model", "instruction", "tools", "description"],
            "example": 'Agent(name="my_agent", model=LiteLlm(...), instruction="...", tools=[...])',
        },
        "lite_llm": {
            "summary": "LiteLlm routes any model through a LiteLLM-compatible proxy.",
            "key_fields": ["model", "api_base", "api_key"],
            "example": 'LiteLlm(model="openai/gpt-5.5", api_base="http://127.0.0.1:4000/v1", api_key=key)',
        },
        "tools": {
            "summary": "Tools are plain Python functions with type hints and docstrings. ADK infers the schema.",
            "key_fields": ["function name", "docstring", "type hints", "return dict"],
            "example": 'def my_tool(param: str) -> dict:\n    """Do something."""\n    return {"status": "ok"}',
        },
        "evals": {
            "summary": "Use pytest + google-adk test harness. smoke_prompts in agents.yaml drive smoke tests.",
            "key_fields": ["smoke_prompts", "pytest", "evalset"],
            "example": "Add smoke_prompts to agents.yaml; run via bridge eval command.",
        },
        "safety": {
            "summary": "Safety levels: read_only (default), local_write (can edit files/run commands), full_access.",
            "key_fields": ["safety_level in agents.yaml"],
            "example": "safety_level: read_only",
        },
        "model_routing": {
            "summary": "Models route through LiteLLM proxy at 127.0.0.1:4000. Prefix with provider: openai/gpt-5.5, google/gemini-2.5-pro.",
            "key_fields": ["LITELLM_BASE_URL", "model prefix"],
            "example": 'LiteLlm(model="openai/gpt-5.5", api_base="http://127.0.0.1:4000/v1")',
        },
    }
    topic_lower = topic.lower().replace(" ", "_")
    if topic_lower in references:
        return {"status": "ok", "topic": topic, "reference": references[topic_lower]}
    return {
        "status": "ok",
        "topic": topic,
        "reference": {"summary": f"No specific reference for '{topic}'. Available: {list(references.keys())}"},
    }
