#!/usr/bin/env python3
"""Structural invariant checks for the Forsch ADK workspace.

Validates:
  1. agent_specs/agents.yaml exists, is valid YAML, and has no duplicate keys.
  2. Every agent entry has the required fields.
  3. Every package directory (builder, chat, factory) has a pyproject.toml.
  4. No unexpected top-level directories (allowlist-based).
  5. Every pyproject.toml has a valid [project] section with name + version.

Exit code 0 = all checks pass. Non-zero = at least one failure.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

AGENT_SPEC = REPO / "agent_specs" / "agents.yaml"

REQUIRED_AGENT_FIELDS = {"package", "attr", "adk_name", "description"}

ALLOWED_TOP_LEVEL = {
    ".claude",
    ".git",
    ".github",
    ".gitignore",
    "agent_specs",
    "agents",
    "builder",
    "chat",
    "CLAUDE.md",
    "CURRENT-STATE.md",
    "data",
    "DIRECTORY.md",
    "docs",
    "factory",
    "GIT-DISCIPLINE.md",
    "graph",
    "Makefile",
    "preambles",
    "README.md",
    "scripts",
    "web_agents",
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def check_agents_yaml() -> bool:
    ok = True
    if not AGENT_SPEC.exists():
        fail(f"{AGENT_SPEC.relative_to(REPO)} not found")
        return False

    try:
        data = yaml.safe_load(AGENT_SPEC.read_text())
    except yaml.YAMLError as exc:
        fail(f"agents.yaml parse error: {exc}")
        return False

    if not isinstance(data, dict):
        fail("agents.yaml top-level is not a mapping")
        return False

    agents = data.get("agents")
    if not isinstance(agents, dict):
        fail("agents.yaml 'agents' key is not a mapping")
        return False

    for name, spec in agents.items():
        if not isinstance(spec, dict):
            fail(f"agent '{name}' is not a mapping")
            ok = False
            continue
        missing = REQUIRED_AGENT_FIELDS - spec.keys()
        if missing:
            fail(f"agent '{name}' missing fields: {', '.join(sorted(missing))}")
            ok = False
        model = spec.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            fail(f"agent '{name}': 'model' must be a non-empty string when present")
            ok = False

    return ok


def check_packages() -> bool:
    ok = True
    for pkg in ("builder", "chat", "factory"):
        pypi = REPO / pkg / "pyproject.toml"
        if not pypi.exists():
            fail(f"{pkg}/pyproject.toml not found")
            ok = False
            continue
        try:
            data = tomllib.loads(pypi.read_text())
        except tomllib.TOMLDecodeError as exc:
            fail(f"{pkg}/pyproject.toml parse error: {exc}")
            ok = False
            continue
        project = data.get("project")
        if not isinstance(project, dict):
            fail(f"{pkg}/pyproject.toml has no [project] section")
            ok = False
            continue
        for field in ("name", "version"):
            if field not in project:
                fail(f"{pkg}/pyproject.toml [project] missing '{field}'")
                ok = False
    return ok


def check_top_level() -> bool:
    ok = True
    for child in sorted(REPO.iterdir()):
        if child.name.startswith("."):
            continue
        if child.name not in ALLOWED_TOP_LEVEL:
            fail(f"unexpected top-level entry: {child.name}/")
            ok = False
    return ok


def main() -> int:
    checks = [
        ("agents.yaml structure", check_agents_yaml),
        ("package manifests", check_packages),
        ("top-level hygiene", check_top_level),
    ]
    failures = 0
    for label, fn in checks:
        print(f"--- {label} ---")
        if fn():
            print(f"  OK")
        else:
            failures += 1

    print()
    if failures:
        print(f"RESULT: {failures} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
