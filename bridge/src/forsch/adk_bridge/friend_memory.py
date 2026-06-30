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
            base += f" NOTE: this id is an ADMIN (Zach) — he runs the place; never quote credentials to him, and he approves new friends with invite_friend_admin(caller_discord_id='{discord_id}', name=...). he can also read the audit log via audit_read_admin(caller_discord_id='{discord_id}')."
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
    admin_line = (
        f" NOTE: this is an ADMIN (Zach) — never quote credentials to him; he approves new friends with "
        f"invite_friend_admin(caller_discord_id='{discord_id}', name=...) and can read the audit log via "
        f"audit_read_admin(caller_discord_id='{discord_id}')."
    ) if admin else ""
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

ONBOARDING_STAGES = (
    "new", "account", "toured", "request_fulfilled", "on_sr1", "member",
    # ── lifecycle (Phase 8) ──
    "suspended",  # access disabled but recoverable — the record + invite history are kept
    "archived",   # offboarded: record exported to _archive-<id>.json, then the active record is wiped
)


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


def _approve_invite(name: str) -> dict:
    """Append a name to the approved list (no auth — internal). Use invite_friend_admin from a tool."""
    invites = _load_invites()
    key = name.strip().lower()
    if key and key not in invites:
        invites.append(key)
        _invites_path().write_text(json.dumps(invites, indent=2))
    return {"ok": True, "invited": name, "pending": invites}


def invite_friend_admin(caller_discord_id: str, name: str) -> dict:
    """Approve a new person for onboarding — ADMIN ONLY. Pass the caller's own discord id; the gate is
    enforced HERE, not by the prompt: only an id in SR_ADMIN_DISCORD_IDS (Zach) may invite. A non-admin
    caller is denied and the attempt is audited. On approval, an account may later be provisioned for
    someone who gives this name."""
    from forsch.adk_bridge.audit_log import log_audit

    caller = str(caller_discord_id)
    if caller not in _admins():
        log_audit("invite_denied", caller, {"name": name, "reason": "not an admin"})
        return {"ok": False, "error": "only an admin (Zach) can invite a new friend."}
    out = _approve_invite(name)
    log_audit("invite_issued", caller, {"name": name.strip().lower()})
    return out


# Back-compat / internal primitive: the unauthenticated approve. NOT exposed as an agent tool — the
# agent must call invite_friend_admin (the gated entry point). Kept so internal callers/tests can seed
# the approved list directly.
invite_friend = _approve_invite


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
        try:
            from forsch.adk_bridge.audit_log import log_audit
            log_audit("invite_consumed", "", {"name": key})
        except Exception:
            pass


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


# ── lifecycle: suspend / offboard / activation (Phase 8) ───────────────────
# Closing the loop after "member": a member can be *suspended* (reversible — access is disabled but
# the record + invite history stay) and *offboarded* (archived to `_archive-<id>.json`, then the
# active record is wiped). These touch ONLY the local friend record; the actual Jellyfin disable is a
# separate, gated `sr users disable` (driven from onboarding_tools). `friend_activation_status` reads
# back where a friend stands without mutating anything — the basis for "did they ever log in?".

def set_stage(discord_id: str, stage: str) -> dict:
    """Set a friend's stage to any valid stage (incl. the Phase 8 lifecycle stages suspended/archived).
    Unlike advance_stage this is the lifecycle setter — same validation, clearer intent."""
    return advance_stage(discord_id, stage)


def friend_activation_status(discord_id: str) -> dict:
    """Where a friend stands, read-only: their stage, whether an account was created, whether the
    login DM landed, and any active suspension. Pure read — no side effects. (Jellyfin login/playback
    activity is a separate live check in screening_room_tools; this is the local-record view.)"""
    rec = _load(str(discord_id)) or {}
    return {
        "discord_id": str(discord_id),
        "name": rec.get("name"),
        "stage": rec.get("stage") or ("member" if rec.get("jellyfin_username") else "new"),
        "account_created": bool(rec.get("jellyfin_username")),
        "dm_delivered": bool(rec.get("dm_delivered")),
        "suspended": (rec.get("stage") == "suspended"),
        "archived": False,  # an archived friend has no active record — this only sees live ones
    }


def _archive_path(discord_id: str) -> Path:
    return _dir() / f"_archive-{discord_id}.json"


def archive_friend(discord_id: str, reason: str = "") -> dict:
    """Offboard a friend: export their record to `_archive-<id>.json` (preserved, not deleted) and
    then remove the active `<id>.json`. Reversible only by hand from the archive — the bot never
    auto-restores. Returns {ok, archived_to} or {ok:False} if there was no active record."""
    rec = _load(str(discord_id))
    if rec is None:
        return {"ok": False, "error": f"no active record for {discord_id} to archive."}
    rec["archived_at"] = _now_iso()
    rec["archive_reason"] = reason or ""
    rec["stage"] = "archived"
    archive = _archive_path(str(discord_id))
    tmp = archive.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2))
    tmp.replace(archive)
    # wipe the active record only after the archive is safely on disk
    _path(str(discord_id)).unlink(missing_ok=True)
    return {"ok": True, "archived_to": archive.name, "name": rec.get("name")}


def is_archived(discord_id: str) -> bool:
    """True if this friend has been offboarded (an `_archive-<id>.json` exists)."""
    return _archive_path(str(discord_id)).exists()


# ── watched requests (Phase 5: proactive notifications) ────────────────────
# When Huberto requests a movie for a friend, he records a *watch*: the friend's id, the title, and
# (optionally) the tmdb id. A background loop (request_watcher.py) polls each unnotified watch; when
# the title becomes watchable it DMs the friend once and flips `notified`. The flag persists in the
# friend's JSON record, so a restart never re-sends a DM. Each watch is one dict in a per-friend
# `watched_requests[]` array, keyed by `title` (lower-cased) so re-requesting the same title is a
# no-op rather than a duplicate watch.

WATCH_STALE_DAYS = 30  # auto-clear a never-fulfilled watch after this long


def _watch_key(title: str, tmdb_id: str = "") -> str:
    return (str(tmdb_id).strip() or title.strip().lower())


def add_watched_request(discord_id: str, tmdb_id: str, title: str) -> dict:
    """Remember that a friend is waiting on a requested title, so Huberto can DM them the moment it
    lands — no need for the friend to ask again. Call this right after request_movie. Idempotent:
    re-requesting the same title just refreshes the existing watch."""
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    watches = rec.setdefault("watched_requests", [])
    key = _watch_key(title, tmdb_id)
    for w in watches:
        if _watch_key(w.get("title", ""), w.get("tmdb_id", "")) == key:
            w["title"] = title
            if tmdb_id:
                w["tmdb_id"] = str(tmdb_id)
            w["notified"] = False  # they re-asked / re-requested — re-arm the watch
            _save(rec)
            return {"ok": True, "watching": title, "total": len(watches)}
    watches.append({
        "tmdb_id": str(tmdb_id) if tmdb_id else "",
        "title": title,
        "requested_at": _now_iso(),
        "notified": False,
    })
    _save(rec)
    return {"ok": True, "watching": title, "total": len(watches)}


def get_watched_requests(discord_id: str, include_notified: bool = False) -> list[dict]:
    """The titles a friend is waiting on. By default only the un-notified (still-pending) ones."""
    rec = _load(str(discord_id)) or {}
    watches = rec.get("watched_requests") or []
    if include_notified:
        return list(watches)
    return [w for w in watches if not w.get("notified")]


def mark_watched_request_notified(discord_id: str, title: str, tmdb_id: str = "") -> dict:
    """Flag a watch as notified once the 'it's ready' DM has gone out — so it's never sent twice."""
    rec = _load(str(discord_id)) or {"discord_id": str(discord_id), "facts": []}
    key = _watch_key(title, tmdb_id)
    hit = False
    for w in rec.get("watched_requests", []):
        if _watch_key(w.get("title", ""), w.get("tmdb_id", "")) == key:
            w["notified"] = True
            w["notified_at"] = _now_iso()
            hit = True
    if hit:
        _save(rec)
    return {"ok": hit, "notified": title}


def rearm_watched_request(discord_id: str, title: str, tmdb_id: str = "") -> dict:
    """Un-flag a watch's `notified` (e.g. the 'ready' DM failed to send, so retry next pass)."""
    rec = _load(str(discord_id))
    if not rec:
        return {"ok": False}
    key = _watch_key(title, tmdb_id)
    hit = False
    for w in rec.get("watched_requests", []):
        if _watch_key(w.get("title", ""), w.get("tmdb_id", "")) == key:
            w["notified"] = False
            w.pop("notified_at", None)
            hit = True
    if hit:
        _save(rec)
    return {"ok": hit}


def clear_watched_request(discord_id: str, title: str, tmdb_id: str = "") -> dict:
    """Drop a watch entirely (fulfilled, cancelled, or gone stale)."""
    rec = _load(str(discord_id))
    if not rec:
        return {"ok": False}
    key = _watch_key(title, tmdb_id)
    before = rec.get("watched_requests") or []
    after = [w for w in before if _watch_key(w.get("title", ""), w.get("tmdb_id", "")) != key]
    rec["watched_requests"] = after
    _save(rec)
    return {"ok": len(after) != len(before), "remaining": len(after)}


def all_friend_ids() -> list[str]:
    """Every known friend's discord id (skips `_`-prefixed bookkeeping files). For the watcher loop."""
    ids = []
    for path in _dir().glob("*.json"):
        if path.name.startswith("_"):
            continue
        ids.append(path.stem)
    return ids


def is_watch_stale(watch: dict, now_iso: str | None = None) -> bool:
    """True if a watch has waited past WATCH_STALE_DAYS without being fulfilled (safe to auto-clear)."""
    from datetime import datetime, timezone
    requested = watch.get("requested_at")
    if not requested:
        return False
    try:
        then = datetime.fromisoformat(requested)
    except Exception:
        return False
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - then).days >= WATCH_STALE_DAYS
