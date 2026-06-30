"""Screening Room tools for Huberto — thin shell-outs to the `sr` CLI.

The `sr` CLI (~/Dev/screening-room/scripts/sr) wraps the whole stack — Jellyfin / Jellyseerr /
Radarr / Sonarr + the SR-1 channel — and was built for an agent to drive by shelling out. These
give Huberto real powers: see what's on SR-1, search the library, and request (download) a movie
into the screening room. Override the binary with the SR_CLI env var.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

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


def request_movie(tmdb_id: str, requested_for: str = "forschfamily") -> str:
    """Add (download) a movie to the Screening Room library by its tmdbId. Call this ONLY after the
    friend has said yes. requested_for is the profile it's attributed to (default: the family)."""
    return _run(["request", str(tmdb_id), "--type", "movie", "--as", requested_for])


def schedule_on_sr1(title_or_tmdb_id: str, at_time: str, dry_run: bool = True) -> str:
    """Put a title on SR-1 (the always-on channel) at a wall-clock time and reflow the rest of the
    schedule so there are no gaps. `title_or_tmdb_id` is a library title or a Jellyfin item id;
    `at_time` is when to start it ("20:00", "+2h", or an absolute time). The title must already be
    in the library (use search_library / request_movie first).

    Defaults to dry_run=True (computes the reflow, writes nothing). Pass dry_run=False to actually
    place it on the air — that mutates the live SR-1 schedule, so only do it when explicitly asked."""
    args = ["tv", "schedule", str(title_or_tmdb_id), "--at", str(at_time)]
    if dry_run:
        args.append("--dry-run")
    return _run(args)
