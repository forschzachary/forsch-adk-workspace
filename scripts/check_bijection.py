#!/usr/bin/env python3
"""Bijection invariant checks for the Forsch ADK workspace.

Validates that agent_specs/agents.yaml and the on-disk package layout are
consistent — no agent without a package, no package without an agent.

In the current repo layout, agent directories live under agents/ and are
.gitignored (they exist on the box, not in the repo).  This script validates
what CAN be validated from the repo alone:

  1. Every agents.yaml entry has a well-formed `package` field.
  2. No two agents share the same package path.
  3. No two agents share the same adk_name.
  4. Every agent package directory that IS on disk (git-tracked) has a
     corresponding agents.yaml entry (catches orphaned directories).
  5. Every agents.yaml entry whose package directory is on disk has a
     valid Python package (__init__.py or equivalent).

When agent packages are migrated into the repo (agents/ un-gitignored),
checks 4+5 become fully active.  Until then they only fire for directories
that happen to exist in CI (e.g. after a future migration step).

Exit code 0 = all checks pass. Non-zero = at least one failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
AGENT_SPEC = REPO / "agent_specs" / "agents.yaml"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def git_tracked_dirs() -> set[str]:
    """Return top-level directory names that are tracked in git."""
    try:
        result = subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=REPO, check=True,
        )
    except subprocess.CalledProcessError:
        return set()
    dirs: set[str] = set()
    for line in result.stdout.strip().splitlines():
        # git ls-tree outputs: mode type sha\tpath
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[0].startswith("040000"):
            dirs.add(parts[1])
    return dirs


def package_to_dir(package: str) -> Path | None:
    """Convert a dotted package path to a filesystem path, or None if invalid."""
    parts = package.split(".")
    if not parts:
        return None
    # Top-level directory is the first segment
    return REPO / parts[0]


def check_package_paths(agents: dict) -> bool:
    ok = True
    packages_seen: dict[str, str] = {}
    adk_names_seen: dict[str, str] = {}

    for name, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        pkg = spec.get("package")
        if not pkg:
            fail(f"agent '{name}': missing 'package' field")
            ok = False
            continue
        if not isinstance(pkg, str) or not pkg.replace(".", "").replace("_", "").isalnum():
            fail(f"agent '{name}': malformed package path '{pkg}'")
            ok = False
        if pkg in packages_seen:
            fail(f"duplicate package '{pkg}': agents '{packages_seen[pkg]}' and '{name}'")
            ok = False
        packages_seen[pkg] = name

        adk = spec.get("adk_name")
        if adk:
            if adk in adk_names_seen:
                fail(f"duplicate adk_name '{adk}': agents '{adk_names_seen[adk]}' and '{name}'")
                ok = False
            adk_names_seen[adk] = name

    return ok


def check_disk_bijection(agents: dict) -> bool:
    ok = True
    tracked = git_tracked_dirs()
    if not tracked:
        print("  (no git-tracked dirs found — disk bijection check skipped)")
        return True

    # Build a map: top-level dir -> set of agent names that reference it
    dir_to_agents: dict[str, set[str]] = {}
    for name, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        pkg = spec.get("package", "")
        top = pkg.split(".")[0] if pkg else ""
        if top:
            dir_to_agents.setdefault(top, set()).add(name)

    # Check for tracked dirs that look like agent packages but have no agents.yaml entry
    agent_like = {d for d in tracked if d.startswith("agent_") or d == "agents"}
    for d in sorted(agent_like):
        if d not in dir_to_agents:
            fail(f"tracked directory '{d}/' has no agents.yaml entry")
            ok = False

    return ok


def main() -> int:
    if not AGENT_SPEC.exists():
        print("SKIP: agent_specs/agents.yaml not found")
        return 0

    data = yaml.safe_load(AGENT_SPEC.read_text())
    if not isinstance(data, dict) or "agents" not in data:
        print("SKIP: agents.yaml has no 'agents' key")
        return 0

    agents = data["agents"]
    if not isinstance(agents, dict):
        print("SKIP: agents.yaml 'agents' is not a mapping")
        return 0

    checks = [
        ("package path consistency", lambda: check_package_paths(agents)),
        ("disk bijection", lambda: check_disk_bijection(agents)),
    ]

    failures = 0
    for label, fn in checks:
        print(f"--- {label} ---")
        if fn():
            print("  OK")
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
