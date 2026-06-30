"""Phase 4 — verified provisioning (managed outcome).

Covers, with mocks/dry-runs only (NO live account, NO live Discord, NO live `sr`):
- friend_memory: has_account idempotency + the pending-DM / dm_delivered lifecycle.
- onboarding_tools.provision_access: invite gate, idempotent already_exists, verify-before-return
  success, and the verify-failed gate path (account made but not usable -> ok=False, no success claim).
- onboarding_tools.verify_guest_provisioning: parses the `sr users verify` JSON line.
- discord_bot DM-403: a Forbidden mid-turn queues the pending DM instead of dropping it.
- credential safety: the password is never written to logs.

All filesystem state is isolated to a tmp FORSCH_ADK_WORKSPACE; subprocess is mocked.
"""
from __future__ import annotations

import importlib
import json
import logging

import pytest


@pytest.fixture
def fm(tmp_path, monkeypatch):
    """friend_memory bound to an isolated workspace (no real data/friends writes)."""
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("SR_ADMIN_DISCORD_IDS", "175984567176527873")
    import forsch.adk_bridge.friend_memory as fm
    importlib.reload(fm)
    return fm


@pytest.fixture
def ot(tmp_path, monkeypatch, fm):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.onboarding_tools as ot
    importlib.reload(ot)
    return ot


# ── friend_memory: idempotency + pending-DM lifecycle ───────────────────────

def test_has_account_false_then_true(fm):
    assert fm.has_account("dave") is False
    fm.record_account("42", "Dave", "dave")
    assert fm.has_account("dave") is True
    assert fm.has_account("DAVE") is True  # case-insensitive
    assert fm.has_account("other") is False


def test_has_account_ignores_underscore_files(fm):
    # _invites.json and friends share the dir; the scan must skip _-prefixed bookkeeping files.
    fm.invite_friend("zoe")
    assert fm.has_account("zoe") is False


def test_pending_dm_lifecycle(fm):
    assert fm.get_pending_dm("99") is None
    fm.queue_pending_dm("99", "your login is ...")
    pending = fm.get_pending_dm("99")
    assert pending and pending["content"] == "your login is ..."
    assert pending["attempts"] == 0 and pending["queued_at"]
    # delivering clears the queue + flips the flag
    fm.mark_dm_delivered("99")
    assert fm.get_pending_dm("99") is None
    rec = json.loads((fm._dir() / "99.json").read_text())
    assert rec["dm_delivered"] is True


def test_queue_pending_dm_preserves_first_queued_at(fm):
    fm.queue_pending_dm("7", "first")
    first_ts = fm.get_pending_dm("7")["queued_at"]
    fm.queue_pending_dm("7", "second")
    assert fm.get_pending_dm("7")["queued_at"] == first_ts  # stable across retries
    assert fm.get_pending_dm("7")["content"] == "second"


# ── verify_guest_provisioning: JSON parsing of `sr users verify` ────────────

def test_verify_parses_ok_json(ot, monkeypatch):
    payload = {"ok": True, "jellyfin_user_id": "abc", "visible_items": 0, "jellyseerr_profile_id": 5}
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (True, json.dumps(payload)))
    out = ot.verify_guest_provisioning("1", "dave", "sr-deadbeef")
    assert out["ok"] is True and out["jellyseerr_profile_id"] == 5


def test_verify_parses_failing_gate(ot, monkeypatch):
    payload = {"ok": False, "gate": "jellyseerr", "error": "the 201-but-null break"}
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (False, json.dumps(payload)))
    out = ot.verify_guest_provisioning("1", "dave", "sr-deadbeef")
    assert out["ok"] is False and out["gate"] == "jellyseerr"


def test_verify_handles_non_json(ot, monkeypatch):
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (False, "(couldn't reach the screening room)"))
    out = ot.verify_guest_provisioning("1", "dave", "x")
    assert out["ok"] is False and out["gate"] == "unknown"


# ── provision_access: invite gate, idempotency, verify-before-return ────────

def test_provision_refuses_uninvited(ot):
    out = ot.provision_access("1", "stranger")
    assert out["ok"] is False and "isn't approved" in out["error"]


def test_provision_idempotent_already_exists(ot, fm, monkeypatch):
    fm.invite_friend("dave")
    fm.record_account("1", "Dave", "dave")  # pretend the account already exists
    called = []
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: called.append(args) or (True, "{}"))
    out = ot.provision_access("1", "dave")
    assert out["ok"] is False and out.get("already_exists") is True
    assert called == []  # never shelled out to create a duplicate


def test_provision_verifies_before_success(ot, fm, monkeypatch):
    fm.invite_friend("dave")
    verify_payload = {"ok": True, "jellyfin_user_id": "abc", "visible_items": 0, "jellyseerr_profile_id": 5}

    def fake_sr(args, timeout=120):
        if args[:2] == ["users", "create"]:
            return True, "created dave (abc)"
        if args[:2] == ["users", "verify"]:
            return True, json.dumps(verify_payload)
        raise AssertionError(f"unexpected sr call: {args}")

    monkeypatch.setattr(ot, "_sr", fake_sr)
    out = ot.provision_access("1", "dave")
    assert out["ok"] is True and out["verified"] is True
    assert out["login"]["username"] == "dave" and out["login"]["password"].startswith("sr-")
    assert out["deliver_privately"] is True
    assert fm.has_account("dave") is True  # recorded


def test_provision_fails_when_verify_gate_fails(ot, fm, monkeypatch):
    fm.invite_friend("dave")

    def fake_sr(args, timeout=120):
        if args[:2] == ["users", "create"]:
            return True, "created dave (abc)"
        if args[:2] == ["users", "verify"]:
            return False, json.dumps({"ok": False, "gate": "jellyseerr", "error": "201-but-null"})
        raise AssertionError(args)

    monkeypatch.setattr(ot, "_sr", fake_sr)
    out = ot.provision_access("1", "dave")
    # account was made but NOT usable: must not claim success, must name the gate, must keep the login.
    assert out["ok"] is False and out["verified"] is False
    assert out["account_created"] is True and out["gate"] == "jellyseerr"
    assert "diagnose provision" in out["error"]
    assert out["login"]["password"].startswith("sr-")  # kept for later delivery


def test_provision_create_failure_short_circuits(ot, fm, monkeypatch):
    fm.invite_friend("dave")
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (False, "boom"))
    out = ot.provision_access("1", "dave")
    assert out["ok"] is False and "creation failed" in out["error"]
    assert "verified" not in out  # never reached verify


# ── credential safety: password never logged ───────────────────────────────

def test_password_never_logged(ot, fm, monkeypatch, caplog):
    fm.invite_friend("dave")

    def fake_sr(args, timeout=120):
        if args[:2] == ["users", "create"]:
            return True, "created dave (abc)"
        return True, json.dumps({"ok": True, "jellyfin_user_id": "abc", "visible_items": 0, "jellyseerr_profile_id": 5})

    monkeypatch.setattr(ot, "_sr", fake_sr)
    with caplog.at_level(logging.DEBUG):
        out = ot.provision_access("1", "dave")
    pw = out["login"]["password"]
    assert pw and pw not in caplog.text
    assert "sr-" not in caplog.text


# ── discord_bot DM-403: queue, don't drop ──────────────────────────────────

class _Forbidden403:
    """Stand-in for discord.Forbidden raised on a blocked DM edit."""


def test_deliver_queues_pending_dm_on_forbidden(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import discord

    import forsch.adk_bridge.friend_memory as fm
    importlib.reload(fm)
    import forsch.adk_bridge.discord_bot as db
    importlib.reload(db)

    bot = db.ADKDiscordBot.__new__(db.ADKDiscordBot)
    bot.spec = db.BotSpec(name="huberto_cat", token="x", agent=object())

    class _Loader:
        async def edit(self, content=""):
            # simulate Discord refusing the DM mid-turn
            raise discord.Forbidden.__new__(discord.Forbidden)

    class _Author:
        id = 4242

    class _Msg:
        author = _Author()

    import asyncio
    asyncio.run(bot._deliver(_Msg(), _Loader(), "here is your login: sr-cafef00d"))

    pending = fm.get_pending_dm("4242")
    assert pending is not None
    assert pending["content"] == "here is your login: sr-cafef00d"


def test_deliver_marks_delivered_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.friend_memory as fm
    importlib.reload(fm)
    import forsch.adk_bridge.discord_bot as db
    importlib.reload(db)

    fm.queue_pending_dm("555", "old")  # a pending DM that should clear once delivery works

    bot = db.ADKDiscordBot.__new__(db.ADKDiscordBot)
    bot.spec = db.BotSpec(name="huberto_cat", token="x", agent=object())

    edited = []

    class _Loader:
        async def edit(self, content=""):
            edited.append(content)

    class _Author:
        id = 555

    class _Msg:
        author = _Author()

    import asyncio
    asyncio.run(bot._deliver(_Msg(), _Loader(), "delivered!"))
    assert edited == ["delivered!"]
    assert fm.get_pending_dm("555") is None  # cleared
