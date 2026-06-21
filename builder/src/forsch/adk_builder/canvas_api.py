"""Build the data the Agent Builder canvas renders.

Reads the live manifest (``agent_specs/agents.yaml``) and a "toolbox" of the
workspace's components, grouped into drawers (Tools / Clients / Agents). Each
toolbox item carries its absolute file path so the UI's edit button can open it
in the embedded terminal. Returns plain dicts the cockpit inlines as JSON.
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


def _summary(node) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.strip().splitlines()[0][:90] if doc.strip() else ""


def _toolbox(ws: Path) -> list[dict]:
    """Drawers of editable components. Tools are wireable onto agents; the rest
    are editable infrastructure."""
    tools: list[dict] = []
    clients: list[dict] = []
    comp = ws / "components" / "src" / "forsch" / "adk_components"
    for py in sorted(comp.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        try:
            tree = ast.parse(py.read_text())
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                tools.append({"name": node.name, "summary": _summary(node), "file": str(py), "wireable": True})
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                clients.append({"name": node.name, "summary": _summary(node), "file": str(py), "wireable": False})

    agents: list[dict] = []
    adir = ws / "agents"
    if adir.is_dir():
        for ag in sorted(p for p in adir.iterdir() if p.is_dir()):
            f = ag / "src" / "forsch" / f"agent_{ag.name}" / "agent.py"
            if f.exists():
                agents.append({"name": ag.name, "summary": "agent package", "file": str(f), "wireable": False})

    drawers = [
        {"drawer": "Tools", "items": tools},
        {"drawer": "Clients", "items": clients},
        {"drawer": "Agents", "items": agents},
    ]
    return [d for d in drawers if d["items"]]


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
    return {"agents": agents, "toolbox": _toolbox(ws)}
