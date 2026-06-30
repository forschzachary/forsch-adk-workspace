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
    rec = _load(discord_id)
    if rec is None:
        return (
            f"[you're talking to a discord user you don't know yet (id {discord_id}). be warm, find "
            f"out their name naturally, and once you know it call onboard_friend(discord_id='{discord_id}', "
            f"name=...). don't interrogate — just chat and pick it up.]"
        )
    name = rec.get("name") or "a friend"
    profile = rec.get("jellyfin_profile") or ""
    facts = rec.get("facts") or []
    fact_line = ("you remember: " + "; ".join(facts)) if facts else "no notes on them yet."
    prof = (
        f" their screening-room profile is '{profile}', so attribute their movie requests to that "
        f"(requested_for='{profile}')."
        if profile else ""
    )
    return (
        f"[you're talking to {name} (discord id {discord_id}). {fact_line}{prof} greet them like you "
        f"know them; jot anything new worth remembering with remember_about_friend(discord_id='{discord_id}', fact=...).]"
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
