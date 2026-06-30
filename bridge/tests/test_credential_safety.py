"""Phase 10 — credential-safety + runtime gate invariants for the native bots.

The eval gate's runtime half: the consequential tools must hold their gates and never leak a secret.
All mocked/dry-run — NO live `sr`, NO Jellyfin account, NO Discord. Uses the conftest fixtures
(``temp_friends_dir``, ``temp_audit``, ``mock_sr_cli``, ``reset_rate_limit``) so nothing touches the
real ``data/friends`` or ``data/audit.jsonl``.

Invariants:
- provision_access REFUSES an uninvited name (no account, no password minted).
- a generated password is returned ONLY in the tool's ``login`` payload (for the friend's DM) and
  NEVER lands in the append-only audit log — for provision, reset, and resend.
- the admin gate on invites holds (non-admin denied + audited; admin approved).
- audit log redacts any secret a careless caller hands it.
"""
from __future__ import annotations

import json

import pytest

ZACH = "175984567176527873"
STRANGER = "999000999"

_SR_PW_RE = "sr-"  # the password prefix (_gen_password -> "sr-" + 8 hex)


def _verify_ok_payload():
    return json.dumps({"ok": True, "jellyfin_user_id": "u1", "visible_items": 0, "jellyseerr_profile_id": 7})


# ── provision_access: the invite gate refuses uninvited (no secret minted) ──

def test_provision_refuses_uninvited(temp_friends_dir, mock_sr_cli, reset_rate_limit):
    ot = mock_sr_cli.ot
    out = ot.provision_access("1", "stranger")
    assert out["ok"] is False
    assert "isn't approved" in out["error"]
    # it bailed BEFORE shelling out — no account creation attempted, no password in the result
    assert mock_sr_cli.calls == []
    assert "login" not in out


def test_provision_password_is_dm_only_never_logged(temp_friends_dir, temp_audit, mock_sr_cli, reset_rate_limit):
    ot = mock_sr_cli.ot
    temp_friends_dir.invite_friend("dave")

    def sr(args):
        if args[:2] == ["users", "create"]:
            return True, "created dave (u1)"
        if args[:2] == ["users", "verify"]:
            return True, _verify_ok_payload()
        raise AssertionError(args)

    mock_sr_cli.sr_returns = sr
    out = ot.provision_access("caller-1", "dave")

    assert out["ok"] is True and out["verified"] is True
    pw = out["login"]["password"]
    assert pw.startswith(_SR_PW_RE)
    # the password is in the DM payload ONLY — never in the audit log
    raw = temp_audit._path().read_text()
    assert pw not in raw
    assert _SR_PW_RE not in raw  # not even the prefix leaks
    # the audit entry records the username, never a password key
    entry = [e for e in temp_audit.read_audit_log() if e["action"] == "provision_access"][-1]
    assert entry["details"]["username"] == "dave"
    assert "password" not in entry["details"]


def test_reset_access_password_never_logged(temp_friends_dir, temp_audit, mock_sr_cli, reset_rate_limit):
    ot = mock_sr_cli.ot
    mock_sr_cli.sr_returns = lambda args: (True, "reset ok")
    out = ot.reset_access("dave", caller_discord_id="caller-2")
    assert out["ok"] is True
    pw = out["login"]["password"]
    assert pw.startswith(_SR_PW_RE)
    raw = temp_audit._path().read_text()
    assert pw not in raw and _SR_PW_RE not in raw
    # a reset is still recorded (just the fact, not the secret)
    assert any(e["action"] == "reset_access" for e in temp_audit.read_audit_log())


def test_resend_login_dm_password_never_logged(temp_friends_dir, temp_audit, mock_sr_cli, reset_rate_limit):
    ot = mock_sr_cli.ot
    # account already exists (so resend is the right, idempotent path — not a new provision)
    temp_friends_dir.record_account("3", "Dave", "dave")

    def sr(args):
        if args[:2] == ["users", "list"]:
            return True, "dave  active  ..."  # is_account_created sees it
        if args[:2] == ["users", "passwd"]:
            return True, "password updated"
        raise AssertionError(args)

    mock_sr_cli.sr_returns = sr
    out = ot.resend_login_dm("3", "dave")
    assert out["ok"] is True
    pw = out["login"]["password"]
    assert pw.startswith(_SR_PW_RE)
    raw = temp_audit._path().read_text()
    assert pw not in raw and _SR_PW_RE not in raw


def test_provision_verify_failed_keeps_login_but_does_not_claim_success(
    temp_friends_dir, temp_audit, mock_sr_cli, reset_rate_limit
):
    """Account made but unusable: NEVER claim success; name the gate; the password is kept for later
    delivery but still never logged."""
    ot = mock_sr_cli.ot
    temp_friends_dir.invite_friend("dave")

    def sr(args):
        if args[:2] == ["users", "create"]:
            return True, "created dave (u1)"
        if args[:2] == ["users", "verify"]:
            return False, json.dumps({"ok": False, "gate": "jellyseerr", "error": "201-but-null"})
        raise AssertionError(args)

    mock_sr_cli.sr_returns = sr
    out = ot.provision_access("4", "dave")
    assert out["ok"] is False and out["verified"] is False
    assert out["account_created"] is True and out["gate"] == "jellyseerr"
    # the login (with password) is kept so the DM can still go out once the gate is repaired...
    assert out["login"]["password"].startswith(_SR_PW_RE)
    # ...but it's STILL never in the audit log
    assert out["login"]["password"] not in temp_audit._path().read_text()


# ── admin gate on invites ──────────────────────────────────────────────────

def test_invite_admin_gate_holds(temp_friends_dir, temp_audit):
    fm = temp_friends_dir
    denied = fm.invite_friend_admin(STRANGER, "newguy")
    assert denied["ok"] is False and "admin" in denied["error"].lower()
    assert fm.is_invited("newguy")["invited"] is False
    # the admin can
    ok = fm.invite_friend_admin(ZACH, "newguy")
    assert ok["ok"] is True and fm.is_invited("newguy")["invited"] is True
    # both the denial and the approval are on the record
    actions = {e["action"] for e in temp_audit.read_audit_log()}
    assert "invite_denied" in actions and "invite_issued" in actions


def test_audit_read_is_admin_only(temp_friends_dir, temp_audit):
    temp_audit.log_audit("provision_access", "1", {"name": "dave"})
    assert temp_audit.audit_read_admin(STRANGER)["ok"] is False
    ok = temp_audit.audit_read_admin(ZACH)
    assert ok["ok"] is True
    assert any(e["action"] == "provision_access" for e in ok["entries"])


def test_audit_redacts_any_secret_handed_to_it(temp_audit):
    temp_audit.log_audit("oops", "1", {"name": "dave", "password": "sr-cafef00d", "token": "abc123"})
    raw = temp_audit._path().read_text()
    assert "sr-cafef00d" not in raw and "abc123" not in raw
    entry = temp_audit.read_audit_log()[-1]
    assert entry["details"]["password"] == "[redacted]"
    assert entry["details"]["token"] == "[redacted]"
    assert entry["details"]["name"] == "dave"


# ── rate-limit gate (the N+1 expensive call is blocked) ────────────────────

def test_provision_rate_limit_blocks_beyond_budget(temp_friends_dir, mock_sr_cli, reset_rate_limit):
    ot = mock_sr_cli.ot
    for name in ("dave", "erin", "finn", "gwen"):
        temp_friends_dir.invite_friend(name)

    def sr(args):
        if args[:2] == ["users", "create"]:
            return True, "created (u)"
        if args[:2] == ["users", "verify"]:
            return True, _verify_ok_payload()
        raise AssertionError(args)

    mock_sr_cli.sr_returns = sr
    # provision_access is 3/day per caller id
    for name in ("dave", "erin", "finn"):
        assert ot.provision_access("same-caller", name)["ok"] is True
    blocked = ot.provision_access("same-caller", "gwen")
    assert blocked["ok"] is False and blocked.get("rate_limited") is True
