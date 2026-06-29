"""Find the Forsch Factory workspace and put its host-lane packages on sys.path.

The workspace has several separate uv venvs (components/, factory/, builder/, per-agent)
that must never cross. The CLI runs in one env and imports the host-lane Forsch packages
directly by adding their `src/` dirs to sys.path — the container/test/bridge lanes are
shelled out to instead. Pure (no click / no ADK) so it's unit-testable.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path


def find_workspace(start: str | os.PathLike | None = None) -> Path | None:
    """Return the workspace root: $FORSCH_ADK_WORKSPACE if set, else the nearest ancestor
    of ``start`` (default cwd) that contains ``agent_specs/agents.yaml``. None if not found."""
    env = os.environ.get("FORSCH_ADK_WORKSPACE")
    if env:
        return Path(env)
    here = Path(start) if start else Path.cwd()
    for d in [here, *here.parents]:
        if (d / "agent_specs" / "agents.yaml").is_file():
            return d
    return None


def bootstrap_path(ws: str | os.PathLike) -> None:
    """Add the host-lane Forsch package src dirs (and every agent package) to sys.path,
    so ``forsch.adk_factory``, ``forsch.adk_builder``, ``forsch_palette`` etc. import."""
    ws = Path(ws)
    for rel in (
        "factory/src", "builder/src", "scripts",
        "components/src", "packages/adk-components/src",
        "live-agent-graph/src", "packages/live-agent-graph/src",
    ):
        d = ws / rel
        if d.exists() and str(d) not in sys.path:
            sys.path.insert(0, str(d))
    for src in glob.glob(str(ws / "agents" / "*" / "src")):
        if src not in sys.path:
            sys.path.insert(0, src)
    os.environ.setdefault("FORSCH_ADK_WORKSPACE", str(ws))
