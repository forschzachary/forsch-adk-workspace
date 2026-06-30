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


def provision_access(discord_id: str, name: str) -> dict:
    """Create a real Jellyfin account for an INVITED friend and return their login to DM them.
    Refuses unless the name was approved with invite_friend. DM the returned login to the friend
    privately (site, username, password) — never post it in a channel or back to Zach."""
    if not fm.is_invited(name)["invited"]:
        return {"ok": False, "error": f"'{name}' isn't approved yet — Zach must invite_friend('{name}') first."}
    username = name.strip().lower()
    password = _gen_password()
    ok, out = _sr(["users", "create", username, "--password", password])
    if not ok:
        return {"ok": False, "error": f"account creation failed: {out[:180]}"}
    fm.record_account(str(discord_id), name, username)
    fm.consume_invite(name)
    return {
        "ok": True,
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
