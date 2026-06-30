"""Expose the screening-room ops lead over A2A, and give Huberto a tool to consult it.

Ops has two front doors on the SAME agent definition: its Discord presence (#team-social, wired in
``discord_main``) and an A2A server (here) so Huberto can delegate admin / pipeline work to the ops
lead instead of faking it through a shared module. It's loopback today (the A2A server runs in the
same process as the bots), but the A2A boundary + AgentCard mean Ops can later move to its own
process / host with no change to Huberto's side — and the ``huberto -> screening_ops`` edge in the
live graph is now a real wire, not a narrative.

A2A support in ADK is flagged experimental (subject to breaking changes); pinned via the
``google-adk[a2a]`` extra.
"""
from __future__ import annotations

import os

OPS_A2A_HOST = os.environ.get("OPS_A2A_HOST", "127.0.0.1")
OPS_A2A_PORT = int(os.environ.get("OPS_A2A_PORT", "8810"))
# to_a2a serves the AgentCard at the root well-known path; overridable if Ops ever moves off-box.
OPS_A2A_CARD_URL = os.environ.get(
    "OPS_A2A_CARD_URL",
    f"http://{OPS_A2A_HOST}:{OPS_A2A_PORT}/.well-known/agent-card.json",
)


def build_ops_a2a_app(port: int = OPS_A2A_PORT):
    """Wrap the ops lead as an A2A ASGI app (Starlette) with an auto-generated AgentCard."""
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    from forsch.adk_bridge.ops_persona import make_ops_agent

    return to_a2a(make_ops_agent(), port=port)


async def serve_ops_a2a(host: str = OPS_A2A_HOST, port: int = OPS_A2A_PORT) -> None:
    """Run the ops A2A server. Call as an asyncio task alongside the Discord bots."""
    import uvicorn

    app = build_ops_a2a_app(port)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    await uvicorn.Server(config).serve()


def ops_delegate_tool():
    """AgentTool wrapping a RemoteA2aAgent for the ops lead.

    Wrapped as a *tool* (not a sub_agent) on purpose: Huberto consults Ops, gets a factual answer
    back, and relays it in his own voice — rather than transferring the conversation to Ops and
    breaking the single friend-facing voice.
    """
    from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
    from google.adk.tools.agent_tool import AgentTool

    ops = RemoteA2aAgent(
        name="screening_ops",
        description=(
            "the screening room's ops / admin lead. consult it for operational + admin questions "
            "you can't resolve with your own tools: why a friend can't access their account, the "
            "root cause of a stuck download, media-pipeline / indexer / storage health. it returns "
            "a terse factual answer — relay it in your own voice, never mention asking it."
        ),
        agent_card=OPS_A2A_CARD_URL,
        use_legacy=False,
    )
    return AgentTool(agent=ops)
