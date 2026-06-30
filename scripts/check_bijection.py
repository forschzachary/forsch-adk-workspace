#!/usr/bin/env python3
"""Filesystem<->graph bijection + artifact-path existence check (R-STRUCT-9, §9).

Adapted from PR #3's package-path checker. PR #3 keyed the bijection on
agent_specs/agents.yaml dotted-package paths; §9 (R-STRUCT-9) requires the
GRAPH-keyed triple set-equality instead, because keying on a yaml registry
green-lights the fluff keys by the operator's own definition.

Rule (both directions, FAIL on any asymmetric element):

    set(agents/<x> dirs on disk)
      == set(agent:<x> node ids in agent-graph-v2.json)
      == set(agent keys in the control-surface registry agents.yaml)

Plus:
  * every `artifact:` path in the graph resolves on disk, after stripping the
    trailing "\\s*\\(.*\\)\\s*$" symbol annotation and expanding globs (logical
    descriptors are skipped);
  * (informational) PR #3's package-path consistency over agent_specs/agents.yaml
    is preserved as a secondary, non-graph check.

Repo root is resolved via `git rev-parse --show-toplevel` so the check runs
from the monorepo root regardless of cwd (the Mac mirror holds only
live-agent-graph/, so it must never be run from inside that subdir).

Exit 0 = bijection holds. Non-zero = at least one asymmetric element.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)


def _graph_path() -> Path:
    p = ROOT / "packages/live-agent-graph/agent-graph-v2.json"
    if p.exists():
        return p
    return ROOT / "live-agent-graph/agent-graph-v2.json"  # pre-migration fallback


def _registry_path() -> Path:
    return ROOT / "packages/live-agent-graph/registry/agents/agents.yaml"


GRAPH = _graph_path()
REGISTRY = _registry_path()
AGENT_SPEC = ROOT / "agent_specs" / "agents.yaml"

ANNOT = re.compile(r"\s*\(.*\)\s*$")
LOGICAL = re.compile(r"external dependency|LiteLLM|authsome|Discord|agents\.yaml group")


def agent_dirs() -> set[str]:
    d = ROOT / "agents"
    if not d.exists():
        return set()
    return {p.name for p in d.iterdir() if p.is_dir()}


def graph_agent_nodes(g: dict) -> set[str]:
    # Native (non-Factory) bots are deliberately NOT generated into agents/<x>/ and are
    # NOT in the Factory registry — they live in capabilities.json + bridge/ and carry
    # "native": true. They are exempt from the agents-dir/registry bijection triple; their
    # artifacts are still validated by artifact_paths_missing().
    return {
        n["id"].split(":", 1)[1]
        for n in g.get("nodes", [])
        if str(n.get("id", "")).startswith("agent:") and not n.get("native")
    }


def registry_agents() -> set[str]:
    if not REGISTRY.exists():
        return set()
    data = yaml.safe_load(REGISTRY.read_text()) or {}
    return set((data.get("agents") or {}).keys())


def artifact_paths_missing(g: dict) -> list[str]:
    bad: list[str] = []
    for n in g.get("nodes", []):
        a = n.get("artifact")
        if not a or "/" not in a or LOGICAL.search(a):
            continue
        p = ANNOT.sub("", a).strip()
        if not (os.path.exists(ROOT / p) or glob.glob(str(ROOT / p))):
            bad.append(a)
    return bad


def package_path_consistency() -> list[str]:
    """Secondary (non-graph) check carried over from PR #3: agent_specs entries
    have a well-formed `package` and no two agents share a package or adk_name.
    Reported as warnings — they do not gate the graph bijection."""
    warns: list[str] = []
    if not AGENT_SPEC.exists():
        return warns
    data = yaml.safe_load(AGENT_SPEC.read_text()) or {}
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return warns
    pkgs: dict[str, str] = {}
    adks: dict[str, str] = {}
    for name, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        pkg = spec.get("package")
        if not pkg or not isinstance(pkg, str):
            warns.append(f"agent_specs '{name}': missing/malformed package")
        elif pkg in pkgs:
            warns.append(f"agent_specs duplicate package '{pkg}': {pkgs[pkg]}, {name}")
        elif isinstance(pkg, str):
            pkgs[pkg] = name
        adk = spec.get("adk_name")
        if adk:
            if adk in adks:
                warns.append(f"agent_specs duplicate adk_name '{adk}': {adks[adk]}, {name}")
            else:
                adks[adk] = name
    return warns


def main() -> int:
    if not GRAPH.exists():
        print(f"FAIL: graph not found at {GRAPH}", file=sys.stderr)
        return 1
    g = json.loads(GRAPH.read_text())

    dirs = agent_dirs()
    nodes = graph_agent_nodes(g)
    reg = registry_agents()

    errs: list[str] = []
    if dirs != nodes:
        errs.append(
            "agents/ dirs != graph agent nodes: "
            f"only-dir={sorted(dirs - nodes)} only-graph={sorted(nodes - dirs)}"
        )
    if nodes != reg:
        errs.append(
            "graph nodes != registry keys: "
            f"only-graph={sorted(nodes - reg)} only-reg={sorted(reg - nodes)}"
        )
    bad = artifact_paths_missing(g)
    if bad:
        errs.append(f"artifact paths missing on disk: {bad}")

    # Secondary informational check (non-gating for the graph bijection).
    for w in package_path_consistency():
        print(f"WARN: {w}")

    if errs:
        print("BIJECTION FAIL:")
        for e in errs:
            print("  -", e)
        return 1

    print("BIJECTION OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
