"""Render generated artifacts from an ``AgentSpec`` — deterministic, no LLM.

Slice 1 renders the ADK Web editable surface (``root_agent.yaml``) and is
golden-file-pinned to the live ``web_agents/stability/root_agent.yaml`` so that
"regenerate" provably equals current behavior. Later slices add the package,
test stub, and bridge route to the returned map.
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
    """Return a map of workspace-relative path -> rendered file content."""
    out: dict[str, str] = {}
    if spec.web_entrypoint:
        tmpl = _env.get_template("root_agent.yaml.j2")
        out[f"{spec.web_entrypoint}/root_agent.yaml"] = tmpl.render(
            a=spec,
            instruction_block=_indent_block(spec.instruction),
        )
    return out
