#!/usr/bin/env python3
"""Emit the agent dependency graph from agent_specs/agents.yaml (force-graph v2).

Same JSON shape as the canonical doc-graph (nodes:[{id,name,kind,...}], links:[{source,target,kind}])
so it feeds the same force-graph renderer. Typed nodes: agent / model / group / tool / channel.
Edges: uses (agent->tool), pinned-model / default-model (agent->model), wears (agent->group),
listens (agent->#channel), fallback (model->model, from the LiteLLM config).

Credentials (agent->authsome connection) are the next layer — they are NOT derivable from
agents.yaml (grep of imports is brittle), so they need an explicit `credentials:` declaration.
"""
import json
import sys
from pathlib import Path

import yaml

WS = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/.hermes/workspace/adk")
agents = (yaml.safe_load((WS / "agent_specs" / "agents.yaml").read_text()) or {}).get("agents", {})

# unpinned agents run on the global FORSCH_ADK_MODEL default (the native bridge container env).
DEFAULT_MODEL = "nvidia-deepseek-v4-flash"
# model -> fallback chain, mirroring litellm/config.yaml `fallbacks:` (cross-provider catches).
FALLBACKS = {
    "glm-5.2": ["gpt-5.5", "gemini-3-pro-preview"],
    "glm-5.1": ["gpt-5.5", "gemini-3-pro-preview"],
    "nvidia-deepseek-v4-flash": ["gpt-5.5", "gemini-3-pro-preview"],
}

nodes: dict = {}
links: list = []


def node(nid, name, kind, **kw):
    nodes.setdefault(nid, {"id": nid, "name": name, "kind": kind, **kw})


def link(s, t, kind):
    links.append({"source": s, "target": t, "kind": kind})


for aid, a in agents.items():
    node(f"agent:{aid}", aid, "agent")
    model = a.get("model") or DEFAULT_MODEL
    node(f"model:{model}", model, "model")
    link(f"agent:{aid}", f"model:{model}", "pinned-model" if a.get("model") else "default-model")
    if (g := a.get("group")):
        node(f"group:{g}", g, "group")
        link(f"agent:{aid}", f"group:{g}", "wears")
    for t in a.get("tools", []) or []:
        leaf = t.rsplit(".", 1)[-1]
        node(f"tool:{leaf}", leaf, "tool")
        link(f"agent:{aid}", f"tool:{leaf}", "uses")
    for c in a.get("discord_channels", []) or []:
        node(f"chan:{c}", c, "channel")
        link(f"agent:{aid}", f"chan:{c}", "listens")

for m, chain in FALLBACKS.items():
    if f"model:{m}" in nodes:
        for fb in chain:
            node(f"model:{fb}", fb, "model")
            link(f"model:{m}", f"model:{fb}", "fallback")

print(json.dumps({"nodes": list(nodes.values()), "links": links,
                  "node_count": len(nodes), "link_count": len(links)}, indent=2))
