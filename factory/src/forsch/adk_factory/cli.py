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
from forsch.adk_factory.renderer import (
    compose_instruction,
    render_agent,
    render_agent_package,
)
from forsch.adk_factory.validation import (
    validate_agent_tools,
    check_deploy_gate,
    DeployGateBlocked,
    format_report_text,
)


def plan(manifest_path, agent_id: str, *, manifest=None, spec=None) -> dict:
    """Dry-run: return {agent, files:[{path, content}]}. Writes nothing.

    Renders BOTH generated surfaces: the ADK Web wrapper (``root_agent.yaml``)
    AND the runnable Python package (``agent.py``). The package is what the
    bridge imports at runtime, so omitting it silently drifts code from the
    manifest — the exact bug this used to ship.

    Composes the group preamble into the instruction first (preamble + job),
    exactly as the Builder cockpit does — otherwise grouped agents (e.g.
    hubert-team-lead) would render with their preamble stripped. Preambles live
    next to the manifest at ``<workspace>/preambles/``, so the workspace root is
    derived from the manifest path, not from any output dir.

    Pass ``manifest`` and ``spec`` to avoid re-loading (used by apply() which
    already loaded them for validation).
    """
    manifest_path = Path(manifest_path)
    if manifest is None:
        manifest = load_manifest(manifest_path)
    if spec is None:
        spec = manifest.agents[agent_id]
    workspace = manifest_path.resolve().parent.parent  # <ws>/agent_specs/agents.yaml
    # Compose on a COPY — never mutate the shared manifest spec in place, or a second
    # render of it (apply --all reuse, plan-then-apply) would double the preamble.
    spec = spec.model_copy(update={"instruction": compose_instruction(str(workspace), spec)})
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


def apply(manifest_path, agent_id: str, workspace_root, *, force: bool = False, skip_validate: bool = False) -> dict:
    """Render an agent and write its files under workspace_root, safely.

    By default, runs the deploy gate: validates all tools before writing and
    blocks if any are red. Pass ``force=True`` to bypass the gate (writes
    anyway with a warning). Pass ``skip_validate=True`` to skip validation
    entirely.
    """
    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    spec = manifest.agents[agent_id]

    if not skip_validate:
        report = validate_agent_tools(spec)
        try:
            check_deploy_gate(agent_id, report)
        except DeployGateBlocked as e:
            if force:
                print(f"[{agent_id}] ⚠ deploy gate bypassed (--force): {e.report.summary['red']} red tool(s)")
            else:
                raise

    result = plan(manifest_path, agent_id, manifest=manifest, spec=spec)
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
    p.add_argument("command", choices=["apply", "plan", "validate"],
                   help="apply writes files; plan is a dry-run that lists targets; validate checks tool health")
    p.add_argument("--agent", help="agent id to render")
    p.add_argument("--all", action="store_true", help="render every agent in the manifest")
    p.add_argument("--manifest",
                   help="path to agents.yaml (default: <workspace>/agent_specs/agents.yaml)")
    p.add_argument("--workspace", help="workspace root (default: $FORSCH_ADK_WORKSPACE)")
    p.add_argument("--target", default="cloud",
                   choices=["cloud", "local", "hetzner", "railway"],
                   help="which box to validate against (default: cloud)")
    p.add_argument("--ttl", type=int, default=24,
                   help="behavioral TTL in hours (default: 24)")
    p.add_argument("--force", action="store_true",
                   help="bypass the deploy gate (write even if tools are red)")
    p.add_argument("--skip-validate", action="store_true",
                   help="skip validation entirely (no gate check)")
    args = p.parse_args(argv)

    if not args.agent and not args.all and args.command != "validate":
        p.error("specify --agent <id> or --all")

    workspace = Path(args.workspace) if args.workspace else _default_workspace()
    manifest_path = (
        Path(args.manifest) if args.manifest
        else workspace / "agent_specs" / "agents.yaml"
    )

    # validate is a different code path — no agent selection needed
    if args.command == "validate":
        manifest = load_manifest(manifest_path)
        agent_ids = [args.agent] if args.agent else list(manifest.agents)
        for aid in agent_ids:
            spec = manifest.agents[aid]
            report = validate_agent_tools(spec, target=args.target, ttl_hours=args.ttl)
            print(f"\n[{aid}]")
            print(format_report_text(report))
        return 0

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
            try:
                result = apply(manifest_path, aid, workspace,
                               force=args.force, skip_validate=args.skip_validate)
                print(f"[apply] {aid}: wrote {len(result['written'])} file(s)")
                for w in result["written"]:
                    print(f"    {w}")
            except DeployGateBlocked as e:
                print(f"[apply] {aid}: BLOCKED — {e.report.summary['red']} red tool(s)")
                print(format_report_text(e.report))
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
