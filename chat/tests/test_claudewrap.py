from forsch.adk_chat.claudewrap import map_block, parse_ask_user_question


class _Text:  # mimics claude_agent_sdk.TextBlock
    def __init__(self, text): self.text = text
class _Tool:  # mimics ToolUseBlock
    def __init__(self, name, inp): self.name = name; self.input = inp
class _Result:  # mimics ToolResultBlock
    def __init__(self, content): self.content = content


# ---------------------------------------------------------------------------
# Existing map_block tests
# ---------------------------------------------------------------------------

def test_text_block_maps_to_token():
    assert map_block(_Text("hi")) == ("token", "hi")

def test_tool_use_maps_to_tool():
    kind, name, inp = map_block(_Tool("Bash", {"command": "ls"}))
    assert (kind, name) == ("tool", "Bash") and inp == {"command": "ls"}

def test_tool_result_maps_to_result():
    assert map_block(_Result("done"))[0] == "tool_result"

def test_unknown_block_maps_to_none():
    assert map_block(object()) is None


# ---------------------------------------------------------------------------
# AskUserQuestion tests
# ---------------------------------------------------------------------------

_AQU_INPUT = {
    "questions": [
        {
            "question": "What is your favorite color?",
            "header": "Color",
            "multiSelect": False,
            "options": [
                {"label": "Red", "description": "The color red."},
                {"label": "Blue", "description": "The color blue."},
                {"label": "Green", "description": "The color green."},
            ],
        }
    ]
}

def test_ask_user_question_maps_to_ask_user_event():
    block = _Tool("AskUserQuestion", _AQU_INPUT)
    ev = map_block(block)
    assert ev[0] == "ask_user", f"expected ask_user, got {ev[0]!r}"

def test_ask_user_question_parses_questions():
    block = _Tool("AskUserQuestion", _AQU_INPUT)
    ev = map_block(block)
    questions = ev[1]
    assert len(questions) == 1
    q = questions[0]
    assert q["question"] == "What is your favorite color?"
    assert q["header"] == "Color"
    assert q["multi_select"] is False
    assert len(q["options"]) == 3
    assert q["options"][0] == {"label": "Red", "description": "The color red."}

def test_ask_user_question_multi_select():
    inp = {"questions": [{"question": "Pick topics", "header": "Topics", "multiSelect": True,
                            "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}]}]}
    block = _Tool("AskUserQuestion", inp)
    ev = map_block(block)
    assert ev[0] == "ask_user"
    assert ev[1][0]["multi_select"] is True

def test_ask_user_question_missing_questions_falls_back_to_tool():
    """Malformed AskUserQuestion input with no questions list falls back to generic tool event."""
    block = _Tool("AskUserQuestion", {"bad": "data"})
    ev = map_block(block)
    assert ev[0] == "tool", f"expected tool fallback, got {ev[0]!r}"

def test_parse_ask_user_question_returns_none_for_non_dict_input():
    class _Bad:
        name = "AskUserQuestion"
        input = "not a dict"
    assert parse_ask_user_question(_Bad()) is None

def test_parse_ask_user_question_returns_none_for_empty_questions():
    class _Empty:
        name = "AskUserQuestion"
        input = {"questions": []}
    assert parse_ask_user_question(_Empty()) is None
