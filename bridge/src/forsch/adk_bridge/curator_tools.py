"""Curator tools for the SR-1 showrunner — thin shell-outs to the `sr` CLI.

The curator owns SR-1 programming: what's on now, the guide, the wall-clock schedule, the
bumps/playlist pools, and Discord events. Same `sr` CLI as Huberto/ops (it wraps the SR-1 channel
from the Supabase `programs` table + the TV programmer); binary overridable via the SR_CLI env var.

`tv_schedule` reuses the Phase 2 engine (`sr tv schedule <title> --at <time>`); the underlying bot
tool `schedule_on_sr1` (screening_room_tools) is now owned by this persona. Like that tool, the
write path is gated behind `dry_run=False` — never mutate the live SR-1 schedule unless explicitly
asked.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "tv_now",
    "tv_guide",
    "tv_reprogram",
    "tv_schedule",
    "bumps_add",
    "bumps_list",
    "bumps_remove",
    "playlist_add",
    "playlist_list",
    "playlist_remove",
    "events_list",
    "events_create",
    "events_cancel",
    "suggest_to_main",
]

SR = os.environ.get("SR_CLI", str(Path.home() / "Dev" / "screening-room" / "scripts" / "sr"))


def _run(args: list[str], timeout: float = 90) -> str:
    try:
        proc = subprocess.run([SR, *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return "(the sr CLI isn't reachable from here)"
    except subprocess.TimeoutExpired:
        return "(the screening room took too long to answer)"
    except Exception as exc:
        return f"(couldn't reach the screening room: {type(exc).__name__})"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return out or err or "(no output)"


# ── SR-1 channel ────────────────────────────────────────────────────────────
def tv_now() -> str:
    """What's playing on SR-1 right now and what's up next. Use this for anything about the channel."""
    return _run(["tv", "now"])


def tv_guide() -> str:
    """The SR-1 guide — the upcoming feature schedule with start times and the block each sits in."""
    return _run(["tv", "guide"])


def tv_reprogram() -> str:
    """Extend the SR-1 schedule forward (deterministic programmer). Use when the guide is running
    short of the horizon, NOT to insert a specific pick — that's tv_schedule."""
    return _run(["tv", "reprogram"])


def tv_schedule(title_or_tmdb_id: str, at_time: str, duration_min: str = "",
                dry_run: bool = True) -> str:
    """Put a title on SR-1 at a wall-clock time and reflow the rest of the schedule so there are no
    gaps or overlaps. `title_or_tmdb_id` is a library title or a Jellyfin item id; `at_time` is when
    to start it ("20:00", "+2h", or an absolute time); `duration_min` overrides the runtime in
    minutes if known (leave "" to auto-detect). The title must already be in the library.

    Defaults to dry_run=True (computes the reflow, writes nothing). Pass dry_run=False to actually
    place it on the air — that mutates the live SR-1 schedule, so only do it when explicitly asked.
    This is Gate B: putting a friend's pick on SR-1 for everyone."""
    args = ["tv", "schedule", str(title_or_tmdb_id), "--at", str(at_time)]
    if duration_min:
        args += ["--duration", str(duration_min)]
    if dry_run:
        args.append("--dry-run")
    return _run(args)


# ── bumps + playlists (the pool that fills between features) ─────────────────
def bumps_add(youtube_url: str, seconds: str = "") -> str:
    """Add a bump clip (a short interstitial) to the SR-1 bumps pool by its YouTube URL. `seconds`
    optionally caps its length."""
    args = ["bumps", "add", str(youtube_url)]
    if seconds:
        args += ["--seconds", str(seconds)]
    return _run(args)


def bumps_list() -> str:
    """List the SR-1 bumps pool — the interstitial clips that play between features."""
    return _run(["bumps", "list"])


def bumps_remove(bump_id: str) -> str:
    """Remove a bump clip from the SR-1 pool by its id. Confirm with bumps_list first; this is a
    deletion — never remove a clip unless asked."""
    return _run(["bumps", "rm", str(bump_id)])


def playlist_add(name: str, youtube_url: str, seconds: str = "") -> str:
    """Add a clip to a named SR-1 playlist (e.g. a themed block) by its YouTube URL. `seconds`
    optionally caps its length."""
    args = ["playlist", str(name), "add", str(youtube_url)]
    if seconds:
        args += ["--seconds", str(seconds)]
    return _run(args)


def playlist_list(name: str) -> str:
    """List the clips in a named SR-1 playlist."""
    return _run(["playlist", str(name), "list"])


def playlist_remove(name: str, clip_id: str) -> str:
    """Remove a clip from a named SR-1 playlist by its id. This is a deletion — confirm first and
    never remove a clip unless asked."""
    return _run(["playlist", str(name), "rm", str(clip_id)])


# ── Discord events (watch parties / premieres) ──────────────────────────────
def events_list() -> str:
    """List the screening room's Discord scheduled events — watch parties and premieres, with their
    times and RSVP counts."""
    return _run(["events", "list"])


def events_create(title: str, starts: str, minutes: str = "", channel: str = "") -> str:
    """Create a Discord scheduled event (a watch party / premiere). `title` is the event name;
    `starts` is the wall-clock start time; `minutes` optionally sets the length; `channel` optionally
    names the announcement channel. Never invent a title or time — only create what's been asked for."""
    args = ["events", "create", str(title), "--starts", str(starts)]
    if minutes:
        args += ["--minutes", str(minutes)]
    if channel:
        args += ["--channel", str(channel)]
    return _run(args)


def events_cancel(event_id: str) -> str:
    """Cancel a Discord scheduled event by its id. This changes the event's lifecycle — confirm the
    id with events_list first and only cancel when explicitly asked."""
    return _run(["events", "cancel", str(event_id), "--yes"])


# ── collaboration: loop Huberto in ──────────────────────────────────────────
def _suggestions_path() -> Path:
    ws = Path(os.environ.get("FORSCH_ADK_WORKSPACE", str(Path.home() / "Dev" / "forsch-adk-workspace")))
    directory = ws / "data" / "curator"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "suggestions.jsonl"


def suggest_to_main(idea: str) -> str:
    """Suggest a programming idea to Huberto (the friend-facing cat) — a pick to feature, a themed
    block, a watch party. The curator is autonomous but collaborative: it floats ideas rather than
    acting on friends' behalf unilaterally. The suggestion is appended to a local queue
    (data/curator/suggestions.jsonl) that Huberto/ops can drain; returns a confirmation to relay."""
    note = (idea or "").strip()
    if not note:
        return "(nothing to suggest — give me an idea first)"
    try:
        rec = {"idea": note, "at": datetime.now(timezone.utc).isoformat(), "status": "pending"}
        with open(_suggestions_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as exc:
        # Be honest about a failed write rather than claiming it was queued.
        return f"(could not queue suggestion for huberto: {exc})"
    return f"noted for huberto (queued): {note}"
