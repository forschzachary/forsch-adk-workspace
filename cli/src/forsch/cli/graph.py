"""Mirror built agents into the live-agent-graph registry, so the map updates as you build.

The graph (packages/live-agent-graph) renders from its own registry —
``packages/live-agent-graph/registry/agents/agents.yaml`` — a SUBSET of the manifest
(description, discord_channels, safety_level, purpose, tools as BARE names, model, role,
group). The factory's source of truth is agent_specs/agents.yaml. This keeps the two in
sync on every ``forsch build``, with a graceful skip when the graph package isn't present.
"""
from __future__ import annotations

from pathlib import Path

_GRAPH_REGISTRY = ("packages", "live-agent-graph", "registry", "agents", "agents.yaml")
_SUBSET = ("description", "discord_channels", "safety_level", "purpose", "tools", "model", "role", "group")


def graph_registry_path(ws: Path) -> Path:
    return ws.joinpath(*_GRAPH_REGISTRY)


def _bare(tool: str) -> str:
    """The graph registry lists bare tool names; the manifest uses fully-qualified paths."""
    return tool.rsplit(".", 1)[-1]


def sync_agent_to_graph_registry(ws: Path, agent_id: str, spec: dict) -> bool:
    """Mirror one agent's graph-subset into the live-agent-graph registry.

    Returns True if synced, False (a graceful no-op) when the graph package/registry
    isn't present in this workspace. Atomic write; preserves the registry's other entries
    and its ``version`` key.
    """
    path = graph_registry_path(ws)
    if not path.exists():
        return False

    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(path.read_text()) or {}
    data.setdefault("version", 1)
    agents = data.setdefault("agents", {})

    entry: dict = {}
    for key in _SUBSET:
        val = spec.get(key)
        if val in (None, "", [], {}):
            continue
        entry[key] = [_bare(t) for t in val] if key == "tools" else val
    agents[agent_id] = entry

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        yaml.dump(data, f)
    tmp.replace(path)
    return True
