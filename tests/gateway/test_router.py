from forsch.adk_bridge.gateway.message import CanonicalMessage
from forsch.adk_bridge.gateway.router import resolve_agent

AGENTS = {"build", "ops", "assistant", "shelby"}
CONFIG = {"mention_routing": True, "source_defaults": {"discord": "assistant"}}


def test_explicit_target_wins():
    m = CanonicalMessage(source="discord", sender="u", text="hi", target="build")
    assert resolve_agent(m, AGENTS, CONFIG) == "build"


def test_unknown_explicit_target_is_ignored():
    m = CanonicalMessage(source="discord", sender="u", text="hi", target="nope")
    assert resolve_agent(m, AGENTS, CONFIG) == "assistant"


def test_mention_routing():
    m = CanonicalMessage(source="sms", sender="u", text="hey @shelby look at this")
    assert resolve_agent(m, AGENTS, CONFIG) == "shelby"


def test_mention_is_case_insensitive_and_word_bounded():
    assert resolve_agent(CanonicalMessage(source="sms", sender="u", text="@OPS ping"), AGENTS, CONFIG) == "ops"
    assert resolve_agent(CanonicalMessage(source="sms", sender="u", text="@opsworld"), AGENTS, CONFIG) is None


def test_source_default_when_no_target_no_mention():
    m = CanonicalMessage(source="discord", sender="u", text="just chatting")
    assert resolve_agent(m, AGENTS, CONFIG) == "assistant"


def test_no_match_returns_none():
    m = CanonicalMessage(source="sms", sender="u", text="just chatting")
    assert resolve_agent(m, AGENTS, CONFIG) is None


def test_mention_routing_disabled():
    cfg = {"mention_routing": False, "source_defaults": {}}
    m = CanonicalMessage(source="sms", sender="u", text="@shelby hi")
    assert resolve_agent(m, AGENTS, cfg) is None


from forsch.adk_bridge.gateway.router import build_source_defaults


def test_source_defaults_from_dm_fallback():
    # dm_fallback no longer seeds discord source_defaults — it's injected at the adapter layer.
    cfg = {"agents": {"assistant": {}, "dm_fallback": "assistant"}}
    assert build_source_defaults(cfg) == {}


def test_explicit_source_defaults_block_overrides_and_merges():
    # explicit source_defaults still work as before; dm_fallback is irrelevant here.
    cfg = {"agents": {"dm_fallback": "assistant"}, "source_defaults": {"sms": "assistant", "discord": "ops"}}
    out = build_source_defaults(cfg)
    assert out["discord"] == "ops"
    assert out["sms"] == "assistant"
