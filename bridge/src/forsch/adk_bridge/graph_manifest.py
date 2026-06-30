"""Derive the live-graph nodes/edges for the NATIVE bots from the bridge's own definitions.

This is the parity engine: the map becomes a function of the code. ``build_live_graph`` calls
``native_graph()`` instead of reading a hand-typed copy, so deleting a bot or a tool from the bridge
removes it from the map on the next render. The shape is STRUCTURAL (the agents/tools/channels/
delegation the code defines), independent of which tokens happen to be set where the graph renders;
runtime liveness is a separate overlay (serve.py). A channel appears only if it's a real, DISTINCT
binding — a placeholder that resolves to another channel's id (e.g. #screening-tv → the team-social
id) is skipped, so the map can never show a channel that doesn't exist.

Light imports only (NATIVE_BOTS + os) — no Discord/ADK runtime needed.
"""
from __future__ import annotations

import os

from forsch.adk_bridge.native_bots import NATIVE_BOTS

_GATES = {"L0": True, "L1": True, "L2": True, "L3": True}


def _persona_artifact(module: str) -> str:
    return "bridge/src/forsch/adk_bridge/%s.py" % module


def _tool_artifact(fn) -> str:
    mod = getattr(fn, "__module__", "") or ""
    path = "bridge/src/" + mod.replace(".", "/") + ".py"
    return "%s (def %s)" % (path, getattr(fn, "__name__", "?"))


def _intake_node(node_id: str, name: str) -> dict:
    return {
        "id": node_id, "name": name, "kind": "intake", "type": "intake", "native": True,
        "artifact": "Discord (%s)" % name, "gates": dict(_GATES), "state": "built", "reachable": False,
        "contract": {"accepts": ["external_message"], "emits": ["routed_message"]}, "role": "plain",
    }


def native_graph() -> dict:
    """Return {"nodes": [...], "links": [...]} for the native bots, derived from NATIVE_BOTS + env."""
    nodes: list = []
    links: list = []
    tool_seen: dict = {}     # tool id -> node (dedupe shared tools, e.g. read_knowledge)
    chan_seen: dict = {}     # resolved channel key -> node id (dedupe channels by their real id)

    for bot in NATIVE_BOTS:
        aid = "agent:" + bot.agent_id

        nodes.append({
            "id": aid, "name": bot.name, "kind": "agent", "type": "agent", "native": True,
            "shared": False, "artifact": _persona_artifact(bot.persona_module), "model": "gpt-5.5",
            "optional": bot.optional, "gates": dict(_GATES), "state": "built", "reachable": False,
            "contract": {"accepts": ["instruction"], "emits": ["response", "tool_call"]}, "role": "plain",
        })

        tools = bot.toolset()
        bid = "bundle:%s:%s" % (bot.agent_id, bot.bundle_key)
        nodes.append({
            "id": bid, "name": bot.bundle_name, "kind": "bundle", "type": "bundle", "native": True,
            "shared": False, "bundle_key": bot.bundle_key, "for_agent": bot.agent_id,
            "description": bot.bundle_desc, "tools_count": len(tools), "inactive_tools": [],
            "artifact": _persona_artifact(bot.persona_module), "optional": bot.optional,
            "gates": dict(_GATES), "state": "built", "reachable": False,
            "contract": {"accepts": ["agent_message"], "emits": ["tool_call"]}, "role": "plain",
        })
        links.append({"source": aid, "target": bid, "kind": "uses-bundle"})

        for fn in tools:
            tname = getattr(fn, "__name__", "?")
            tid = "tool:" + tname
            if tid in tool_seen:
                tool_seen[tid]["shared"] = True   # used by more than one bundle
            else:
                node = {
                    "id": tid, "name": tname, "kind": "tool", "type": "tool", "native": True,
                    "shared": False, "family": "screening", "artifact": _tool_artifact(fn),
                    "gates": dict(_GATES), "state": "built", "reachable": False,
                    "contract": {"accepts": ["agent_message"], "emits": ["result"]}, "role": "plain",
                }
                nodes.append(node)
                tool_seen[tid] = node
            links.append({"source": bid, "target": tid, "kind": "contains"})

        # Channel + listens — only a REAL, DISTINCT channel (see module docstring).
        if bot.dm:
            node_id = "chan:DM"
            if "DM" not in chan_seen:
                chan_seen["DM"] = node_id
                nodes.append(_intake_node(node_id, "DM (friend)"))
            links.append({"source": aid, "target": node_id, "kind": "listens"})
        elif bot.channel_name:
            cid = os.environ.get(bot.channel_env, bot.channel_default) if bot.channel_env else bot.channel_default
            my_node_id = "chan:" + bot.channel_name
            claimed = chan_seen.get(cid)
            if claimed is None:
                chan_seen[cid] = my_node_id
                nodes.append(_intake_node(my_node_id, bot.channel_name))
                links.append({"source": aid, "target": my_node_id, "kind": "listens"})
            elif claimed == my_node_id:
                links.append({"source": aid, "target": my_node_id, "kind": "listens"})
            # else: placeholder collision — this bot's channel id is really another channel; skip it.

    # Delegation — structural: each bot flagged ``delegates`` consults every A2A specialist.
    specialists = [b for b in NATIVE_BOTS if b.a2a_specialist]
    for d in NATIVE_BOTS:
        if not d.delegates:
            continue
        for target in specialists:
            if target.agent_id != d.agent_id:
                links.append({
                    "source": "agent:" + d.agent_id, "target": "agent:" + target.agent_id, "kind": "delegates",
                })

    return {"nodes": nodes, "links": links}
