"""Guarded edits to the manifest, then deterministic regeneration.

Writes ``agent_specs/agents.yaml`` round-trip-safe (ruamel), composes the
agent's group preamble onto its instruction, then regenerates BOTH artifacts:
  - ``web_agents/<id>/root_agent.yaml`` (the ADK-Web wrapper), and
  - ``agents/<id>/src/forsch/agent_<id>/agent.py`` (the runtime the bridge imports).

Composition happens here (the render boundary), not in the manifest or the
canvas view — so the manifest keeps only the agent's own job + its ``group``.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from forsch.adk_factory.cli import write_files
from forsch.adk_factory.loader import load_manifest
from forsch.adk_factory.renderer import compose_instruction, render_agent, render_agent_package

_TOOL_PREFIX = "forsch.adk_components.tools."

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def update_agent(workspace_root: str, agent_id: str, patch: dict) -> dict:
    """Apply ``patch`` to one agent, then regenerate its wrapper and runtime package.
    Handles: instruction, description, tools, model, group, and the flat fields
    discord_channels / web_entrypoint / safety_level. ``model`` pins the LiteLLM model
    (blank = unpin → shared default); ``group`` selects a preamble jacket (blank = none);
    a blank/empty flat field removes the key. Returns
    {ok, agent, tools, model, group, written, rendered_yaml}."""
    ws = Path(workspace_root)
    mpath = ws / "agent_specs" / "agents.yaml"
    data = _yaml.load(mpath.read_text())

    agents = data.get("agents") or {}
    if agent_id not in agents:
        raise KeyError(f"unknown agent: {agent_id}")
    agent = agents[agent_id]

    if patch.get("instruction") is not None:
        agent["instruction"] = LiteralScalarString(str(patch["instruction"]).rstrip("\n") + "\n")
    if patch.get("description") is not None:
        agent["description"] = str(patch["description"])
    if patch.get("tools") is not None:
        agent["tools"] = [
            t if t.startswith(_TOOL_PREFIX) else _TOOL_PREFIX + t for t in patch["tools"]
        ]
    # model pin and group jacket are optional manifest keys: a value sets them,
    # blank removes them (unpin / no jacket). Only act when the key is present so
    # an instruction/tools-only patch never disturbs them.
    if "model" in patch:
        if (m := str(patch["model"] or "").strip()):
            agent["model"] = m
        else:
            agent.pop("model", None)
    if "group" in patch:
        if (g := str(patch["group"] or "").strip()):
            agent["group"] = g
        else:
            agent.pop("group", None)
    # Additional flat manifest fields. set_config gates WHICH ones may be set; here we just
    # write them as data — a value sets the key, blank/empty removes it.
    for key in ("discord_channels", "web_entrypoint", "safety_level"):
        if key in patch:
            if patch[key] in (None, "", []):
                agent.pop(key, None)
            else:
                agent[key] = patch[key]

    buf = StringIO()
    _yaml.dump(data, buf)
    mpath.write_text(buf.getvalue())

    spec = load_manifest(mpath).agents[agent_id]
    spec.instruction = compose_instruction(str(ws), spec)  # group preamble + job

    files = [{"path": rel, "content": c} for rel, c in render_agent(spec).items()]
    files += [{"path": rel, "content": c} for rel, c in render_agent_package(spec).items()]
    written = write_files(ws, files)

    rendered = ""
    entry = agent.get("web_entrypoint")
    if entry and (ra := ws / entry / "root_agent.yaml").exists():
        rendered = ra.read_text()

    return {
        "ok": True,
        "agent": agent_id,
        "tools": [t.rsplit(".", 1)[-1] for t in agent.get("tools", [])],
        "model": agent.get("model") or "",
        "group": agent.get("group") or "",
        "written": written,
        "rendered_yaml": rendered,
    }
