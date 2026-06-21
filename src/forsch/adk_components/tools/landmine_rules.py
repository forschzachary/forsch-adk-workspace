"""Declarative landmine ruleset shared by the stability audit tools."""

from __future__ import annotations

import re

RULES = [
    {"id": "dead-fleet-path", "severity": "high",
     "pattern": r"/opt/data\b",
     "remedy": "the dead fleet mount; read from FORSCH_ADK_WORKSPACE or derive"},
    {"id": "hardcoded-tailnet", "severity": "medium",
     "pattern": r"[\w.-]+\.ts\.net",
     "remedy": "derive from `tailscale status --json` or FORSCH_ADK_FUNNEL_HOST"},
    {"id": "hardcoded-loopback-port", "severity": "low",
     "pattern": r"(?:127\.0\.0\.1|localhost):\d{2,5}",
     "remedy": "env-first with a co-located default"},
    {"id": "hardcoded-model-id", "severity": "low",
     "pattern": r"(?:openai/|gpt-|gemini-|claude-|glm-)[\w.\-/]+",
     "remedy": "source from FORSCH_ADK_MODEL / config"},
]

_COMPILED = [(r, re.compile(r["pattern"])) for r in RULES]


def rule_hits(text: str) -> list[dict]:
    """Return the rules whose pattern matches ``text`` (a single source line/literal)."""
    return [r for r, rx in _COMPILED if rx.search(text)]
