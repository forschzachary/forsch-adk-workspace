"""Patterns CLI — super-easy entry point for the building blocks library.

Usage:
    patterns list                       # all blocks (kind + id + one-liner intention)
    patterns list --json                # machine-readable (for the future webpage)
    patterns search "kw"                # keyword search across all inventories
    patterns info <kind> <id>           # full details on one block
    patterns new-agent <id> "desc" "instruction" [tool1 tool2 ...]
    patterns lint                       # drift check across all inventories

Block kinds: pattern, agent, ui, router, datasource
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("patterns CLI: pyyaml not installed", file=sys.stderr)
    sys.exit(1)


BLOCK_KINDS = ["pattern", "agent", "ui", "router", "datasource"]
KIND_TO_DIR = {"pattern": "patterns", "agent": "agents", "ui": "uis", "router": "routers", "datasource": "datasources"}


def _workspace() -> Path:
    return Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/root/.hermes/workspace/adk"))


def _components_root() -> Path:
    return _workspace() / "components" / "src" / "forsch" / "adk_components"


def _load_all_inventories() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for kind in BLOCK_KINDS:
        inv = _components_root() / KIND_TO_DIR[kind] / "inventory.yaml"
        if inv.exists():
            try:
                data = yaml.safe_load(inv.read_text()) or {}
                if kind == "pattern":
                    out[kind] = data.get("patterns", {}) or {}
                else:
                    out[kind] = data.get(kind + "s", data) or {}
            except Exception:
                pass
    return out


def cmd_list(args) -> int:
    invs = _load_all_inventories()
    rows = []
    for kind in BLOCK_KINDS:
        for name, meta in invs.get(kind, {}).items():
            if not isinstance(meta, dict):
                continue
            rows.append({
                "kind": kind,
                "id": name,
                "intention": meta.get("intention", ""),
                "function": meta.get("function", ""),
            })
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no blocks indexed yet")
        return 0
    for r in rows:
        print(f"  [{r['kind']:>10}] {r['id']:25} {r['function']}")
    return 0


def cmd_search(args) -> int:
    invs = _load_all_inventories()
    needle = args.query.lower()
    matches = []
    for kind in BLOCK_KINDS:
        for name, meta in invs.get(kind, {}).items():
            if not isinstance(meta, dict):
                continue
            haystack = " ".join([
                name.lower(),
                meta.get("intention", "").lower(),
                meta.get("function", "").lower(),
                " ".join(meta.get("keywords", []) or []).lower(),
            ])
            if needle in haystack:
                matches.append((kind, name, meta))
    if not matches:
        print(f"no matches for {args.query!r}")
        return 1
    for kind, name, meta in matches:
        print(f"  [{kind:>10}] {name}")
        print(f"    intention: {meta.get('intention', '')}")
        print(f"    function:  {meta.get('function', '')}")
        if meta.get("keywords"):
            print(f"    keywords:  {', '.join(meta['keywords'])}")
    return 0


def cmd_info(args) -> int:
    invs = _load_all_inventories()
    kind = args.kind
    name = args.id
    meta = invs.get(kind, {}).get(name)
    if not meta:
        print(f"unknown {kind}: {name}")
        return 1
    print(json.dumps({name: meta}, indent=2))
    return 0


def cmd_new_agent(args) -> int:
    try:
        from forsch.adk_components.patterns.cluster_spawn import make_agent_files
    except ImportError as exc:
        print(f"cluster_spawn not importable: {exc}", file=sys.stderr)
        return 1
    tools = args.tool or []
    try:
        result = make_agent_files(args.id, args.description, args.instruction, tools)
    except ValueError as exc:
        print(f"new-agent: {exc}", file=sys.stderr)
        return 2
    print(f"agent {args.id} scaffolded; files written:")
    for path, size in result["files_written"].items():
        print(f"  {path} ({size} bytes)")
    return 0


def cmd_lint(args) -> int:
    try:
        from forsch.adk_components.patterns._lint import lint
    except ImportError as exc:
        print(f"_lint not importable: {exc}", file=sys.stderr)
        return 1
    return lint()


def main() -> int:
    p = argparse.ArgumentParser(prog="patterns", description="Building blocks library CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_list = sub.add_parser("list", help="List all indexed blocks")
    sp_list.add_argument("--json", action="store_true", help="machine-readable output")
    sp_list.set_defaults(func=cmd_list)

    sp_search = sub.add_parser("search", help="Keyword search across all inventories")
    sp_search.add_argument("query", help="search keyword")
    sp_search.set_defaults(func=cmd_search)

    sp_info = sub.add_parser("info", help="Full details on one block")
    sp_info.add_argument("kind", choices=BLOCK_KINDS)
    sp_info.add_argument("id")
    sp_info.set_defaults(func=cmd_info)

    sp_new = sub.add_parser("new-agent", help="Scaffold a new ADK agent")
    sp_new.add_argument("id")
    sp_new.add_argument("description")
    sp_new.add_argument("instruction")
    sp_new.add_argument("tool", nargs="*", help="tool names (bare, e.g. log_groceries)")
    sp_new.set_defaults(func=cmd_new_agent)

    sp_lint = sub.add_parser("lint", help="Drift check across all inventories")
    sp_lint.set_defaults(func=cmd_lint)

    args = p.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
