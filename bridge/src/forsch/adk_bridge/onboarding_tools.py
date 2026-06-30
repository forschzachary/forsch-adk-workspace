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
        return {"ok": False, "error": f"'{name}' isn't approved yet — Zach must invite_friend('{name}') first."}
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


def reset_access(name: str) -> dict:
    """Reset a friend's Jellyfin password and return the new login to DM them privately."""
    username = name.strip().lower()
    password = _gen_password()
    ok, out = _sr(["users", "passwd", username, password])
    if not ok:
        return {"ok": False, "error": f"password reset failed: {out[:180]}"}
    return {
        "ok": True,
        "deliver_privately": True,
        "login": {"site": _jellyfin_url(), "username": username, "password": password},
    }
