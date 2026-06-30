"""Build a new agent's manifest block from defaults. Pure — unit-testable."""
from __future__ import annotations


def new_agent_block(agent_id: str, description: str = "", instruction: str = "",
                    safety_level: str = "read_only") -> dict:
    """A minimal, factory-renderable agent block for ``agent_specs/agents.yaml``.

    The package/attr/adk_name/model_code follow the factory's naming so a plain
    ``forsch build <id>`` renders a working agent.py + root_agent.yaml.
    """
    pkg = agent_id.replace("-", "_")
    desc = description or f"{agent_id} agent."
    return {
        "package": f"forsch.agent_{pkg}.agent",
        "attr": "root_agent",
        "adk_name": f"{pkg}_agent",
        "description": desc,
        "model_code": f"forsch.agent_{pkg}.agent.{pkg}_model",
        "web_entrypoint": f"web_agents/{agent_id}",
        "discord_channels": [],
        "safety_level": safety_level,
        "purpose": desc,
        "instruction": instruction or f"You are {agent_id}, a Forsch agent. Be warm, concise, and practical.",
        "tools": [],
    }
