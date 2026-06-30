"""Phase 7 — security hardening (admin gate, ops mention-only, rate limits, audit log).

All mocks/dry-runs (NO live `sr`, NO live Discord): the four gates are exercised in isolation.

- invite_friend_admin: a non-admin caller is denied (+ audited); the admin (Zach) is approved (+ audited).
- ops mention-only: BotSpec.mention_only gates a guild channel to @-mentions only; DMs always bypass.
- rate_limit: the sliding-window limiter blocks the N+1 call and is per-(user, action).
- audit_log: every consequential action lands one password-free JSONL line; read-back is admin-only.

Filesystem state (friends/ + audit.jsonl) is isolated to a tmp FORSCH_ADK_WORKSPACE; the process-global
rate limiter is reset per test.
"""
from __future__ import annotations

import importlib
import json

import pytest

ZACH = "175984567176527873"
STRANGER = "999000999"


@pytest.fixture
def fm(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("SR_ADMIN_DISCORD_IDS", ZACH)
    import forsch.adk_bridge.audit_log as audit
    importlib.reload(audit)
    import forsch.adk_bridge.friend_memory as fm
    importlib.reload(fm)
    return fm


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("SR_ADMIN_DISCORD_IDS", ZACH)
    import forsch.adk_bridge.audit_log as audit
    importlib.reload(audit)
    return audit


@pytest.fixture
def rl():
    import forsch.adk_bridge.rate_limit as rl
    importlib.reload(rl)
    rl.reset_all()
    return rl


# ── gate 1: invite_friend_admin (admin-only) ───────────────────────────────

def test_invite_admin_denies_non_admin(fm, audit):
    out = fm.invite_friend_admin(STRANGER, "newguy")
    assert out["ok"] is False and "admin" in out["error"].lower()
    # name was NOT approved
    assert fm.is_invited("newguy")["invited"] is False
    # the denial is audited
    entries = audit.read_audit_log()
    assert any(e["action"] == "invite_denied" and e["caller"] == STRANGER for e in entries)


def test_invite_admin_allows_admin(fm, audit):
    out = fm.invite_friend_admin(ZACH, "Dave")
    assert out["ok"] is True
    assert fm.is_invited("dave")["invited"] is True
    entries = audit.read_audit_log()
    assert any(e["action"] == "invite_issued" and e["caller"] == ZACH and e["details"]["name"] == "dave"
               for e in entries)


def test_invite_admin_id_is_str_coerced(fm):
    # an int caller id (some call sites) still matches the admin set
    out = fm.invite_friend_admin(int(ZACH), "Erin")
    assert out["ok"] is True and fm.is_invited("erin")["invited"] is True


def test_approve_invite_is_unauthenticated_primitive(fm):
    # the back-compat alias is the no-auth primitive — used internally/tests, not exposed as a tool
    assert fm.invite_friend is fm._approve_invite
    fm.invite_friend("zoe")
    assert fm.is_invited("zoe")["invited"] is True


# ── gate 2: ops mention-only (_handles) ────────────────────────────────────

class _Channel:
    def __init__(self, name="team-social", cid="1511377396668825662"):
        self.name = name
        self.id = int(cid)


class _Msg:
    def __init__(self, guild, channel, mentions):
        self.guild = guild
        self.channel = channel
        self.mentions = mentions


def _ops_bot(monkeypatch, tmp_path):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.discord_bot as db
    importlib.reload(db)
    spec = db.BotSpec(name="screening_ops", token="x", agent=object(),
                      dm=False, mention_only=True, channels=["1511377396668825662"])
    bot = db.ADKDiscordBot.__new__(db.ADKDiscordBot)
    bot.spec = spec
    bot._channels = {c.lower().lstrip("#") for c in spec.channels}
    bot._bot_user = object()  # stand-in for self.user
    return db, bot


def test_ops_ignores_non_mention(monkeypatch, tmp_path):
    db, bot = _ops_bot(monkeypatch, tmp_path)
    me = bot._bot_user
    monkeypatch.setattr(type(bot), "user", property(lambda self: me))
    msg = _Msg(guild=object(), channel=_Channel(), mentions=[])  # no @mention
    assert bot._handles(msg) is False


def test_ops_responds_when_mentioned(monkeypatch, tmp_path):
    db, bot = _ops_bot(monkeypatch, tmp_path)
    me = bot._bot_user
    monkeypatch.setattr(type(bot), "user", property(lambda self: me))
    msg = _Msg(guild=object(), channel=_Channel(), mentions=[me])  # @-mentions the bot
    assert bot._handles(msg) is True


def test_ops_ignores_other_channel(monkeypatch, tmp_path):
    db, bot = _ops_bot(monkeypatch, tmp_path)
    me = bot._bot_user
    monkeypatch.setattr(type(bot), "user", property(lambda self: me))
    msg = _Msg(guild=object(), channel=_Channel(name="random", cid="42"), mentions=[me])
    assert bot._handles(msg) is False  # mentioned but wrong channel


def test_mention_only_does_not_break_dms(monkeypatch, tmp_path):
    """A mention_only bot that DOES take DMs still answers them (DMs bypass the mention gate)."""
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.discord_bot as db
    importlib.reload(db)
    spec = db.BotSpec(name="x", token="x", agent=object(), dm=True, mention_only=True)
    bot = db.ADKDiscordBot.__new__(db.ADKDiscordBot)
    bot.spec = spec
    bot._channels = set()
    msg = _Msg(guild=None, channel=object(), mentions=[])  # DM (guild is None)
    assert bot._handles(msg) is True


def test_default_spec_is_not_mention_only(monkeypatch, tmp_path):
    """Huberto's default (channels left empty, mention_only False) is unaffected — DMs still work."""
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.discord_bot as db
    importlib.reload(db)
    spec = db.BotSpec(name="huberto_cat", token="x", agent=object())
    assert spec.mention_only is False
    bot = db.ADKDiscordBot.__new__(db.ADKDiscordBot)
    bot.spec = spec
    bot._channels = set()
    assert bot._handles(_Msg(guild=None, channel=object(), mentions=[])) is True  # DM answered


# ── gate 3: per-user rate limit ────────────────────────────────────────────

def test_rate_limit_allows_up_to_limit_then_blocks(rl):
    # request_movie is 10/hour
    for i in range(10):
        out = rl.check_rate_limit("user1", "request_movie")
        assert out["ok"] is True, f"call {i} should be allowed"
    blocked = rl.check_rate_limit("user1", "request_movie")
    assert blocked["ok"] is False
    assert blocked["retry_after"] > 0
    assert "rate limit" in blocked["reason"].lower()


def test_rate_limit_is_per_user(rl):
    # provision_access is 3/day
    for _ in range(3):
        assert rl.check_rate_limit("alice", "provision_access")["ok"] is True
    assert rl.check_rate_limit("alice", "provision_access")["ok"] is False
    # a different user has their own fresh budget
    assert rl.check_rate_limit("bob", "provision_access")["ok"] is True


def test_rate_limit_is_per_action(rl):
    for _ in range(3):
        rl.check_rate_limit("alice", "provision_access")
    assert rl.check_rate_limit("alice", "provision_access")["ok"] is False
    # a different action for the same user is independent
    assert rl.check_rate_limit("alice", "reset_access")["ok"] is True


def test_rate_limit_window_slides(rl):
    # 4th provision in a day is blocked; once the window passes, it's allowed again
    base = 1_000_000.0
    for _ in range(3):
        assert rl.check_rate_limit("alice", "provision_access", now=base)["ok"] is True
    assert rl.check_rate_limit("alice", "provision_access", now=base + 10)["ok"] is False
    # a day + 1s later, the early calls have aged out
    later = base + 24 * 60 * 60 + 1
    assert rl.check_rate_limit("alice", "provision_access", now=later)["ok"] is True


def test_unknown_action_is_unlimited(rl):
    for _ in range(100):
        assert rl.check_rate_limit("alice", "some_unconfigured_action")["ok"] is True


# ── gate 4: append-only audit log ──────────────────────────────────────────

def test_log_audit_appends_one_line(audit):
    audit.log_audit("provision_access", "1", {"name": "dave"})
    audit.log_audit("request_movie", "1", {"tmdb_id": "603"})
    entries = audit.read_audit_log()
    assert len(entries) == 2
    assert entries[0]["action"] == "provision_access" and entries[0]["caller"] == "1"
    assert entries[1]["details"]["tmdb_id"] == "603"
    assert all("at" in e for e in entries)


def test_audit_redacts_secret_keys(audit):
    # even if a careless caller hands a password, it must NOT land in the log
    audit.log_audit("provision_access", "1", {"name": "dave", "password": "sr-cafef00d", "token": "abc"})
    raw = (audit._path()).read_text()
    assert "sr-cafef00d" not in raw
    assert "abc" not in raw
    entry = audit.read_audit_log()[-1]
    assert entry["details"]["password"] == "[redacted]"
    assert entry["details"]["token"] == "[redacted]"
    assert entry["details"]["name"] == "dave"


def test_audit_is_append_only(audit):
    audit.log_audit("invite_issued", ZACH, {"name": "a"})
    audit.log_audit("invite_issued", ZACH, {"name": "b"})
    # re-read after a third append — earlier lines are preserved (never rewritten)
    audit.log_audit("invite_issued", ZACH, {"name": "c"})
    entries = audit.read_audit_log()
    assert [e["details"]["name"] for e in entries] == ["a", "b", "c"]


def test_audit_read_limit(audit):
    for i in range(10):
        audit.log_audit("request_movie", "1", {"tmdb_id": str(i)})
    recent = audit.read_audit_log(limit=3)
    assert len(recent) == 3
    assert [e["details"]["tmdb_id"] for e in recent] == ["7", "8", "9"]  # newest tail


def test_audit_read_missing_file_is_empty(audit):
    assert audit.read_audit_log() == []


def test_audit_read_admin_gate(audit, fm):
    audit.log_audit("provision_access", "1", {"name": "dave"})
    # non-admin is denied + the attempt is audited
    denied = audit.audit_read_admin(STRANGER)
    assert denied["ok"] is False
    # admin reads the entries back (including the just-recorded denial)
    ok = audit.audit_read_admin(ZACH)
    assert ok["ok"] is True
    actions = [e["action"] for e in ok["entries"]]
    assert "provision_access" in actions
    assert "audit_read_denied" in actions  # the non-admin attempt left a trace


# ── integration: the four expensive actions audit + rate-limit ─────────────

@pytest.fixture
def ot(tmp_path, monkeypatch, fm, audit, rl):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.onboarding_tools as ot
    importlib.reload(ot)
    return ot


def test_provision_rate_limited_after_budget(ot, fm, audit, rl, monkeypatch):
    fm.invite_friend("dave")
    fm.invite_friend("erin")
    fm.invite_friend("finn")
    fm.invite_friend("gwen")

    def fake_sr(args, timeout=120):
        if args[:2] == ["users", "create"]:
            return True, "created (abc)"
        if args[:2] == ["users", "verify"]:
            return True, json.dumps({"ok": True, "jellyfin_user_id": "abc", "visible_items": 0, "jellyseerr_profile_id": 1})
        raise AssertionError(args)

    monkeypatch.setattr(ot, "_sr", fake_sr)
    # same discord id provisioning 4 different invited friends → 4th is rate-limited (3/day)
    for name in ("dave", "erin", "finn"):
        assert ot.provision_access("caller1", name)["ok"] is True
    blocked = ot.provision_access("caller1", "gwen")
    assert blocked["ok"] is False and blocked.get("rate_limited") is True
    # the three successes were audited, and the password never appears in the log
    raw = audit._path().read_text()
    assert raw.count('"action": "provision_access"') == 3
    assert "sr-" not in raw and "password" not in raw.replace('"password"', "")  # no sr- pw token anywhere


def test_provision_audit_has_no_password(ot, fm, audit, monkeypatch):
    fm.invite_friend("dave")

    def fake_sr(args, timeout=120):
        if args[:2] == ["users", "create"]:
            return True, "created (abc)"
        return True, json.dumps({"ok": True, "jellyfin_user_id": "abc", "visible_items": 0, "jellyseerr_profile_id": 1})

    monkeypatch.setattr(ot, "_sr", fake_sr)
    out = ot.provision_access("caller2", "dave")
    pw = out["login"]["password"]
    raw = audit._path().read_text()
    assert pw not in raw  # the real generated password is never in the audit log
    entry = [e for e in audit.read_audit_log() if e["action"] == "provision_access"][-1]
    assert entry["details"]["username"] == "dave"
    assert "password" not in entry["details"]
