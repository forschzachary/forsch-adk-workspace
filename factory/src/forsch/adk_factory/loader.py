"""Load and normalize the canonical manifest into typed models.

Applies the top-level ``defaults`` block under each agent before validation, so
the rest of the Factory works with fully-resolved ``AgentSpec`` objects.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from forsch.adk_factory.models import AgentSpec, Manifest


def load_manifest(path) -> Manifest:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    defaults = raw.get("defaults") or {}
    agents: dict[str, AgentSpec] = {}
    for aid, spec in (raw.get("agents") or {}).items():
        merged = {**defaults, **(spec or {}), "id": aid}
        agents[aid] = AgentSpec(**merged)
    return Manifest(version=raw.get("version", 1), agents=agents)
