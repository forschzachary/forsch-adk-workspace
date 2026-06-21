"""Validate a spec against the known component palette.

A tool the palette doesn't have yet is NOT an error — it is the signal to mint a
new ability (Slice 5) and factorize it into ``components/``. The validator just
classifies; the caller decides.
"""

from __future__ import annotations

from forsch.adk_factory.models import AgentSpec


def classify_tools(spec: AgentSpec, known: set[str]) -> tuple[list[str], list[str]]:
    """Split a spec's tools into (already-in-palette, new-ability) lists."""
    known_tools = [t for t in spec.tools if t in known]
    new_tools = [t for t in spec.tools if t not in known]
    return known_tools, new_tools
