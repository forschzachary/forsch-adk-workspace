"""Tests for the AskUserQuestion render helpers in cl_app.

cl_app imports chainlit and opens HUBERT_SOUL_PATH at module load, so these tests
require IS_SANDBOX + HUBERT_SOUL_PATH in the env (conftest sets them).
"""
import pytest

from forsch.adk_chat import cl_app


_Q_SINGLE = {
    "header": "Color",
    "question": "What is your favorite color?",
    "multi_select": False,
    "options": [
        {"label": "Red", "description": "the color red"},
        {"label": "Blue", "description": ""},
    ],
}

_Q_MULTI = {
    "header": "Topics",
    "question": "Pick topics",
    "multi_select": True,
    "options": [
        {"label": "A", "description": "alpha"},
        {"label": "B", "description": "beta"},
    ],
}


def test_render_includes_header_and_question():
    md = cl_app._render_ask_user_markdown(_Q_SINGLE)
    assert "**Color**" in md
    assert "What is your favorite color?" in md


def test_render_single_select_hint():
    md = cl_app._render_ask_user_markdown(_Q_SINGLE)
    assert "Click an option below" in md
    assert "type your own reply" in md


def test_render_multi_select_hint():
    md = cl_app._render_ask_user_markdown(_Q_MULTI)
    assert "Select all that apply" in md


def test_option_actions_one_per_option():
    actions = cl_app._option_actions(_Q_SINGLE)
    assert len(actions) == 2
    assert [a.label for a in actions] == ["Red", "Blue"]


def test_option_actions_name_and_payload():
    actions = cl_app._option_actions(_Q_SINGLE)
    a = actions[0]
    assert a.name == "ask_user_option"
    assert a.payload == {"label": "Red", "header": "Color"}


def test_option_actions_tooltip_falls_back_to_label():
    actions = cl_app._option_actions(_Q_SINGLE)
    # First option has a description -> used as tooltip
    assert actions[0].tooltip == "the color red"
    # Second option has empty description -> tooltip falls back to label
    assert actions[1].tooltip == "Blue"


def test_option_actions_empty_when_no_options():
    assert cl_app._option_actions({"options": []}) == []
    assert cl_app._option_actions({}) == []
