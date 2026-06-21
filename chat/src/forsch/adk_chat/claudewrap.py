"""Map Claude Agent SDK content blocks to UI events (token / tool / tool_result)."""

from __future__ import annotations

from typing import Any


def map_block(block: Any):
    """Return a UI event tuple for one SDK content block, or None to ignore it.
    Duck-typed so it works regardless of exact SDK class identities."""
    text = getattr(block, "text", None)
    if isinstance(text, str):
        return ("token", text)
    name = getattr(block, "name", None)
    if name is not None and hasattr(block, "input"):
        return ("tool", name, getattr(block, "input"))
    if hasattr(block, "content") and getattr(block, "name", None) is None:
        return ("tool_result", getattr(block, "content"))
    return None
