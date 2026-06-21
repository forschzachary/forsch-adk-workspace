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

from pathlib import Path
from typing import Callable, Optional

from forsch.adk_factory.loader import load_manifest
from forsch.adk_factory.renderer import render_agent


def plan(manifest_path, agent_id: str) -> dict:
    """Dry-run: return {agent, files:[{path, content}]}. Writes nothing."""
    manifest = load_manifest(manifest_path)
    spec = manifest.agents[agent_id]
    files = [
        {"path": rel, "content": content}
        for rel, content in render_agent(spec).items()
    ]
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
