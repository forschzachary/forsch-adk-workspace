"""Dashboard renderer (Phase 1, read-only).

Renders the collector's ``Workspace`` model into self-contained HTML using
Jinja2 with autoescaping on (no raw user/workspace strings reach the page).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from forsch.adk_builder.models import Workspace


def _templates_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "templates"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("builder templates/ directory not found")


_env = Environment(
    loader=FileSystemLoader(str(_templates_dir())),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_dashboard(workspace: Workspace) -> str:
    """Return the read-only dashboard HTML for ``workspace``."""
    return _env.get_template("index.html").render(ws=workspace, read_only=True)
