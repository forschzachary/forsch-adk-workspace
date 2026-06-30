"""Skills for the forsch operator — named, reusable capability files (Claude-Code-style).

A skill is just focused know-how the operator can pull on demand: a markdown file under the
workspace ``skills/`` directory. The operator gets two tools — ``list_skills()`` to see what
exists and ``load_skill(name)`` to read one — plus the REPL ``/skills`` command. Add a skill
by dropping a ``.md`` file in ``skills/``; the first non-heading line is its summary.
"""
from __future__ import annotations

from pathlib import Path


def skills_dir(ws: Path) -> Path:
    for cand in (ws / "skills", ws / "cli" / "skills"):
        if cand.is_dir():
            return cand
    return ws / "skills"


def list_skill_names(ws: Path) -> list[str]:
    d = skills_dir(ws)
    return sorted(p.stem for p in d.glob("*.md")) if d.is_dir() else []


def _summary(path: Path) -> str:
    for line in path.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def make_skills_tools(ws: Path) -> list:
    """Two callables ADK auto-wraps into FunctionTools: list_skills + load_skill."""

    def list_skills() -> list[dict]:
        """List the skills (name + one-line summary) the operator can load on demand."""
        d = skills_dir(ws)
        paths = sorted(d.glob("*.md")) if d.is_dir() else []
        return [{"name": p.stem, "summary": _summary(p)} for p in paths]

    def load_skill(name: str) -> str:
        """Load a named skill's full instructions (markdown). Consult it before related work."""
        p = skills_dir(ws) / f"{name}.md"
        if not p.exists():
            avail = ", ".join(list_skill_names(ws)) or "none"
            return f"no skill '{name}'. available: {avail}"
        return p.read_text()

    return [list_skills, load_skill]
