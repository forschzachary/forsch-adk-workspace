"""Shared acquisition-pipeline diagnostics — the `sr` CLI checks that answer "where's my movie?".

These are the root-cause tools the ops lead uses (`pipeline_health` = `sr stack`, `diagnose_title`
= `sr diagnose`). They live here so BOTH personas can reuse them with no bot-to-bot coupling:
ops surfaces them to the team, and Huberto leans on them quietly to give a friend a real status.
Import direction is one-way (ops_tools and screening_room_tools import from here, never the reverse).
Binary overridable via SR_CLI.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

SR = os.environ.get("SR_CLI", str(Path.home() / "Dev" / "screening-room" / "scripts" / "sr"))


def _sr(args: list[str], timeout: float = 120) -> str:
    try:
        proc = subprocess.run([SR, *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return "(the sr CLI isn't reachable from here)"
    except subprocess.TimeoutExpired:
        return "(the screening room took too long to answer)"
    except Exception as exc:
        return f"(couldn't reach the screening room: {type(exc).__name__})"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and not out:
        return f"(sr failed, exit {proc.returncode}): {(proc.stderr or '').strip() or 'no output'}"
    return out or (proc.stderr or "").strip() or "(no output)"


def pipeline_health() -> str:
    """Deep acquisition-pipeline health — the whole download chain: Radarr/Sonarr, the Prowlarr
    indexers (incl. cooldowns / expired VIP), and the NZBGet usenet client + provider connections.
    Use this to answer 'is the stack or the NZB sources broken?' when downloads aren't landing."""
    return _sr(["stack"])


def diagnose_title(title_or_tmdb_id: str, media_type: str = "") -> str:
    """Find the ROOT CAUSE for why one specific title isn't downloading — maps it through
    Radarr/Sonarr -> indexers and reports the cause + fix: no release found (indexer cooldown),
    grabbed-but-failed, stuck in the download client, already acquired (stale Jellyseerr status),
    or never pushed to Radarr. Pass a tmdbId or a title; media_type is 'movie' or 'tv' (optional)."""
    args = ["diagnose", str(title_or_tmdb_id)]
    if media_type in ("movie", "tv"):
        args += ["--type", media_type]
    return _sr(args)
