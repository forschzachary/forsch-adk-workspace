from types import SimpleNamespace as NS
from forsch.adk_bridge.gateway.render import _visible_parts_text


def test_thought_parts_excluded():
    parts = [
        NS(text="We need to compute 17*23...", thought=True),   # reasoning — must be dropped
        NS(text="The answer is 391.", thought=False),           # answer — must be kept
        NS(text=" more thinking", thought=True),                # reasoning — dropped
    ]
    assert _visible_parts_text(parts) == "The answer is 391."


def test_parts_without_thought_attr_are_visible():
    parts = [NS(text="hello")]  # no .thought attribute -> treated as visible
    assert _visible_parts_text(parts) == "hello"


def test_empty_and_none_text_ignored():
    parts = [NS(text="", thought=False), NS(text=None, thought=False), NS(text="ok", thought=False)]
    assert _visible_parts_text(parts) == "ok"
