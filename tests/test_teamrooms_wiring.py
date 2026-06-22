"""Wiring gate — decide whether the Team Rooms poller should start. Pure + tested so
the live startup hook stays a one-liner and never starts a misconfigured poller.
"""
from forsch.adk_bridge.teamrooms.wiring import poller_gate

ENABLED = {"teamrooms": {"enabled": True, "base_url": "https://crm.x", "bot_user": "bot@x"}}
ENV_OK = {"GAMEPLAN_BOT_KEY": "K", "GAMEPLAN_BOT_SECRET": "S"}


def test_disabled_by_default():
    ok, reason = poller_gate({"teamrooms": {"enabled": False}}, ENV_OK)
    assert ok is False and reason == "disabled"


def test_missing_block_is_disabled():
    ok, reason = poller_gate({}, ENV_OK)
    assert ok is False and reason == "disabled"


def test_missing_creds():
    ok, reason = poller_gate(ENABLED, {})
    assert ok is False and reason == "missing_creds"


def test_missing_bot_user():
    cfg = {"teamrooms": {"enabled": True, "base_url": "https://crm.x"}}
    ok, reason = poller_gate(cfg, ENV_OK)
    assert ok is False and reason == "missing_bot_user"


def test_missing_base_url():
    cfg = {"teamrooms": {"enabled": True, "bot_user": "bot@x"}}
    ok, reason = poller_gate(cfg, ENV_OK)
    assert ok is False and reason == "missing_base_url"


def test_base_url_from_env_ok():
    cfg = {"teamrooms": {"enabled": True, "bot_user": "bot@x"}}
    ok, reason = poller_gate(cfg, {**ENV_OK, "GAMEPLAN_BASE_URL": "https://crm.x"})
    assert ok is True and reason == "ok"


def test_fully_configured_ok():
    ok, reason = poller_gate(ENABLED, ENV_OK)
    assert ok is True and reason == "ok"
