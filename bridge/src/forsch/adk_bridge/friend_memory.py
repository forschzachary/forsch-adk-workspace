"""Per-friend identity + memory for Huberto — who he's talking to, and what he remembers.

A small local store keyed by Discord user id: ``data/friends/<discord_id>.json`` holding the
friend's name, their ScreeningRoom (Jellyfin) profile for request attribution, and remembered
facts. ``friend_context()`` builds the line the Discord bot injects before each turn, so Huberto
greets known friends by name and recalls them; an unknown user triggers gentle onboarding.

(v1: the tools take the discord id as an argument, supplied via the injected context. A later pass
can derive it from the ADK ToolContext so the model never has to copy it.)
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _dir() -> Path:
    ws = Path(os.environ.get("FORSCH_ADK_WORKSPACE", str(Path.home() / "Dev" / "forsch-adk-workspace")))
    directory = ws / "data" / "friends"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _path(discord_id: str) -> Path:
    return _dir() / f"{discord_id}.json"


def _load(discord_id: str) -> dict | None:
    path = _path(discord_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _save(rec: dict) -> None:
    path = _path(rec["discord_id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2))
    tmp.replace(path)


def friend_context(discord_id: str) -> str:
    """The system line the bot injects before a turn: who Huberto is talking to + what he recalls."""
    discord_id = str(discord_id)
    admin = discord_id in _admins()
    rec = _load(discord_id)
    if rec is None:
        base = (
            f"you're talking to a discord user you don't know yet (id {discord_id}). be warm, find "
            f"out their name naturally, and once you know it call onboard_friend(discord_id='{discord_id}', "
            f"name=...). if they want to JOIN the screening room, check is_invited(name) once you know "
            f"it — only provision an account for an INVITED friend (read_knowledge('onboarding-playbook'))."
        )
        if admin:
            base += " NOTE: this id is an ADMIN (Zach) — he runs the place; never quote credentials to him, and he approves new friends with invite_friend(name)."
        return f"[{base}]"
    name = rec.get("name") or "a friend"
    profile = rec.get("jellyfin_profile") or ""
    facts = rec.get("facts") or []
    stage = rec.get("stage") or ("member" if rec.get("jellyfin_username") else "new")
    fact_line = ("you remember: " + "; ".join(facts)) if facts else "no notes on them yet."
    prof = (
        f" their screening-room profile is '{profile}', so attribute their movie requests to that "
        f"(requested_for='{profile}')."
        if profile else ""
    )
    stage_line = "" if stage == "member" else f" onboarding stage: {stage} — nudge the next step (read_knowledge('onboarding-playbook'))."
    admin_line = " NOTE: this is an ADMIN (Zach) — never quote credentials to him; he approves new friends with invite_friend(name)." if admin else ""
    return (
        f"[you're talking to {name} (discord id {discord_id}). {fact_line}{prof}{stage_line}{admin_line} "
        f"greet them like you know them; jot anything new with remember_about_friend(discord_id='{discord_id}', fact=...).]"
    )


# ── tools for Huberto ──────────────────────────────────────────────────────

def onboard_friend(discord_id: str, name: str, jellyfin_profile: str = "") -> dict:
    """Register/link a friend by their Discord id: their name and (optional) ScreeningRoom profile.
    Call this once you learn who a new person is, so you remember them next time."""
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    rec["name"] = name
    if jellyfin_profile:
        rec["jellyfin_profile"] = jellyfin_profile
    _save(rec)
    return {"ok": True, "name": name, "profile": jellyfin_profile or None}


def remember_about_friend(discord_id: str, fact: str) -> dict:
    """Remember a fact about a friend (a taste, a favorite, something they said) for next time."""
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    facts = rec.setdefault("facts", [])
    if fact not in facts:
        facts.append(fact)
    _save(rec)
    return {"ok": True, "remembered": fact, "total_facts": len(facts)}


# ── onboarding stages + invite gate ────────────────────────────────────────

ONBOARDING_STAGES = ("new", "account", "toured", "request_fulfilled", "on_sr1", "member")


def _admins() -> set[str]:
    return {s.strip() for s in os.environ.get("SR_ADMIN_DISCORD_IDS", "").split(",") if s.strip()}


def advance_stage(discord_id: str, stage: str) -> dict:
    """Advance a friend's onboarding stage as they pass each gate. Order: new -> account -> toured ->
    request_fulfilled -> on_sr1 -> member."""
    if stage not in ONBOARDING_STAGES:
        return {"ok": False, "error": f"unknown stage; use one of: {', '.join(ONBOARDING_STAGES)}"}
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    rec["stage"] = stage
    _save(rec)
    return {"ok": True, "stage": stage}


def onboarding_status(discord_id: str) -> dict:
    """Where a friend is in onboarding — their stage + whether they already have an account."""
    rec = _load(str(discord_id)) or {}
    return {
        "stage": rec.get("stage") or ("member" if rec.get("jellyfin_username") else "new"),
        "has_account": bool(rec.get("jellyfin_username")),
        "name": rec.get("name"),
    }


def _invites_path() -> Path:
    return _dir() / "_invites.json"


def _load_invites() -> list[str]:
    path = _invites_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def invite_friend(name: str) -> dict:
    """Approve a new person for onboarding — ONLY call when the admin (Zach) approves them. After
    this, an account may be provisioned for someone who gives this name."""
    invites = _load_invites()
    key = name.strip().lower()
    if key and key not in invites:
        invites.append(key)
        _invites_path().write_text(json.dumps(invites, indent=2))
    return {"ok": True, "invited": name, "pending": invites}


def is_invited(name: str) -> dict:
    """Check whether a name was approved for onboarding — the gate before provisioning an account."""
    return {"invited": name.strip().lower() in _load_invites(), "name": name}


def list_invites() -> dict:
    """List names approved for onboarding but not yet given an account."""
    return {"invites": _load_invites()}


def consume_invite(name: str) -> None:
    """Remove a name from the approved list once their account is created (one-time invite)."""
    invites = _load_invites()
    key = name.strip().lower()
    if key in invites:
        invites.remove(key)
        _invites_path().write_text(json.dumps(invites, indent=2))


def record_account(discord_id: str, name: str, jellyfin_username: str, jellyfin_profile: str = "") -> None:
    """Persist that a friend now has a Jellyfin account (advances stage to 'account')."""
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    rec["name"] = name
    rec["jellyfin_username"] = jellyfin_username
    rec["jellyfin_profile"] = jellyfin_profile or jellyfin_username
    rec["stage"] = "account"
    _save(rec)


def has_account(name: str) -> bool:
    """True if any friend record already has a Jellyfin account under this username (idempotency)."""
    username = name.strip().lower()
    for path in _dir().glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            rec = json.loads(path.read_text())
        except Exception:
            continue
        if (rec.get("jellyfin_username") or "").strip().lower() == username:
            return True
    return False


# ── DM delivery tracking (Phase 4 + 5) ─────────────────────────────────────
# When the credential DM can't be delivered (Discord 403 — the friend hasn't accepted the bot /
# shares no guild), we don't lose the login: we queue it as a pending_dm and surface the true state
# to Zach ("media ready + login verified, comms route waiting"). The dispatch/retry loop is Phase 5.
# pending_dm never stores the password in Zach-facing output — it lives only in the friend's local
# record so the bot can deliver it automatically once the route opens.

def queue_pending_dm(discord_id: str, content: str) -> dict:
    """Queue a DM that couldn't be delivered (Discord 403) so it can be sent automatically later."""
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    pending = rec.get("pending_dm") or {}
    rec["pending_dm"] = {
        "content": content,
        "queued_at": pending.get("queued_at") or _now_iso(),
        "attempts": int(pending.get("attempts", 0)),
    }
    rec["dm_delivered"] = False
    _save(rec)
    return {"ok": True, "queued": True}


def get_pending_dm(discord_id: str) -> dict | None:
    """The queued-but-undelivered DM for a friend, if any (for the Phase 5 dispatch loop)."""
    rec = _load(str(discord_id))
    return (rec or {}).get("pending_dm")


def mark_dm_delivered(discord_id: str) -> dict:
    """Record that the friend's DM landed; clears any pending_dm queue entry."""
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    rec["dm_delivered"] = True
    rec.pop("pending_dm", None)
    _save(rec)
    return {"ok": True, "dm_delivered": True}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
