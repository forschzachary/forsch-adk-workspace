"""Guarded edits to the manifest, then deterministic regeneration.

Writes ``agent_specs/agents.yaml`` round-trip-safe (comments/structure preserved
via ruamel), then runs the Factory to regenerate the agent's artifacts. This is
the operational write path the canvas drives.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from forsch.adk_factory.cli import apply

_TOOL_PREFIX = "forsch.adk_components.tools."

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096  # do not re-wrap long/folded scalars (e.g. purpose)
_yaml.indent(mapping=2, sequence=4, offset=2)  # match the manifest's 6-space list style


def update_agent(workspace_root: str, agent_id: str, patch: dict) -> dict:
    """Apply ``patch`` (instruction and/or tools) to one agent, then regenerate.

    ``patch`` keys: ``instruction`` (str), ``tools`` (list of short names).
    Returns {ok, agent, tools, written, rendered_yaml}.
    """
    ws = Path(workspace_root)
    mpath = ws / "agent_specs" / "agents.yaml"
    data = _yaml.load(mpath.read_text())

    agents = data.get("agents") or {}
    if agent_id not in agents:
        raise KeyError(f"unknown agent: {agent_id}")
    agent = agents[agent_id]

    if "instruction" in patch and patch["instruction"] is not None:
        text = str(patch["instruction"]).rstrip("\n") + "\n"
        agent["instruction"] = LiteralScalarString(text)

    if "tools" in patch and patch["tools"] is not None:
        agent["tools"] = [
            t if t.startswith(_TOOL_PREFIX) else _TOOL_PREFIX + t for t in patch["tools"]
        ]

    buf = StringIO()
    _yaml.dump(data, buf)
    mpath.write_text(buf.getvalue())

    result = apply(mpath, agent_id, str(ws))

    rendered = ""
    entry = agent.get("web_entrypoint")
    if entry:
        ra = ws / entry / "root_agent.yaml"
        if ra.exists():
            rendered = ra.read_text()

    return {
        "ok": True,
        "agent": agent_id,
        "tools": [t.rsplit(".", 1)[-1] for t in agent.get("tools", [])],
        "written": result.get("written", []),
        "rendered_yaml": rendered,
    }
