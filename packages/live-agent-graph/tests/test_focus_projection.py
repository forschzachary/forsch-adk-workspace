from __future__ import annotations


def lid(value):
    if isinstance(value, dict):
        return value["id"]
    return value


def agent_neighborhood(data, focused_id):
    """Mirror the browser algorithm for finding an agent's neighborhood."""
    neighbor_ids = {focused_id}
    for link in data["links"]:
        source = lid(link["source"])
        target = lid(link["target"])
        if source == focused_id:
            neighbor_ids.add(target)
        if target == focused_id:
            neighbor_ids.add(source)
    return neighbor_ids


def test_agent_neighborhood_handles_forcegraph_mutated_links():
    data = {
        "nodes": [
            {"id": "agent:ops", "type": "agent"},
            {"id": "tool:deploy", "type": "tool"},
            {"id": "agent:brand", "type": "agent"},
        ],
        "links": [
            {"source": {"id": "agent:ops"}, "target": {"id": "tool:deploy"}},
            {"source": "agent:brand", "target": "tool:deploy"},
        ],
    }
    assert agent_neighborhood(data, "agent:ops") == {"agent:ops", "tool:deploy"}


def test_agent_neighborhood_excludes_unrelated_nodes():
    data = {
        "nodes": [
            {"id": "agent:ops", "type": "agent"},
            {"id": "tool:deploy", "type": "tool"},
            {"id": "tool:other", "type": "tool"},
        ],
        "links": [
            {"source": "agent:ops", "target": "tool:deploy"},
            {"source": "agent:brand", "target": "tool:other"},
        ],
    }
    result = agent_neighborhood(data, "agent:ops")
    assert "tool:other" not in result
    assert "agent:brand" not in result


def test_focus_synthetic_node_ids_are_namespaced_by_agent():
    agent_id = "agent:ops"
    suffixes = ["config", "tools", "evals", "runtime", "chat", "generate", "verify"]
    ids = [f"focus:{agent_id}:{suffix}" for suffix in suffixes]
    assert len(ids) == len(set(ids))
    assert all(node_id.startswith("focus:agent:ops:") for node_id in ids)


def test_focus_synthetic_ids_dont_collide_across_agents():
    ids_a = {f"focus:agent:ops:{s}" for s in ["config", "tools", "evals"]}
    ids_b = {f"focus:agent:brand:{s}" for s in ["config", "tools", "evals"]}
    assert ids_a.isdisjoint(ids_b)
