"""Render generated artifacts from an ``AgentSpec`` — deterministic, no LLM.

- ``render_agent`` renders the ADK Web editable surface (``root_agent.yaml``),
  golden-file-pinned to the live ``web_agents/stability/root_agent.yaml`` so
  "regenerate" provably equals current behavior.
- ``render_agent_package`` renders the runnable agent module (``agent.py``).
  It is NOT byte-pinned (a hand-written agent.py wraps its instruction string
  arbitrarily); instead it is verified by *functional equivalence* — executing
  the generated code constructs an ``Agent`` with the manifest's exact name,
  description, instruction, and tools.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from forsch.adk_factory.models import AgentSpec

# factory/src/forsch/adk_factory/renderer.py -> parents[3] == factory/
_TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
)


def _indent_block(text: str, spaces: int = 2) -> str:
    """Indent each line of a block scalar by ``spaces`` (no trailing newline)."""
    pad = " " * spaces
    return "\n".join(pad + line for line in text.rstrip("\n").split("\n"))


def render_agent(spec: AgentSpec) -> dict[str, str]:
    """Return a map of workspace-relative path -> rendered file content (web surface)."""
    out: dict[str, str] = {}
    if spec.web_entrypoint:
        tmpl = _env.get_template("root_agent.yaml.j2")
        out[f"{spec.web_entrypoint}/root_agent.yaml"] = tmpl.render(
            a=spec,
            instruction_block=_indent_block(spec.instruction),
        )
    return out


def render_agent_package(spec: AgentSpec) -> dict[str, str]:
    """Return a map of workspace-relative path -> rendered runnable agent module.

    Tools in the manifest are fully-qualified (``forsch.adk_components.tools.X``);
    the generated module imports the leaf names from the components package.
    """
    leaves = [t.rsplit(".", 1)[-1] for t in spec.tools]
    tmpl = _env.get_template("agent.py.j2")
    content = tmpl.render(
        a=spec,
        tool_leaves=leaves,
        name_repr=repr(spec.adk_name),
        description_repr=repr(spec.description),
        instruction_repr=repr(spec.instruction.rstrip("\n")),
    )
    rel = f"agents/{spec.id}/src/forsch/agent_{spec.id}/agent.py"
    return {rel: content}
