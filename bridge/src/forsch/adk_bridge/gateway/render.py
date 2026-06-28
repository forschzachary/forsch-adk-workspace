"""Shared rendering helper: user-visible text from ADK event parts (excludes reasoning)."""
from __future__ import annotations


def _visible_parts_text(parts) -> str:
    """Concatenated text from parts that should reach the user — EXCLUDES the model's
    reasoning/thought parts (`part.thought == True`), which must never stream out."""
    return "".join(
        p.text for p in parts
        if getattr(p, "text", None) and not getattr(p, "thought", False)
    )
