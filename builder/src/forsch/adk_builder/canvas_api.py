"""Build the data the Agent Builder canvas renders.

Reads the live manifest (``agent_specs/agents.yaml``) and the component palette
(public tool functions under ``components/.../tools``). Returns plain dicts that
the cockpit inlines into the canvas page as JSON — no client API calls, so it
works unchanged behind the Frappe reverse-proxy.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

DEFAULT_MODEL = "openai/gpt-5.5"


def _safe_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _palette(ws: Path) -> list[dict]:
    """Public tool functions discovered under the components package."""
    tools_dir = ws / "components" / "src" / "forsch" / "adk_components" / "tools"
    out: list[dict] = []
    for py in sorted(tools_dir.glob("*.py")):
        if py.name == "__init__.py":
            continue
        try:
            tree = ast.parse(py.read_text())
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                doc = ast.get_docstring(node) or ""
                summary = doc.strip().splitlines()[0] if doc.strip() else ""
                out.append({"name": node.name, "module": py.stem, "summary": summary[:90]})
    return out


def build_view(workspace_root: str) -> dict:
    ws = Path(workspace_root)
    raw = _safe_yaml(ws / "agent_specs" / "agents.yaml")
    agents: list[dict] = []
    for aid, spec in (raw.get("agents") or {}).items():
        spec = spec or {}
        entry = spec.get("web_entrypoint")
        rendered = ""
        if entry:
            ra = ws / entry / "root_agent.yaml"
            if ra.exists():
                rendered = ra.read_text()
        agents.append(
            {
                "id": aid,
                "name": spec.get("adk_name") or aid,
                "description": spec.get("description", ""),
                "model": DEFAULT_MODEL,
                "safety": spec.get("safety_level", "read_only"),
                "instruction": (spec.get("instruction", "") or "").strip(),
                "tools": [t.rsplit(".", 1)[-1] for t in (spec.get("tools") or [])],
                "channels": spec.get("discord_channels") or [],
                "smoke_prompts": spec.get("smoke_prompts") or [],
                "rendered_yaml": rendered,
            }
        )

    used = {t for a in agents for t in a["tools"]}
    palette = [p for p in _palette(ws) if p["name"] not in used]
    return {"agents": agents, "palette": palette}
