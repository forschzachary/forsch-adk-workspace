"""Robust JSON extraction — pull the object out of an LLM reply.

Models (especially across providers like minimax-m3) wrap JSON in prose or ``` fences. Rather
than rely on ADK's strict output_schema enforcement (which can break on a model that doesn't
support structured output), the planner/judge instruct JSON and parse it here: grab from the
first ``{`` to the last ``}``.
"""
from __future__ import annotations


def extract_json(text: str) -> str:
    if not text:
        return ""
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else ""
