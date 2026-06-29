"""Promote a builder-edited ``web_agents/<id>/root_agent.yaml`` back into the manifest.

The ADK Web Builder edits the GENERATED wrapper (``web_agents/<id>/root_agent.yaml``).
That file is downstream of ``agent_specs/agents.yaml``: a ``factory apply`` would
clobber it, and the Discord bridge runs the separate ``agent.py``. ``promote`` closes
the loop the other way — read the edited wrapper, fold its changes back into the
manifest (the single source of truth), then regenerate BOTH artifacts via
``update_agent`` so the wrapper, the manifest, and ``agent.py`` agree again.

This inverts the forward composition: ``compose_instruction`` renders the wrapper with
the COMPOSED instruction (group preamble + the agent's own job); the manifest stores
only the job, so we strip the preamble back off here. The model pin lives only in the
manifest + ``agent.py`` (the wrapper carries ``model_code``, a constant code ref), so
``promote`` never touches it.

Module-level imports are stdlib-only on purpose: the pure helpers are unit-testable
without ruamel/jinja/the factory. The heavy imports live inside ``promote_agent``.
"""

from __future__ import annotations

from pathlib import Path

_TOOL_PREFIX = "forsch.adk_components.tools."


class PromoteError(RuntimeError):
    """Raised when the wrapper cannot be safely folded back into the manifest."""


def _recover_job(composed: str, preamble: str) -> str:
    """Recover the agent's own job by stripping the group preamble that
    ``compose_instruction`` prepended (``preamble + "\\n\\n" + job``).

    Raises ``PromoteError`` if the agent has a group but the edited instruction no
    longer starts with that preamble — writing it back as the job would double the
    preamble on the next render, so we refuse instead of silently corrupting.
    """
    composed = composed.rstrip("\n")
    if not preamble:
        return composed
    preamble = preamble.strip()
    if composed == preamble:
        return ""  # only the preamble survived; the job was emptied
    prefix = preamble + "\n\n"
    if composed.startswith(prefix):
        return composed[len(prefix):]
    raise PromoteError(
        "the edited instruction does not start with the agent's group preamble, so "
        "promoting it would double the preamble on the next render. Edit the preamble "
        "in preambles/<group>.md, or drop the agent's group, then re-promote."
    )


def _tool_patch(yaml_tools: list[str], manifest_tools: list[str]) -> list[str] | None:
    """Return the explicit tool list to write, or ``None`` if tools are unchanged.

    Preserves wildcard manifest entries (e.g. ``crm.*``) when the edited set matches
    their expansion; writes an explicit list only when the builder actually changed
    the tools — an explicit edit legitimately gives up wildcard compression.
    """
    if any("*" in t for t in manifest_tools):
        from forsch.adk_factory.renderer import expand_tools  # lazy: only needed for wildcards

        if set(yaml_tools) == set(expand_tools(manifest_tools)):
            return None
        return yaml_tools
    return None if yaml_tools == manifest_tools else yaml_tools


def build_promotion_patch(root_yaml: dict, manifest_tools: list[str], preamble: str) -> dict:
    """Pure: turn a parsed ``root_agent.yaml`` dict into an ``update_agent`` patch.

    Only the builder-editable fields are folded back: ``instruction`` (preamble
    stripped to the job), ``description``, and ``tools`` (only when changed).
    """
    patch: dict = {}
    if "instruction" in root_yaml:
        patch["instruction"] = _recover_job(str(root_yaml["instruction"]), preamble)
    if "description" in root_yaml:
        patch["description"] = str(root_yaml["description"]).strip()
    yaml_tools = [
        t["name"]
        for t in (root_yaml.get("tools") or [])
        if isinstance(t, dict) and t.get("name")
    ]
    tools = _tool_patch(yaml_tools, manifest_tools)
    if tools is not None:
        patch["tools"] = tools
    return patch


def promote_agent(workspace_root: str, agent_id: str) -> dict:
    """Fold ``web_agents/<id>/root_agent.yaml`` back into the manifest, then regenerate
    both artifacts via ``update_agent``. Returns ``update_agent``'s result plus
    ``promoted_from`` and ``patch_keys``."""
    import yaml  # lazy

    from forsch.adk_builder.editor import update_agent  # lazy
    from forsch.adk_factory.loader import load_manifest  # lazy
    from forsch.adk_factory.renderer import load_preamble  # lazy

    ws = Path(workspace_root)
    manifest = load_manifest(ws / "agent_specs" / "agents.yaml")
    if agent_id not in manifest.agents:
        raise KeyError(f"unknown agent: {agent_id}")
    spec = manifest.agents[agent_id]
    if not spec.web_entrypoint:
        raise PromoteError(f"{agent_id} has no web_entrypoint — nothing to promote")
    ra_path = ws / spec.web_entrypoint / "root_agent.yaml"
    if not ra_path.exists():
        raise PromoteError(f"no edited wrapper at {ra_path}")

    root_yaml = yaml.safe_load(ra_path.read_text()) or {}
    preamble = load_preamble(str(ws), spec.group)
    patch = build_promotion_patch(root_yaml, spec.tools, preamble)

    result = update_agent(str(ws), agent_id, patch)
    result["promoted_from"] = str(ra_path)
    result["patch_keys"] = sorted(patch)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m forsch.adk_builder.promote --agent <id>``."""
    import argparse
    import os

    p = argparse.ArgumentParser(
        prog="forsch.adk_builder.promote",
        description="Fold a builder-edited web_agents/<id>/root_agent.yaml back into "
        "agent_specs/agents.yaml and regenerate both artifacts.",
    )
    p.add_argument("--agent", required=True, help="agent id to promote")
    p.add_argument("--workspace", help="workspace root (default: $FORSCH_ADK_WORKSPACE)")
    args = p.parse_args(argv)

    ws = args.workspace or os.environ.get("FORSCH_ADK_WORKSPACE")
    if not ws:
        p.error("set --workspace or FORSCH_ADK_WORKSPACE")

    result = promote_agent(ws, args.agent)
    folded = ", ".join(result["patch_keys"]) or "nothing (no changes)"
    print(f"[promote] {args.agent}: folded {folded} into the manifest")
    for w in result["written"]:
        print(f"    {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
