"""Shared graph-introspection tools for ADK orchestrator agents."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_GRAPH_PATH = Path(os.environ.get(
    "FORSCH_ADK_WORKSPACE", "/root/.hermes/workspace/adk"
)) / "live-agent-graph" / "agent-graph-v2.json"

_CLUSTERS_DIR = _GRAPH_PATH.parent / "clusters"


def _load_graph() -> dict[str, Any]:
    """Load the live agent-graph JSON from disk."""
    with open(_GRAPH_PATH) as f:
        return json.load(f)


def get_graph_overview() -> dict[str, Any]:
    """Return a high-level overview of the agent graph and cluster topology.

    Returns JSON with node_count, link_count, by_type breakdown, and clusters list.
    """
    graph = _load_graph()
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])

    by_type: dict[str, int] = {}
    for node in nodes:
        kind = node.get("kind", node.get("type", "unknown"))
        by_type[kind] = by_type.get(kind, 0) + 1

    clusters: list[str] = []
    if _CLUSTERS_DIR.is_dir():
        clusters = sorted(
            p.name for p in _CLUSTERS_DIR.iterdir() if p.is_dir()
        )

    return {
        "node_count": len(nodes),
        "link_count": len(links),
        "by_type": by_type,
        "clusters": clusters,
        "version": graph.get("version"),
        "active_cluster": graph.get("cluster"),
    }


def manage_cluster(action: str = "list", name: str | None = None) -> dict[str, Any]:
    """Manage clusters: list, create, or switch.

    Actions:
        list    - return all cluster names (default)
        create  - create a new cluster directory with a stub cluster.yaml
        switch  - return which cluster is active (reads graph "cluster" field)
    """
    if action == "list":
        clusters: list[str] = []
        if _CLUSTERS_DIR.is_dir():
            clusters = sorted(
                p.name for p in _CLUSTERS_DIR.iterdir() if p.is_dir()
            )
        return {"action": "list", "clusters": clusters}

    if action == "create":
        if not name:
            return {"action": "create", "error": "name is required"}
        target = _CLUSTERS_DIR / name
        if target.exists():
            return {"action": "create", "error": f"cluster '{name}' already exists"}
        target.mkdir(parents=True, exist_ok=True)
        (target / "cluster.yaml").write_text(
            f"name: {name}\ncreated_by: graph_tools\n"
        )
        return {"action": "create", "cluster": name, "path": str(target)}

    if action == "switch":
        graph = _load_graph()
        return {
            "action": "switch",
            "active_cluster": graph.get("cluster"),
            "note": "cluster field is read-only in graph JSON; edit agent-graph-v2.json to change",
        }

    return {"action": action, "error": f"unknown action '{action}'"}


def get_factory_status() -> dict[str, Any]:
    """Return factory-wide health: agent count, agent list, and tool modules."""
    graph = _load_graph()
    nodes = graph.get("nodes", [])

    agents: list[dict[str, Any]] = []
    tools: list[str] = []
    for node in nodes:
        kind = node.get("kind", node.get("type", "unknown"))
        if kind == "agent":
            agents.append({
                "id": node["id"],
                "name": node.get("name", node["id"]),
                "state": node.get("state", "unknown"),
            })
        elif kind == "tool":
            tools.append(node.get("name", node["id"]))

    return {
        "agent_count": len(agents),
        "agents": agents,
        "tool_modules": sorted(tools),
        "total_nodes": len(nodes),
        "total_links": len(graph.get("links", [])),
        "graph_version": graph.get("version"),
    }
