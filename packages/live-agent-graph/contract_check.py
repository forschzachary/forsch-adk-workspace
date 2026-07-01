#!/usr/bin/env python3
"""Contract-checked wiring validator for the Live Agent Graph.

Given two node IDs and the graph manifest, validates that the source's emits
intersect with the target's accepts. Returns the intersection (what flows)
or the gap (what's missing).

Usage:
  python3 contract_check.py agent:stability tool:get_git_state
  python3 contract_check.py --json agent-graph-v2.json agent:stability tool:check_service_health
"""

import json
import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
DEFAULT_GRAPH = SPIKE_DIR / "agent-graph-v2.json"


def load_graph(path: Path) -> dict:
    return json.loads(path.read_text())


def find_node(graph: dict, node_id: str) -> dict | None:
    for n in graph["nodes"]:
        if n["id"] == node_id:
            return n
    return None


def check_contract(source: dict, target: dict) -> dict:
    """Validate that source.emits ∩ target.accepts is non-empty.

    Returns:
      { valid: bool, intersection: [str], source_emits: [str], target_accepts: [str],
        gap: [str] (what source emits that target doesn't accept),
        missing: [str] (what target accepts that source doesn't emit) }
    """
    src_emits = set(source.get("contract", {}).get("emits", []))
    tgt_accepts = set(target.get("contract", {}).get("accepts", []))

    intersection = src_emits & tgt_accepts
    gap = src_emits - tgt_accepts
    missing = tgt_accepts - src_emits

    return {
        "valid": len(intersection) > 0,
        "intersection": sorted(intersection),
        "source_emits": sorted(src_emits),
        "target_accepts": sorted(tgt_accepts),
        "gap": sorted(gap),
        "missing": sorted(missing),
    }


def main():
    args = sys.argv[1:]
    graph_path = DEFAULT_GRAPH

    # Parse --json flag
    if args and args[0] == "--json":
        graph_path = Path(args[1])
        args = args[2:]

    if len(args) < 2:
        print("Usage: python3 contract_check.py [--json GRAPH] <source_id> <target_id>", file=sys.stderr)
        print("Example: python3 contract_check.py agent:stability tool:get_git_state", file=sys.stderr)
        sys.exit(1)

    source_id, target_id = args[0], args[1]
    graph = load_graph(graph_path)

    source = find_node(graph, source_id)
    target = find_node(graph, target_id)

    if not source:
        print(f"Error: source node '{source_id}' not found in graph", file=sys.stderr)
        sys.exit(1)
    if not target:
        print(f"Error: target node '{target_id}' not found in graph", file=sys.stderr)
        sys.exit(1)

    result = check_contract(source, target)
    result["source_id"] = source_id
    result["source_type"] = source["type"]
    result["target_id"] = target_id
    result["target_type"] = target["type"]

    print(json.dumps(result, indent=2))

    if not result["valid"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
