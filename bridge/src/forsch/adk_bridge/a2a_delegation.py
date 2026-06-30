"""Expose ScreeningRoom specialist agents over A2A so Huberto can delegate to them.

Each specialist (ops, curator) is the SAME agent definition that may also run a Discord bot; here
it gets an A2A front door (``to_a2a`` → AgentCard) so Huberto consults it as a *tool* and relays the
answer in his own voice. Loopback today (the A2A servers run in-process alongside the bots), but the
A2A boundary + AgentCard mean a specialist can later move to its own process / host with no change to
Huberto's side — and each ``huberto -> <specialist>`` edge in the live graph is a real wire.

Add a new specialist by adding one entry to ``SPECIALISTS`` — that wires both its A2A server
(``serve_specialists``) and Huberto's delegate tool (``delegate_tools``).

A2A support in ADK is flagged experimental (subject to breaking changes); pinned via the
``google-adk[a2a]`` extra.
"""
from __future__ import annotations

import os

A2A_HOST = os.environ.get("A2A_HOST", "127.0.0.1")

# name -> port, agent factory (module, attr), and the friend-facing description Huberto sees on the
# delegate tool (it decides when to consult each specialist from this text).
SPECIALISTS = {
    "screening_ops": {
        "port": int(os.environ.get("OPS_A2A_PORT", "8810")),
        "factory": ("forsch.adk_bridge.ops_persona", "make_ops_agent"),
        "description": (
            "the screening room's ops / admin lead. consult it for operational + admin questions "
            "you can't resolve with your own tools: why a friend can't access their account, the "
            "root cause of a stuck download, media-pipeline / indexer / storage health. it returns "
            "a terse factual answer — relay it in your own voice, never mention asking it."
        ),
    },
    "screening_curator": {
        "port": int(os.environ.get("CURATOR_A2A_PORT", "8811")),
        "factory": ("forsch.adk_bridge.curator_persona", "make_curator_agent"),
        "description": (
            "the SR-1 channel's curator. consult it for DEEP programming a friend asks for that's "
            "beyond your own basic scheduling: rearranging / reprogramming the SR-1 lineup, a themed "
            "block or marathon, building a playlist, adding bumps or events. it returns what it set "
            "up or proposes — relay it in your own voice, never mention asking it."
        ),
    },
}


def _make_agent(name):
    import importlib

    mod, attr = SPECIALISTS[name]["factory"]
    return getattr(importlib.import_module(mod), attr)()


def card_url(name):
    """The well-known AgentCard URL for a specialist (to_a2a serves it at the root path)."""
    port = SPECIALISTS[name]["port"]
    return os.environ.get(
        f"{name.upper()}_A2A_CARD_URL",
        f"http://{A2A_HOST}:{port}/.well-known/agent-card.json",
    )


def build_specialist_app(name):
    """Wrap a specialist agent as an A2A ASGI app (Starlette) with an auto-generated AgentCard."""
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    return to_a2a(_make_agent(name), port=SPECIALISTS[name]["port"])


async def serve_specialists(names=None):
    """Run the A2A server(s) for the given specialists (default: all). Call as an asyncio task
    alongside the Discord bots."""
    import asyncio

    import uvicorn

    coros = []
    for name in (names or list(SPECIALISTS)):
        app = build_specialist_app(name)
        cfg = uvicorn.Config(app, host=A2A_HOST, port=SPECIALISTS[name]["port"], log_level="warning")
        coros.append(uvicorn.Server(cfg).serve())
    await asyncio.gather(*coros)


def delegate_tools(names=None):
    """AgentTools wrapping a RemoteA2aAgent per specialist.

    Wrapped as *tools* (not sub_agents) on purpose: Huberto consults a specialist, gets a factual
    answer back, and relays it in his own voice — rather than transferring the conversation and
    breaking the single friend-facing voice.
    """
    from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
    from google.adk.tools.agent_tool import AgentTool

    tools = []
    for name in (names or list(SPECIALISTS)):
        remote = RemoteA2aAgent(
            name=name,
            description=SPECIALISTS[name]["description"],
            agent_card=card_url(name),
            use_legacy=False,
        )
        tools.append(AgentTool(agent=remote))
    return tools
