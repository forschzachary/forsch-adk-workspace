"""Factory CLI surface.

``plan`` is a pure dry-run: it loads the manifest, renders an agent, and returns
the target paths + rendered content **without writing anything**. This return
value is exactly the payload the Builder Cockpit's review gate shows before any
write (spec D5). ``apply`` (backup -> atomic write -> re-validate -> rollback) is
deferred to Slice 1b.
"""

from __future__ import annotations

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
