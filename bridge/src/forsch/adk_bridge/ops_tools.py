"""Ops tools for the screening-room ops lead — shell-outs to the `sr` CLI + box checks.

Covers the operational metrics: account access (sr profiles audit), media-request success (the
Jellyseerr queue + retries), and storage health (disk where the media lives). Same `sr` CLI as
Huberto; binary overridable via SR_CLI.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# pipeline_health + diagnose_title live in the shared diagnostics module so Huberto can reuse them
# (re-exported here so make_ops_agent's tool list and any callers are unchanged).
from forsch.adk_bridge.audit_log import log_audit
from forsch.adk_bridge.ops_diagnostics import diagnose_title, pipeline_health
from forsch.adk_bridge.rate_limit import check_rate_limit

__all__ = [
    "account_audit",
    "media_queue",
    "queue_counts",
    "retry_failed",
    "pipeline_health",
    "diagnose_title",
    "storage_health",
]

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
    """Retry a failed media request by its id. Only after you've confirmed it actually failed.
    Rate-limited (ops is a shared internal identity, so the limit is keyed on the ops bucket) and
    audited so repeated re-pokes of the pipeline are capped and recorded."""
    rl = check_rate_limit("ops", "retry_failed")
    if not rl["ok"]:
        log_audit("retry_rate_limited", "ops", {"request_id": str(request_id), "retry_after": rl["retry_after"]})
        return rl["reason"]
    out = _sr(["queue", "retry", str(request_id), "--yes"])
    log_audit("retry_failed", "ops", {"request_id": str(request_id)})
    return out


def storage_health() -> str:
    """Disk usage where the media lives — surfaces low-space issues proactively."""
    try:
        proc = subprocess.run(["df", "-h"], capture_output=True, text=True, timeout=15)
    except Exception as exc:
        return f"(couldn't read disk usage: {type(exc).__name__})"
    return ((proc.stdout or proc.stderr or "").strip())[:1500]
