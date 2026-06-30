"""Onboarding action tools — provisioning real Jellyfin access for invited friends.

These shell out to the `sr` CLI (sr users create / passwd) and persist state via friend_memory.
Hard rule: provision_access REFUSES anyone not approved via invite_friend. Passwords are generated
here and returned to the agent ONLY so it can DM them privately to the friend — never logged, never
shown to Zach, never posted in a channel.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from pathlib import Path

from forsch.adk_bridge import friend_memory as fm
from forsch.adk_bridge.audit_log import log_audit
from forsch.adk_bridge.rate_limit import check_rate_limit

SR = os.environ.get("SR_CLI", str(Path.home() / "Dev" / "screening-room" / "scripts" / "sr"))


def _sr(args: list[str], timeout: float = 120) -> tuple[bool, str]:
    try:
        proc = subprocess.run([SR, *args], capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return False, f"(couldn't reach the screening room: {type(exc).__name__})"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode == 0, (out or err or "(no output)")


def _jellyfin_url() -> str:
    try:
        cfg = json.loads((Path.home() / ".config/screening-room/cli.json").read_text())
        return (cfg.get("JELLYFIN_URL") or "").rstrip("/")
    except Exception:
        return ""


def _gen_password() -> str:
    return "sr-" + secrets.token_hex(4)  # e.g. sr-9f3a1c84 — strong + typeable


def verify_guest_provisioning(discord_id: str, name: str, password: str) -> dict:
    """Prove a freshly-provisioned friend can actually use the screening room — they can log in,
    their isolated library answers for THEIR token, and Jellyseerr is linked so they can request.
    Shells `sr users verify`. Returns {ok, gate, ...}; on failure `gate` is the exact thing that's
    broken (auth / library / jellyseerr) so Huberto can report precisely instead of claiming success."""
    ok, out = _sr(["users", "verify", name.strip().lower(), password])
    try:
        # `sr users verify` prints a single JSON line (last line of stdout); parse it.
        last = [ln for ln in out.splitlines() if ln.strip().startswith("{")]
        data = json.loads(last[-1]) if last else {}
    except Exception:
        data = {}
    if not data:
        return {"ok": False, "gate": "unknown", "error": f"verify produced no result: {out[:160]}"}
    return data


def provision_access(discord_id: str, name: str) -> dict:
    """Create a real Jellyfin account for an INVITED friend, VERIFY they can actually use it, then
    return their login to DM them. Refuses unless the name was approved with invite_friend. Idempotent:
    if the account already exists, returns already_exists (use reset_access for a fresh password
    rather than making a duplicate). DM the returned login to the friend privately (site, username,
    password) — never post it in a channel or back to Zach. `verified` is only true when the friend
    can log in, see their library, and request — don't tell them "you're set" unless it's true."""
    if not fm.is_invited(name)["invited"]:
        return {"ok": False, "error": f"'{name}' isn't approved yet — Zach must invite the friend first."}
    rl = check_rate_limit(str(discord_id), "provision_access")
    if not rl["ok"]:
        log_audit("provision_rate_limited", str(discord_id), {"name": name.strip().lower(), "retry_after": rl["retry_after"]})
        return {"ok": False, "rate_limited": True, "error": rl["reason"]}
    username = name.strip().lower()
    if fm.has_account(name):
        # Don't create a second account — steer to reset_access for a fresh password.
        return {
            "ok": False,
            "already_exists": True,
            "username": username,
            "error": f"'{username}' already has an account — use reset_access('{name}') for a fresh password instead of provisioning again.",
        }
    password = _gen_password()
    ok, out = _sr(["users", "create", username, "--password", password])
    if not ok:
        return {"ok": False, "error": f"account creation failed: {out[:180]}"}
    fm.record_account(str(discord_id), name, username)
    fm.consume_invite(name)

    # Account exists now — record it in the audit log (NEVER the password) before we verify.
    log_audit("provision_access", str(discord_id), {"name": name.strip().lower(), "username": username})

    # Managed outcome: don't return success until we've PROVEN the friend can use it.
    check = verify_guest_provisioning(str(discord_id), name, password)
    if not check.get("ok"):
        return {
            "ok": False,
            "account_created": True,
            "verified": False,
            "gate": check.get("gate"),
            "error": (
                f"account made but verification failed at the '{check.get('gate')}' gate: "
                f"{check.get('error', '')}. Run `sr diagnose provision {username} --repair` to fix it "
                f"(or check_my_request); do NOT tell the friend they're set yet."
            ),
            # password kept so the DM can still go out once the gate is repaired — never log it.
            "login": {"site": _jellyfin_url(), "username": username, "password": password},
        }
    return {
        "ok": True,
        "verified": True,
        "deliver_privately": True,
        "login": {
            "site": _jellyfin_url(),
            "username": username,
            "password": password,
            "how": "open the site, sign in with the username + password; if it asks for a server, paste the same URL.",
        },
    }


def get_access(name: str) -> dict:
    """Look up an existing friend's login basics (site + username). Passwords can't be read back —
    if they forgot theirs, use reset_access."""
    return {
        "site": _jellyfin_url(),
        "username": name.strip().lower(),
        "note": "passwords can't be retrieved; use reset_access if they forgot it.",
    }


def reset_access(name: str, caller_discord_id: str = "") -> dict:
    """Reset a friend's Jellyfin password and return the new login to DM them privately. Pass the
    caller's discord id (the admin/friend asking) so the reset is rate-limited + audited per user;
    it's keyed on that id, falling back to the friend's username when absent."""
    username = name.strip().lower()
    rl_key = str(caller_discord_id) or username
    rl = check_rate_limit(rl_key, "reset_access")
    if not rl["ok"]:
        log_audit("reset_rate_limited", rl_key, {"name": username, "retry_after": rl["retry_after"]})
        return {"ok": False, "rate_limited": True, "error": rl["reason"]}
    password = _gen_password()
    ok, out = _sr(["users", "passwd", username, password])
    if not ok:
        return {"ok": False, "error": f"password reset failed: {out[:180]}"}
    # audit the reset — NEVER the new password (only that a reset happened).
    log_audit("reset_access", rl_key, {"name": username})
    return {
        "ok": True,
        "deliver_privately": True,
        "login": {"site": _jellyfin_url(), "username": username, "password": password},
    }


# ── lifecycle: recovery + suspend/offboard (Phase 8) ───────────────────────
# Closes the loop after a friend is a member: recover an account whose login DM failed (idempotently,
# no duplicate account), and reversibly suspend / archive a friend. The Jellyfin disable is the gated
# `sr users disable` (reversible) — we NEVER hard-delete from a tool; offboarding archives the local
# record first. Passwords only ever ride in a DM payload, never in a log.

def is_account_created(name: str) -> bool:
    """True if a Jellyfin account for this name already exists on the live server (idempotency check
    via `sr users list`). Used by recovery so we never create a duplicate. Falls back to the local
    friend record if the CLI can't be reached."""
    username = name.strip().lower()
    ok, out = _sr(["users", "list"])
    if ok:
        for line in out.splitlines():
            # `sr users list` is a padded table; the first column is the name.
            first = line.strip().split()
            if first and first[0].strip().lower() == username:
                return True
        return False
    # CLI unreachable — fall back to what we already recorded locally.
    return fm.has_account(name)


def resend_login_dm(discord_id: str, name: str) -> dict:
    """Recover an account whose login DM never landed: mint a FRESH password (`sr users passwd`) and
    return the login to DM the friend again. Idempotent by design — it resets the existing account
    rather than provisioning a new one, so re-running it can't create a duplicate. If no account
    exists yet, it says so (provision first). The password rides only in this return value, for the
    DM — never logged."""
    username = name.strip().lower()
    if not is_account_created(name):
        return {
            "ok": False,
            "error": f"no account for '{username}' yet — provision_access(discord_id, name) first; nothing to resend.",
        }
    rl_key = str(discord_id) or username
    rl = check_rate_limit(rl_key, "reset_access")
    if not rl["ok"]:
        log_audit("resend_login_rate_limited", rl_key, {"name": username, "retry_after": rl["retry_after"]})
        return {"ok": False, "rate_limited": True, "error": rl["reason"]}
    password = _gen_password()
    ok, out = _sr(["users", "passwd", username, password])
    if not ok:
        return {"ok": False, "error": f"could not refresh the login: {out[:180]}"}
    # the DM had failed before; clear the stale pending entry and re-queue is the bot's job — here we
    # just record the recovery (never the password) and hand back the fresh login to deliver.
    log_audit("resend_login_dm", rl_key, {"name": username})
    return {
        "ok": True,
        "deliver_privately": True,
        "login": {"site": _jellyfin_url(), "username": username, "password": password},
    }


def suspend_friend_account(name: str, discord_id: str = "", reason: str = "") -> dict:
    """Reversibly suspend a friend's access: disable their Jellyfin login (`sr users disable`, NOT a
    delete) and mark their record `suspended`. The account, library and Jellyseerr link are untouched,
    so resume_friend_account restores everything. Pass discord_id to also move the local stage. Audited;
    no secret involved."""
    username = name.strip().lower()
    ok, out = _sr(["users", "disable", username])
    if not ok:
        return {"ok": False, "error": f"could not suspend '{username}': {out[:180]}"}
    if discord_id:
        fm.set_stage(str(discord_id), "suspended")
    log_audit("suspend_account", str(discord_id), {"name": username, "reason": reason or ""})
    return {"ok": True, "suspended": username, "reversible": True}


def resume_friend_account(name: str, discord_id: str = "") -> dict:
    """Undo a suspension: re-enable the Jellyfin login (`sr users enable`) and restore the friend's
    stage to 'member'. The reverse of suspend_friend_account."""
    username = name.strip().lower()
    ok, out = _sr(["users", "enable", username])
    if not ok:
        return {"ok": False, "error": f"could not resume '{username}': {out[:180]}"}
    if discord_id:
        fm.set_stage(str(discord_id), "member")
    log_audit("resume_account", str(discord_id), {"name": username})
    return {"ok": True, "resumed": username}


def offboard_friend(discord_id: str, name: str = "", reason: str = "", archive: bool = True) -> dict:
    """Offboard a friend (they're leaving the club). SAFE BY DEFAULT: archive=True disables their
    Jellyfin access (reversible) and archives the local record — it does NOT hard-delete the Jellyfin
    account (that's irreversible and is left to a human running `sr users delete --yes` deliberately).
    Pass archive=False only to skip the local archive (rare). Returns the archive location. Audited."""
    username = (name or "").strip().lower()
    # 1) disable Jellyfin access if we know the username (reversible — never delete from a tool).
    disabled = None
    if username:
        ok, out = _sr(["users", "disable", username])
        disabled = ok
        if not ok:
            # don't abort the offboard just because the disable hiccuped — record it and continue.
            log_audit("offboard_disable_failed", str(discord_id), {"name": username, "detail": out[:120]})
    # 2) archive the local record (export then wipe) unless explicitly told not to.
    archived = None
    if archive:
        res = fm.archive_friend(str(discord_id), reason or "offboarded")
        archived = res.get("archived_to") if res.get("ok") else None
    log_audit("offboard_friend", str(discord_id), {"name": username, "archived": bool(archived), "disabled": bool(disabled)})
    return {
        "ok": True,
        "offboarded": username or str(discord_id),
        "jellyfin_disabled": disabled,
        "archived_to": archived,
        "note": "Jellyfin account disabled (reversible), record archived — NOT hard-deleted. Use `sr users delete --yes` by hand to remove the account for good.",
    }
