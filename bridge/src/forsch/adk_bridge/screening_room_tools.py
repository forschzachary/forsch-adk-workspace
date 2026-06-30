"""Screening Room tools for Huberto — thin shell-outs to the `sr` CLI.

The `sr` CLI (~/Dev/screening-room/scripts/sr) wraps the whole stack — Jellyfin / Jellyseerr /
Radarr / Sonarr + the SR-1 channel — and was built for an agent to drive by shelling out. These
give Huberto real powers: see what's on SR-1, search the library, and request (download) a movie
into the screening room. Override the binary with the SR_CLI env var.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

# Shared ops diagnostics — Huberto reuses these to answer "where's my movie?" with a real root
# cause, without exposing that ops' logic is doing the scratching. One-way import.
from forsch.adk_bridge.audit_log import log_audit
from forsch.adk_bridge.ops_diagnostics import diagnose_title, pipeline_health
from forsch.adk_bridge.rate_limit import check_rate_limit

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


def whats_on_sr1() -> str:
    """What's playing on SR-1 right now and what's up next. Use this for anything about the channel."""
    return _run(["tv", "now"])


def search_library(title: str) -> str:
    """Search the Screening Room for a title. Returns matches with tmdbId, year, and status —
    'available' means it's already here and ready to watch; 'not in library' means you'd need to
    grab it. Always use this before telling a friend whether something is here or offering to add it."""
    return _run(["search", title])


def request_movie(tmdb_id: str, requested_for: str = "forschfamily", requester_discord_id: str = "") -> str:
    """Add (download) a movie to the Screening Room library by its tmdbId. Call this ONLY after the
    friend has said yes. requested_for is the profile it's attributed to (default: the family).
    Pass requester_discord_id (the friend's discord id) so the request is rate-limited + audited per
    person; it's keyed on that id, falling back to requested_for when absent."""
    rl_key = str(requester_discord_id) or requested_for
    rl = check_rate_limit(rl_key, "request_movie")
    if not rl["ok"]:
        log_audit("request_rate_limited", rl_key, {"tmdb_id": str(tmdb_id), "retry_after": rl["retry_after"]})
        return rl["reason"]
    out = _run(["request", str(tmdb_id), "--type", "movie", "--as", requested_for])
    log_audit("request_movie", rl_key, {"tmdb_id": str(tmdb_id), "requested_for": requested_for})
    return out


def check_my_request(title: str) -> str:
    """Check the REAL status of a friend's request — 'where's my movie?' / 'did it work?'. First
    sees if it's already in the library (then it's ready to watch); otherwise finds the actual
    root cause (downloading, indexer cooldown, grabbed-but-failed, stuck in the client) plus the
    overall pipeline health, so you can give a friend honest facts and a rough when. Pass the title
    (or tmdbId). Returns a status you can relay in your own voice — never mention how it's checked."""
    lib = search_library(title)
    if "available" in lib.lower():
        return lib  # already here — short-circuit
    stack = pipeline_health()  # is the stack broken? (cooldowns, providers)
    diag = diagnose_title(title)  # per-title root cause
    return f"{diag}\n\nPipeline status:\n{stack}"


def schedule_on_sr1(title_or_tmdb_id: str, at_time: str, dry_run: bool = True) -> str:
    """Put a title on SR-1 (the always-on channel) at a wall-clock time and reflow the rest of the
    schedule so there are no gaps. `title_or_tmdb_id` is a library title or a Jellyfin item id;
    `at_time` is when to start it ("20:00", "+2h", or an absolute time). The title must already be
    in the library (use search_library / request_movie first).

    Defaults to dry_run=True (computes the reflow, writes nothing). Pass dry_run=False to actually
    place it on the air — that mutates the live SR-1 schedule, so only do it when explicitly asked.

    SR-1 programming is OWNED by the curator persona (curator_tools.tv_schedule wraps this same
    engine); Huberto uses this only to put a friend's own badge pick on the air or delegates to the
    curator. The Phase 2 `sr tv schedule` engine backs both."""
    args = ["tv", "schedule", str(title_or_tmdb_id), "--at", str(at_time)]
    if dry_run:
        args.append("--dry-run")
    out = _run(args)
    if _is_schedule_conflict(out):
        # The slot is taken (the engine's unique-index / horizon rejection, surfaced as a 409). Don't
        # silently drop the second pick — tell the caller it's a conflict so Huberto/curator can give
        # the first requester the slot and offer this one an open time.
        return (
            f"SLOT CONFLICT: that SR-1 time is already taken — {out.strip()}\n"
            f"don't silently defer: the first pick keeps '{at_time}'; offer this one another open slot "
            f"(check `sr tv guide` for gaps, or try a different --at)."
        )
    if not dry_run and "fail" not in out.lower() and "error" not in out.lower():
        # a real mutation of the live SR-1 schedule — record it (the title + time, never a secret).
        log_audit("sr1_scheduled", "", {"title": str(title_or_tmdb_id), "at": str(at_time)})
    return out


# A schedule attempt that lost the slot: the route returns 409 and `sr tv schedule` dies with that
# status, or the reflow engine's plain-text reasons (taken / horizon / race). Detected so the caller
# can arbitrate instead of dropping the second pick.
_CONFLICT_MARKERS = ("409", "already taken", "lost the race", "slot already", "beyond the")


def _is_schedule_conflict(out: str) -> bool:
    low = (out or "").lower()
    return any(m in low for m in _CONFLICT_MARKERS)


# ── activation + branding (Phase 9) ────────────────────────────────────────

def jellyfin_activation_status(name: str) -> dict:
    """Did a friend actually log in and watch anything? Read-only — shells `sr users info <name>`,
    which reports Jellyfin's last-active date + a watched (played) count. Returns
    {ok, has_logged_in, last_active, watched_count} (or {ok:False, error}). Use it to know whether a
    new member ever signed in, so you can gently nudge them if they haven't — never to claim more than
    the data shows. NOTE: last-active is last login/activity, not strictly playback, so 'logged in but
    watched 0' is a real, normal in-between state."""
    out = _run(["users", "info", name.strip().lower()])
    try:
        # `sr users info` prints a single JSON line; take the last brace-leading line.
        last = [ln for ln in out.splitlines() if ln.strip().startswith("{")]
        data = json.loads(last[-1]) if last else {}
    except Exception:
        data = {}
    if not data:
        return {"ok": False, "error": f"couldn't read activation for '{name}': {out[:160]}"}
    return data


def announce_sr1_pick(title: str, friend_name: str, year: str = "", runtime: str = "") -> str:
    """Render the SPOILER-SAFE 'now showing on SR-1' announcement for a friend's own pick — text only.
    Returns the filled message (mood/vibe only, never plot). `title` + `friend_name` are required;
    `year` and `runtime` are optional and omitted cleanly when blank. Post the returned text in your
    own warm voice. Use this rather than hand-typing the copy so the template stays consistent. See
    read_knowledge('sr1-announcement-template') for the format + the no-spoiler rules."""
    title = (title or "").strip()
    friend = (friend_name or "").strip() or "a friend"
    year_paren = f" ({year.strip()})" if (year or "").strip() else ""
    runtime_suffix = f" · {runtime.strip()}" if (runtime or "").strip() else ""
    return (
        f"🎬 now showing on SR-1: **{title}**{year_paren}{runtime_suffix}\n"
        f"{friend}'s pick — pull up a seat, everyone."
    )
