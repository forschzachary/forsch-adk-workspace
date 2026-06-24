"""Render generated artifacts from an ``AgentSpec`` — deterministic, no LLM.

- ``render_agent`` renders the ADK Web editable surface (``root_agent.yaml``).
- ``render_agent_package`` renders the runnable agent module (``agent.py``),
  verified by functional equivalence (executing it builds the right ``Agent``).
- ``compose_instruction`` prepends a group's preamble component to an agent's
  own instruction (the manifest keeps only the job; shared identity/discipline
  lives once in ``preambles/<group>.md``).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from forsch.adk_factory.models import AgentSpec
from forsch.adk_factory.tool_metadata import ToolRegistry

# factory/src/forsch/adk_factory/renderer.py -> parents[3] == factory/
_TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
)

DEFAULT_MODEL = "openai/gpt-5.5"


def _indent_block(text: str, spaces: int = 2) -> str:
    """Indent each line of a block scalar by ``spaces`` (no trailing newline)."""
    pad = " " * spaces
    return "\n".join(pad + line for line in text.rstrip("\n").split("\n"))


def load_preamble(workspace_root, group: str | None) -> str:
    """Return the text of ``preambles/<group>.md`` (empty if no group / missing)."""
    if not group:
        return ""
    p = Path(workspace_root) / "preambles" / f"{group}.md"
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def compose_instruction(workspace_root, spec: AgentSpec) -> str:
    """group preamble + the agent's own job (preamble first, then specialize)."""
    preamble = load_preamble(workspace_root, spec.group)
    job = spec.instruction.strip()
    if preamble and job:
        return f"{preamble}\n\n{job}"
    return preamble or job


def expand_tools(tool_patterns: list[str]) -> list[str]:
    """Expand wildcard patterns like 'crm.*' to concrete FQ tool names.

    Literal FQ names pass through unchanged. Unknown families expand to empty.
    """
    result: list[str] = []
    for pattern in tool_patterns:
        result.extend(ToolRegistry.expand_wildcard(pattern))
    return result


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
    """Return a map of workspace-relative path -> rendered runnable agent module."""
    expanded = expand_tools(spec.tools)
    leaves = [t.rsplit(".", 1)[-1] for t in expanded]
    tmpl = _env.get_template("agent.py.j2")
    # Pinned model HARD-wins (ignores the global FORSCH_ADK_MODEL); unpinned agents
    # fall to the global env default. A bare model name gets the `openai/` proxy
    # convention (litellm routes it to the LiteLLM proxy as an openai-compatible
    # endpoint); an explicit provider prefix (has "/") is kept as-is.
    if spec.model:
        pinned = spec.model if "/" in spec.model else f"openai/{spec.model}"
        model_expr = repr(pinned)
    else:
        model_expr = f'os.environ.get("FORSCH_ADK_MODEL", {DEFAULT_MODEL!r})'
    content = tmpl.render(
        a=spec,
        tool_leaves=leaves,
        expanded_tools=expanded,
        name_repr=repr(spec.adk_name),
        description_repr=repr(spec.description),
        instruction_repr=repr(spec.instruction.rstrip("\n")),
        model_expr=model_expr,
    )
    rel = f"agents/{spec.id}/src/forsch/agent_{spec.id}/agent.py"
    return {rel: content}
