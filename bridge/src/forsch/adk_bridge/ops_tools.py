"""Ops tools for the screening-room ops lead — shell-outs to the `sr` CLI + box checks.

Covers the operational metrics: account access (sr profiles audit), media-request success (the
Jellyseerr queue + retries), and storage health (disk where the media lives). Same `sr` CLI as
Huberto; binary overridable via SR_CLI.
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
    return (proc.stdout or "").strip() or (proc.stderr or "").strip() or "(no output)"


def account_audit() -> str:
    """Audit accounts — who can get in, missing Jellyseerr/Jellyfin links, quotas, folder scoping.
    Use this for any 'can people access their accounts' question."""
    return _sr(["profiles", "audit"])


def media_queue(status: str = "active") -> str:
    """The Jellyseerr request pipeline (the media-request success view). status: active | all |
    pending | approved. Shows what's requested / downloading / available, plus failures."""
    status = status if status in ("active", "all", "pending", "approved") else "active"
    return _sr(["queue", status])


def queue_counts() -> str:
    """A quick summary of the request queue — counts by stage. Good for a fast health glance."""
    return _sr(["queue", "counts"])


def retry_failed(request_id: str) -> str:
    """Retry a failed media request by its id. Only after you've confirmed it actually failed."""
    return _sr(["queue", "retry", str(request_id), "--yes"])


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


def storage_health() -> str:
    """Disk usage where the media lives — surfaces low-space issues proactively."""
    try:
        proc = subprocess.run(["df", "-h"], capture_output=True, text=True, timeout=15)
    except Exception as exc:
        return f"(couldn't read disk usage: {type(exc).__name__})"
    return ((proc.stdout or proc.stderr or "").strip())[:1500]
