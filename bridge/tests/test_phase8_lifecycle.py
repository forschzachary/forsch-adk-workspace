"""Phase 8 — lifecycle (offboard/suspend, scheduling conflicts, partial-failure recovery).

All mocks/dry-runs (NO live `sr`, NO live Jellyfin, NO live Discord, NO live SR-1):

- friend_memory: the new lifecycle stages + state transitions (member -> suspended -> member),
  archive_friend (export-then-wipe), friend_activation_status (read-only), is_archived.
- onboarding_tools: idempotent recovery (resend_login_dm never duplicates an account), reversible
  suspend/resume, and offboard_friend's archive-first / never-hard-delete contract.
- screening_room_tools.schedule_on_sr1: a slot conflict is surfaced for arbitration, not dropped.
- credential safety: a recovered/reset password rides only in the return value, never the log.

Filesystem state (friends/ + audit.jsonl) is isolated to a tmp FORSCH_ADK_WORKSPACE; the process-global
rate limiter is reset per test; subprocess (`_sr` / `_run`) is mocked.
"""
from __future__ import annotations

import importlib
import json
import logging

import pytest

ZACH = "175984567176527873"


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
def ot(tmp_path, monkeypatch, fm):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.rate_limit as rl
    importlib.reload(rl)
    rl.reset_all()
    import forsch.adk_bridge.onboarding_tools as ot
    importlib.reload(ot)
    return ot


@pytest.fixture
def srt(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.audit_log as audit
    importlib.reload(audit)
    import forsch.adk_bridge.rate_limit as rl
    importlib.reload(rl)
    rl.reset_all()
    import forsch.adk_bridge.screening_room_tools as srt
    importlib.reload(srt)
    return srt


# ── friend_memory: lifecycle stages + transitions ──────────────────────────

def test_lifecycle_stages_added():
    import forsch.adk_bridge.friend_memory as fm
    assert "suspended" in fm.ONBOARDING_STAGES
    assert "archived" in fm.ONBOARDING_STAGES
    # the original onboarding stages are preserved in order
    assert fm.ONBOARDING_STAGES[:6] == ("new", "account", "toured", "request_fulfilled", "on_sr1", "member")


def test_set_stage_validates(fm):
    fm.record_account("10", "Dave", "dave")  # -> stage 'account'
    assert fm.set_stage("10", "suspended")["ok"] is True
    assert fm.onboarding_status("10")["stage"] == "suspended"
    # round-trip back to member is allowed (reversible)
    assert fm.set_stage("10", "member")["ok"] is True
    assert fm.onboarding_status("10")["stage"] == "member"
    # an unknown stage is rejected, leaving the record untouched
    assert fm.set_stage("10", "banished")["ok"] is False
    assert fm.onboarding_status("10")["stage"] == "member"


def test_friend_activation_status_read_only(fm):
    # unknown friend -> sane defaults, no record created
    blank = fm.friend_activation_status("404")
    assert blank["account_created"] is False and blank["stage"] == "new"
    assert blank["suspended"] is False and blank["archived"] is False
    assert not (fm._dir() / "404.json").exists()  # pure read — nothing written

    fm.record_account("11", "Eve", "eve")
    fm.mark_dm_delivered("11")
    st = fm.friend_activation_status("11")
    assert st["account_created"] is True and st["dm_delivered"] is True
    assert st["stage"] == "account" and st["suspended"] is False

    fm.set_stage("11", "suspended")
    assert fm.friend_activation_status("11")["suspended"] is True


def test_archive_friend_exports_then_wipes(fm):
    fm.record_account("12", "Finn", "finn")
    fm.remember_about_friend("12", "loves westerns")
    assert (fm._dir() / "12.json").exists()

    out = fm.archive_friend("12", reason="moved away")
    assert out["ok"] is True and out["archived_to"] == "_archive-12.json"
    # active record is gone; the archive holds the data + reason + stage
    assert not (fm._dir() / "12.json").exists()
    assert fm.is_archived("12") is True
    archived = json.loads((fm._dir() / "_archive-12.json").read_text())
    assert archived["name"] == "Finn" and archived["stage"] == "archived"
    assert archived["archive_reason"] == "moved away" and archived["archived_at"]
    assert "loves westerns" in archived.get("facts", [])


def test_archive_friend_missing_record(fm):
    out = fm.archive_friend("nope")
    assert out["ok"] is False
    assert fm.is_archived("nope") is False


# ── onboarding_tools: idempotent recovery (resend) ─────────────────────────

def test_resend_login_dm_resets_not_recreates(ot, fm, monkeypatch):
    calls = []

    def fake_sr(args, timeout=120):
        calls.append(args)
        if args[:2] == ["users", "list"]:
            return True, "name   id   admin  disabled  lastActive\ndave   abc                 2026-06-01"
        if args[:2] == ["users", "passwd"]:
            return True, "password updated for dave"
        raise AssertionError(f"unexpected sr call: {args}")

    monkeypatch.setattr(ot, "_sr", fake_sr)
    out = ot.resend_login_dm("1", "Dave")
    assert out["ok"] is True and out["deliver_privately"] is True
    assert out["login"]["username"] == "dave" and out["login"]["password"].startswith("sr-")
    # idempotent: it RESET (passwd), never CREATE — no duplicate account
    assert ["users", "create"] not in [c[:2] for c in calls]
    assert ["users", "passwd", "dave", out["login"]["password"]] in calls


def test_resend_login_dm_refuses_when_no_account(ot, monkeypatch):
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (True, "name   id\nsomeoneelse  zzz"))
    out = ot.resend_login_dm("1", "ghost")
    assert out["ok"] is False and "no account" in out["error"]


def test_is_account_created_parses_list(ot, monkeypatch):
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (True, "name   id\ndave   abc\neve    def"))
    assert ot.is_account_created("Dave") is True
    assert ot.is_account_created("eve") is True
    assert ot.is_account_created("nobody") is False


def test_is_account_created_falls_back_to_local(ot, fm, monkeypatch):
    # CLI unreachable -> fall back to the local friend record
    fm.record_account("1", "Dave", "dave")
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (False, "(couldn't reach the screening room)"))
    assert ot.is_account_created("dave") is True
    assert ot.is_account_created("stranger") is False


# ── onboarding_tools: reversible suspend / resume ──────────────────────────

def test_suspend_then_resume_roundtrip(ot, fm, monkeypatch):
    fm.record_account("5", "Gus", "gus")
    fm.set_stage("5", "member")
    seen = []
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: seen.append(args) or (True, f"{args[2]} {args[1]}d"))

    sus = ot.suspend_friend_account("Gus", "5", reason="break")
    assert sus["ok"] is True and sus["reversible"] is True
    assert ["users", "disable", "gus"] in seen
    assert fm.onboarding_status("5")["stage"] == "suspended"

    res = ot.resume_friend_account("Gus", "5")
    assert res["ok"] is True
    assert ["users", "enable", "gus"] in seen
    assert fm.onboarding_status("5")["stage"] == "member"


def test_suspend_failure_does_not_change_stage(ot, fm, monkeypatch):
    fm.record_account("6", "Hal", "hal")
    fm.set_stage("6", "member")
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (False, "no Jellyfin user named 'hal'"))
    out = ot.suspend_friend_account("hal", "6")
    assert out["ok"] is False and "could not suspend" in out["error"]
    assert fm.onboarding_status("6")["stage"] == "member"  # unchanged on failure


# ── onboarding_tools: offboard archives, never hard-deletes ────────────────

def test_offboard_archives_and_disables_never_deletes(ot, fm, monkeypatch):
    fm.record_account("7", "Ivy", "ivy")
    seen = []
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: seen.append(args) or (True, "disabled ivy"))

    out = ot.offboard_friend("7", "Ivy", reason="left the club")
    assert out["ok"] is True
    assert out["jellyfin_disabled"] is True and out["archived_to"] == "_archive-7.json"
    # NEVER a hard delete from the tool
    assert ["users", "delete", "ivy"] not in [c[:3] for c in seen]
    assert any(c[:2] == ["users", "disable"] for c in seen)
    # local record archived (export-then-wipe)
    assert not (fm._dir() / "7.json").exists()
    assert fm.is_archived("7") is True


def test_offboard_continues_when_disable_hiccups(ot, fm, monkeypatch):
    # a disable failure must NOT abort the offboard — the record still archives.
    fm.record_account("8", "Jo", "jo")
    monkeypatch.setattr(ot, "_sr", lambda args, timeout=120: (False, "jellyfin unreachable"))
    out = ot.offboard_friend("8", "Jo")
    assert out["ok"] is True and out["jellyfin_disabled"] is False
    assert out["archived_to"] == "_archive-8.json"
    assert fm.is_archived("8") is True


# ── schedule_on_sr1: conflict is surfaced for arbitration, not dropped ──────

def test_schedule_conflict_surfaced(srt, monkeypatch):
    monkeypatch.setattr(
        srt, "_run",
        lambda args, timeout=90: "schedule failed (409): slot already taken (concurrent insert lost the race)",
    )
    out = srt.schedule_on_sr1("Heat", "20:00", dry_run=False)
    assert "SLOT CONFLICT" in out
    assert "another open slot" in out


def test_schedule_horizon_rejection_is_conflict(srt, monkeypatch):
    monkeypatch.setattr(
        srt, "_run",
        lambda args, timeout=90: "schedule failed (409): starts_at is beyond the 48h horizon",
    )
    out = srt.schedule_on_sr1("Heat", "+5d", dry_run=False)
    assert "SLOT CONFLICT" in out


def test_schedule_success_not_flagged_conflict(srt, monkeypatch):
    monkeypatch.setattr(
        srt, "_run",
        lambda args, timeout=90: "scheduled Heat at Jun 30, 8:00 PM — reflowed 2 program(s)",
    )
    out = srt.schedule_on_sr1("Heat", "20:00", dry_run=False)
    assert "SLOT CONFLICT" not in out and "scheduled Heat" in out


def test_schedule_dry_run_no_audit(srt, monkeypatch):
    import forsch.adk_bridge.audit_log as audit
    monkeypatch.setattr(srt, "_run", lambda args, timeout=90: "DRY RUN: would schedule Heat at ... (reflow 2 program(s))")
    srt.schedule_on_sr1("Heat", "20:00", dry_run=True)
    assert audit.read_audit_log() == []  # dry run writes nothing


def test_is_schedule_conflict_markers(srt):
    assert srt._is_schedule_conflict("schedule failed (409): ...") is True
    assert srt._is_schedule_conflict("slot already taken") is True
    assert srt._is_schedule_conflict("scheduled Heat — reflowed 1 program(s)") is False


# ── credential safety: recovery password never logged ──────────────────────

def test_resend_password_never_logged(ot, monkeypatch, caplog):
    def fake_sr(args, timeout=120):
        if args[:2] == ["users", "list"]:
            return True, "name   id\ndave   abc"
        return True, "password updated for dave"

    monkeypatch.setattr(ot, "_sr", fake_sr)
    with caplog.at_level(logging.DEBUG):
        out = ot.resend_login_dm("1", "dave")
    pw = out["login"]["password"]
    assert pw and pw not in caplog.text
    assert "sr-" not in caplog.text
