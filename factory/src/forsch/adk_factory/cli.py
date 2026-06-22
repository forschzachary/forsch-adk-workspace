"""Factory CLI surface.

``plan`` is a pure dry-run: it loads the manifest, renders an agent, and returns
the target paths + rendered content **without writing anything**. This return
value is exactly the payload the Builder Cockpit's review gate shows before any
write (spec D5).

``apply`` performs the write with safety: for every target it backs up existing
content, writes atomically (tmp + ``os.replace``), then re-validates on-disk
content equals intent. Any failure rolls every touched file back to its prior
state (or removes newly-created files). Re-applying an unchanged manifest is a
no-op (idempotent).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from forsch.adk_factory.loader import load_manifest
from forsch.adk_factory.renderer import render_agent, render_agent_package


def plan(manifest_path, agent_id: str) -> dict:
    """Dry-run: return {agent, files:[{path, content}]}. Writes nothing.

    Renders BOTH generated surfaces: the ADK Web wrapper (``root_agent.yaml``)
    AND the runnable Python package (``agent.py``). The package is what the
    bridge imports at runtime, so omitting it silently drifts code from the
    manifest — the exact bug this used to ship.
    """
    manifest = load_manifest(manifest_path)
    spec = manifest.agents[agent_id]
    rendered = {**render_agent(spec), **render_agent_package(spec)}
    files = [{"path": rel, "content": content} for rel, content in rendered.items()]
    return {"agent": agent_id, "files": files}


def write_files(
    workspace_root,
    files: list[dict],
    *,
    verify: Optional[Callable[[Path], bool]] = None,
) -> list[str]:
    """Backup -> atomic write -> verify -> rollback-on-failure for each file.

    ``files`` is a list of {"path": <workspace-relative>, "content": <str>}.
    On any error, restores backed-up files and deletes newly-created ones, then
    re-raises. Returns the list of written absolute paths on success.
    """
    root = Path(workspace_root)
    written: list[Path] = []
    backups: dict[Path, str] = {}
    content_by_target: dict[Path, str] = {}
    try:
        for f in files:
            target = root / f["path"]
            content_by_target[target] = f["content"]
            if target.exists():
                backups[target] = target.read_text()
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(f["content"])
            tmp.replace(target)  # atomic on same filesystem
            written.append(target)
        for target in written:
            ok = (
                target.read_text() == content_by_target[target]
                if verify is None
                else verify(target)
            )
            if not ok:
                raise RuntimeError(f"post-write validation failed: {target}")
        return [str(p) for p in written]
    except Exception:
        for target in written:
            if target in backups:
                target.write_text(backups[target])
            else:
                target.unlink(missing_ok=True)
        raise


def apply(manifest_path, agent_id: str, workspace_root) -> dict:
    """Render an agent and write its files under workspace_root, safely."""
    result = plan(manifest_path, agent_id)
    written = write_files(workspace_root, result["files"])
    return {"agent": agent_id, "written": written}


def _default_workspace() -> Path:
    root = os.environ.get("FORSCH_ADK_WORKSPACE")
    if not root:
        raise SystemExit(
            "FORSCH_ADK_WORKSPACE is not set (and --workspace was not given)"
        )
    return Path(root)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: render agent packages from the manifest.

    Examples:
      python -m forsch.adk_factory.cli apply --agent stability
      python -m forsch.adk_factory.cli plan  --agent stability
      python -m forsch.adk_factory.cli apply --all
    """
    import argparse

    p = argparse.ArgumentParser(
        prog="forsch.adk_factory.cli",
        description="Render ADK agent packages (root_agent.yaml + agent.py) from the manifest.",
    )
    p.add_argument("command", choices=["apply", "plan"],
                   help="apply writes files; plan is a dry-run that lists targets")
    p.add_argument("--agent", help="agent id to render")
    p.add_argument("--all", action="store_true", help="render every agent in the manifest")
    p.add_argument("--manifest",
                   help="path to agents.yaml (default: <workspace>/agent_specs/agents.yaml)")
    p.add_argument("--workspace", help="workspace root (default: $FORSCH_ADK_WORKSPACE)")
    args = p.parse_args(argv)

    if not args.agent and not args.all:
        p.error("specify --agent <id> or --all")

    workspace = Path(args.workspace) if args.workspace else _default_workspace()
    manifest_path = (
        Path(args.manifest) if args.manifest
        else workspace / "agent_specs" / "agents.yaml"
    )

    manifest = load_manifest(manifest_path)
    if args.all:
        agent_ids = list(manifest.agents)
    else:
        if args.agent not in manifest.agents:
            p.error(f"unknown agent {args.agent!r} (have: {', '.join(manifest.agents)})")
        agent_ids = [args.agent]

    for aid in agent_ids:
        if args.command == "plan":
            result = plan(manifest_path, aid)
            print(f"[plan] {aid}:")
            for f in result["files"]:
                print(f"    {f['path']}")
        else:
            result = apply(manifest_path, aid, workspace)
            print(f"[apply] {aid}: wrote {len(result['written'])} file(s)")
            for w in result["written"]:
                print(f"    {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
