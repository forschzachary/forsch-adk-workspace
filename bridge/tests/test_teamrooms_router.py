"""Routing: which agent (if any) should handle a Team Rooms item.

Pure logic, no I/O — the trigger-agnostic core decides the agent here.
"""
from forsch.adk_bridge.teamrooms.router import resolve_agent

CONFIG = {
    "spaces": {"stability-room": "stability", "ops-room": "ops"},
    "mention_routing": True,
}
AGENTS = {"stability", "ops", "assistant"}


def test_space_map_hit():
    assert resolve_agent(project="stability-room", content="hi", agents=AGENTS, config=CONFIG) == "stability"


def test_space_map_miss_no_mention():
    assert resolve_agent(project="random", content="just chatting", agents=AGENTS, config=CONFIG) is None


def test_mention_routes_in_any_space():
    assert resolve_agent(project="random", content="hey @ops can you check the box", agents=AGENTS, config=CONFIG) == "ops"


def test_mention_routing_disabled():
    cfg = {"spaces": {}, "mention_routing": False}
    assert resolve_agent(project="random", content="@ops help", agents=AGENTS, config=cfg) is None


def test_unknown_mention_ignored():
    assert resolve_agent(project="random", content="@nobody help", agents=AGENTS, config=CONFIG) is None


def test_space_takes_priority_over_mention():
    assert resolve_agent(project="stability-room", content="@ops help", agents=AGENTS, config=CONFIG) == "stability"


def test_mention_is_word_bounded():
    # "@opstimal" must not match agent "ops"
    assert resolve_agent(project="random", content="discussing @opstimal strategy", agents=AGENTS, config=CONFIG) is None
