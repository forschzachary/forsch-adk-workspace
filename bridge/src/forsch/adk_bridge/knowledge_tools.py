"""Knowledge tools — let the agents read the curated Screening Room reference docs.

The 'Hybrid' knowledge model: the onboarding flow + friend-facing site explanation live in the
personas (it's the agents' core job); the deeper reference lives here as curated, forsch-owned docs
(distilled from the seedbox-ops wiki, no Hermes dependency) that the agents read on demand.
"""
from __future__ import annotations

from pathlib import Path

_KNOWLEDGE = Path(__file__).resolve().parent / "knowledge"


def list_knowledge() -> str:
    """List the Screening Room reference docs available to read_knowledge."""
    docs = sorted(p.stem for p in _KNOWLEDGE.glob("*.md"))
    return "available docs: " + ", ".join(docs) if docs else "(no docs found)"


def read_knowledge(doc: str) -> str:
    """Read a curated Screening Room reference doc by name (e.g. 'site-guide', 'onboarding-playbook',
    'stack'). Use it when you need the details — how the site works, the onboarding steps, or the
    stack topology — instead of guessing."""
    name = doc.strip().lower()
    if name.endswith(".md"):
        name = name[:-3]
    path = _KNOWLEDGE / f"{name}.md"
    if not path.exists():
        return f"no doc named '{name}'. {list_knowledge()}"
    return path.read_text()[:8000]
