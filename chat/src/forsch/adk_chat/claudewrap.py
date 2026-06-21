"""Map Claude Agent SDK content blocks to UI events (token / tool / tool_result / ask_user)."""

from __future__ import annotations

from typing import Any


def parse_ask_user_question(block: Any) -> list[dict[str, Any]] | None:
    """Extract structured question data from an AskUserQuestion ToolUseBlock.

    Returns a list of question dicts, each with:
      - header: str
      - question: str
      - options: list[{label, description}]
      - multi_select: bool
    Returns None if the block input is not a valid AskUserQuestion payload.
    """
    inp = getattr(block, "input", None)
    if not isinstance(inp, dict):
        return None
    questions_raw = inp.get("questions")
    if not isinstance(questions_raw, list) or not questions_raw:
        return None
    questions = []
    for q in questions_raw:
        if not isinstance(q, dict):
            continue
        questions.append({
            "header": q.get("header", ""),
            "question": q.get("question", ""),
            "options": [
                {"label": o.get("label", ""), "description": o.get("description", "")}
                for o in (q.get("options") or [])
                if isinstance(o, dict)
            ],
            "multi_select": bool(q.get("multiSelect", False)),
        })
    return questions if questions else None


def map_block(block: Any):
    """Return a UI event tuple for one SDK content block, or None to ignore it.
    Duck-typed so it works regardless of exact SDK class identities.

    Event types:
      ("token", text)            - text to stream
      ("ask_user", questions)    - AskUserQuestion: list of parsed question dicts
      ("tool", name, input)      - generic tool use
      ("tool_result", content)   - tool result
    """
    text = getattr(block, "text", None)
    if isinstance(text, str):
        return ("token", text)

    name = getattr(block, "name", None)
    if name is not None and hasattr(block, "input"):
        if name == "AskUserQuestion":
            questions = parse_ask_user_question(block)
            if questions is not None:
                return ("ask_user", questions)
        return ("tool", name, getattr(block, "input"))

    if hasattr(block, "content") and getattr(block, "name", None) is None:
        return ("tool_result", getattr(block, "content"))

    return None
