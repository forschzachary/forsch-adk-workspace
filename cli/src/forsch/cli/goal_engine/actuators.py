"""Actuator registry — maps a GoalStep.actuator to the factory verb that performs it.

Execution is DETERMINISTIC: the typed plan already says what to do, so a step runs a verb
function — no LLM needed to act. Each returns an evidence string the Judge reads. Critically,
the registry holds ONLY safe verbs; deploy and delete are not wired in, so /goal physically
cannot cross the deploy gate (CLAUDE.md §4). 'consult' and 'manual' have no actuator — the
engine treats them as advisory / park-and-report.
"""
from __future__ import annotations

from pathlib import Path


def actuate(ws: Path, actuator: str, args: dict) -> str:
    """Run the verb for a step; return an evidence string. Raises on a real failure."""
    fn = _REGISTRY.get(actuator)
    if fn is None:
        return f"(no actuator for '{actuator}' — advisory/manual; not executed)"
    return fn(ws, args or {})


def _build_agent(ws: Path, args: dict) -> str:
    from forsch.adk_factory.cli import apply
    from forsch.adk_factory.loader import load_manifest

    from forsch.cli.graph import sync_agent_to_graph_registry

    aid = args["agent_id"]
    res = apply(ws / "agent_specs" / "agents.yaml", aid, ws)
    spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[aid]
    synced = sync_agent_to_graph_registry(ws, aid, spec.model_dump())
    return f"built {aid}: {len(res['written'])} file(s) written; graph_synced={synced}"


def _add_tool(ws: Path, args: dict) -> str:
    from forsch.adk_builder.editor import update_agent
    from forsch.adk_factory.loader import load_manifest

    aid = args["agent_id"]
    tool = args["tool_name"].rsplit(".", 1)[-1]
    spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[aid]
    bare = [t.rsplit(".", 1)[-1] for t in spec.tools]
    if tool in bare:
        return f"{tool} already on {aid}"
    update_agent(str(ws), aid, {"tools": bare + [tool]})
    return f"added {tool} to {aid} (rebuilt)"


def _promote(ws: Path, args: dict) -> str:
    from forsch.adk_builder.promote import promote_agent

    res = promote_agent(str(ws), args["agent_id"])
    return f"promoted {args['agent_id']}: folded {res['patch_keys'] or 'nothing (already in sync)'}"


def _check_agent(ws: Path, args: dict) -> str:
    from forsch.adk_factory.loader import load_manifest
    from forsch.adk_factory.validation import format_report_text, validate_agent_tools

    spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[args["agent_id"]]
    return format_report_text(validate_agent_tools(spec))


def _run_eval(ws: Path, args: dict) -> str:
    from forsch.cli.evals import eval_set_path, run_eval

    aid = args["agent_id"]
    set_file = eval_set_path(ws, aid)
    if not set_file.exists():
        return f"no eval set for {aid} (run: forsch eval {aid} --new)"
    ok = run_eval(ws, aid, set_file, threshold=float(args.get("threshold", 0.7)))
    return f"eval {aid}: {'PASS' if ok else 'FAIL'}"


_REGISTRY = {
    "build_agent": _build_agent,
    "add_tool": _add_tool,
    "promote_edits": _promote,
    "check_agent": _check_agent,
    "run_eval": _run_eval,
    # 'consult' + 'manual' intentionally absent -> advisory / park-and-report.
    # 'deploy' + 'delete' intentionally DO NOT EXIST -> /goal cannot cross the gate.
}

SAFE_ACTUATORS = tuple(_REGISTRY)
