"""The Forsch lane-specialists — background expert sub-agents the operator consults.

Repurposed from the Hubert factory-bot design (one expert per layer of the factory). Each
is an ADK agent wrapped in an AgentTool, so the operator can call it like a tool — one
seamless chat, experts working under the hood. They are READ-ONLY advisors: they investigate
and recommend; the operator acts with its own build/wire verbs.

Layers: Agent·Logic (agent config/model/evals), Tools·Data (the tool library),
Interfaces (channels/bridge), Router (cluster routing + contracts).
"""
from __future__ import annotations

from pathlib import Path

SPECIALISTS = [
    {
        "id": "agent_logic_specialist",
        "description": "Expert on agent config, model selection, evals, and ADK patterns — consult before designing or changing an agent.",
        "instruction": (
            "You are the Agent·Logic specialist for the Forsch ADK Factory. Your domain: agent "
            "configuration, model selection, evals, ADK patterns, tool wiring, and safety levels. "
            "When asked about an agent, read its spec from the manifest and report its model, tools, "
            "safety level, and purpose. When asked to design or change one, specify exactly: id, "
            "description, tools, model, safety level. When asked about models, reason about "
            "capability/cost/context for the use case. When asked about evals, describe the eval set "
            "and metrics. Be precise, cite file paths, show config when relevant. You are an advisor "
            "— you do not write files; you tell the operator exactly what to build."
        ),
    },
    {
        "id": "tools_data_specialist",
        "description": "Expert on the shared tool/component library — consult about which tools exist, what an agent needs, or how to build a new tool.",
        "instruction": (
            "You are the Tools·Data specialist for the Forsch ADK Factory. Your domain: the shared "
            "tool/component library (forsch.adk_components.tools) — what tools exist, what each does, "
            "testing conventions, and registration. When asked, list the relevant tools and recommend "
            "which an agent needs for a job. When asked to add a tool, describe how: a Python function "
            "in the components package plus tests, then wired into the agent's toolset. Be precise, "
            "cite tool names and file paths. You advise; the operator wires."
        ),
    },
    {
        "id": "interfaces_specialist",
        "description": "Expert on how agents reach the world — Discord channels, the bridge chat, ADK Web. Consult about channel/interface config.",
        "instruction": (
            "You are the Interfaces specialist for the Forsch ADK Factory. Your domain: how agents "
            "reach the outside world — Discord channels and webhooks, the native bridge (Chainlit "
            "chat), and ADK Web. When asked, report an agent's configured channels (discord_channels), "
            "explain channel/bridge/web setup, and recommend interface config. Be precise, cite config "
            "keys and paths. You advise; the operator configures."
        ),
    },
    {
        "id": "router_specialist",
        "description": "Expert on message routing + cluster membership — consult about how messages flow and how clusters are wired.",
        "instruction": (
            "You are the Router specialist for the Forsch ADK Factory. Your domain: message routing "
            "and flow between agents and clusters — cluster membership "
            "(packages/live-agent-graph/clusters/<name>/cluster.yaml), routing rules, and contract "
            "checks between layers. When asked, explain how a message flows, which cluster an agent "
            "belongs to, and how to wire routing. Be precise, cite cluster files and rules. You "
            "advise; the operator wires."
        ),
    },
]


def _read_tools(ws: Path) -> list:
    """A small read-only toolset the specialists share so they can investigate their layer."""

    def list_agents() -> list[str]:
        """List the agent ids in the manifest."""
        from forsch.adk_factory.loader import load_manifest

        return list(load_manifest(ws / "agent_specs" / "agents.yaml").agents)

    def get_agent_spec(agent_id: str) -> dict:
        """Read one agent's full spec (model, tools, safety, purpose, channels) from the manifest."""
        from forsch.adk_factory.loader import load_manifest

        manifest = load_manifest(ws / "agent_specs" / "agents.yaml")
        if agent_id not in manifest.agents:
            return {"error": f"no agent '{agent_id}'"}
        return manifest.agents[agent_id].model_dump()

    def list_tools() -> list[dict]:
        """List the Forsch tools available to agents (name, family, description)."""
        from forsch_palette import build_catalog

        return [{"name": t["name"], "family": t["family"], "description": t["desc"]} for t in build_catalog()]

    return [list_agents, get_agent_spec, list_tools]


def make_specialist_agenttools(ws: Path, model) -> list:
    """Build each lane-specialist as an ADK agent wrapped in an AgentTool for the operator."""
    from google.adk import Agent
    from google.adk.tools.agent_tool import AgentTool

    read = _read_tools(ws)
    tools = []
    for spec in SPECIALISTS:
        specialist = Agent(
            name=spec["id"],
            description=spec["description"],
            model=model,
            instruction=spec["instruction"],
            tools=list(read),
        )
        tools.append(AgentTool(specialist))
    return tools
