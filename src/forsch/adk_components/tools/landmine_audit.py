"""Stability self-audit tools: detect hardcode/config-drift landmines, propose/apply fixes."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from forsch.adk_components.tools.landmine_rules import RULES, rule_hits

_SKIP_DIRS = {".venv", ".git", "__pycache__", "node_modules"}
_SCAN_EXT = {".py", ".yaml", ".yml", ".sh"}


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if p.suffix in _SCAN_EXT and not any(part in _SKIP_DIRS for part in p.parts) \
                and ".bak" not in p.name:
            yield p


def _env_default_literals(tree: ast.AST) -> set[int]:
    """Line numbers of string literals that are the 2nd arg of os.environ.get(...)
    (the healthy env-first pattern), which must NOT be flagged as raw hardcodes."""
    safe: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and isinstance(node.func.value, ast.Attribute) \
                and node.func.value.attr == "environ" and len(node.args) >= 2 \
                and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            safe.add(node.args[1].lineno)
    return safe


def scan_hardcoded_paths(root: str | None = None) -> list[dict[str, Any]]:
    """AST/line scan for landmine literals, skipping env-first defaults + vendored dirs."""
    base = Path(root or os.environ["FORSCH_ADK_WORKSPACE"]).expanduser().resolve()
    findings: list[dict[str, Any]] = []
    for path in _iter_files(base):
        text = path.read_text(errors="replace")
        safe_lines: set[int] = set()
        if path.suffix == ".py":
            try:
                safe_lines = _env_default_literals(ast.parse(text))
            except SyntaxError:
                pass
        for i, line in enumerate(text.splitlines(), start=1):
            if i in safe_lines:
                continue
            for r in rule_hits(line):
                findings.append({"file": str(path), "line": i, "snippet": line.strip()[:120],
                                 "rule": r["id"], "severity": r["severity"], "remedy": r["remedy"]})
    return findings


def check_env_contract(root: str | None = None) -> list[dict[str, Any]]:
    """Every os.environ.get("X", default) / os.environ["X"] -> is X set, and does its
    default itself trip a rule (e.g. a /opt/data default)?"""
    base = Path(root or os.environ["FORSCH_ADK_WORKSPACE"]).expanduser().resolve()
    seen: dict[str, dict[str, Any]] = {}
    for path in _iter_files(base):
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            var = default = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "get" and isinstance(node.func.value, ast.Attribute) \
                    and node.func.value.attr == "environ" and node.args \
                    and isinstance(node.args[0], ast.Constant):
                var = node.args[0].value
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    default = node.args[1].value
            elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                    and node.value.attr == "environ" and isinstance(node.slice, ast.Constant):
                var = node.slice.value
            if isinstance(var, str) and var not in seen:
                dead = bool(default and isinstance(default, str) and any(h["severity"] == "high" for h in rule_hits(default)))
                seen[var] = {"var": var, "set": var in os.environ,
                             "default": default, "default_looks_dead": dead}
    return list(seen.values())


def detect_config_drift() -> dict[str, Any]:
    """Declared-vs-actual: workspace + env-contract (model/port cross-checks deferred)."""
    root = os.environ.get("FORSCH_ADK_WORKSPACE")
    workspace = {"declared": root, "actual_exists": bool(root) and Path(root).is_dir(), "ok": False}
    workspace["ok"] = workspace["actual_exists"]
    env = [r for r in check_env_contract(root) if not r["set"] and r["default_looks_dead"]]
    return {"workspace": workspace, "env_relying_on_dead_default": env}
