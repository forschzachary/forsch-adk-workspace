"""Append-only audit log of consequential ScreeningRoom actions — the receipt Zach can read back.

Every action that creates/changes real state (an account provisioned, a password reset, a movie
requested, a failed request retried, an invite issued/consumed, a title scheduled on SR-1) lands ONE
JSON line in ``data/audit.jsonl``. The log is append-only: we open in ``"a"`` and never rewrite, so a
record can't be silently edited away.

Hard rule (mirrors onboarding_tools): a password/token NEVER enters the log. Callers pass only a
``details`` dict of non-secret facts (a username, a tmdb id, a reason) — if a key looks secret it's
redacted defensively here too, so a careless caller can't leak one.

Reading it back is admin-gated: ``audit_read_admin(caller_discord_id)`` returns the recent lines only
for an id in ``SR_ADMIN_DISCORD_IDS`` (Zach). A non-admin gets a denial — and that denial is itself
audited, so an attempt to read the log leaves a trace.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

_LOG = logging.getLogger("adk_bridge.audit_log")

# keys we never persist, even if a caller hands them to us by mistake
_SECRET_KEYS = {"password", "passwd", "pass", "token", "secret", "api_key", "apikey", "key"}


def _dir() -> Path:
    ws = Path(os.environ.get("FORSCH_ADK_WORKSPACE", str(Path.home() / "Dev" / "forsch-adk-workspace")))
    directory = ws / "data"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _path() -> Path:
    return _dir() / "audit.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact(details: dict | None) -> dict:
    """Drop any obviously-secret keys so a careless caller can't leak a credential into the log."""
    if not details:
        return {}
    clean: dict = {}
    for k, v in details.items():
        if str(k).strip().lower() in _SECRET_KEYS:
            clean[k] = "[redacted]"
        else:
            clean[k] = v
    return clean


def log_audit(action: str, caller_discord_id: str = "", details: dict | None = None) -> dict:
    """Append one consequential action to ``data/audit.jsonl``. Never logs a password/token.

    ``action`` is a short verb-noun (e.g. "provision_access", "invite_issued", "sr1_scheduled");
    ``caller_discord_id`` is who triggered it (a Discord id, "" if none); ``details`` is a small dict
    of non-secret facts. Returns {ok, at}. Failure to write is logged but never raised — auditing must
    not break the action it records."""
    entry = {
        "at": _now_iso(),
        "action": action,
        "caller": str(caller_discord_id) if caller_discord_id else "",
        "details": _redact(details),
    }
    try:
        with _path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        _LOG.exception("audit_log: could not append %s", action)
        return {"ok": False, "at": entry["at"]}
    return {"ok": True, "at": entry["at"]}


def read_audit_log(limit: int = 50) -> list[dict]:
    """The most recent ``limit`` audit entries (newest last), parsed from the JSONL. Tolerant of a
    missing file (returns []) and of a malformed line (skips it)."""
    path = _path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        _LOG.exception("audit_log: could not read %s", path)
        return []
    tail = lines[-int(limit):] if limit and limit > 0 else lines
    out: list[dict] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# ── admin-gated read tool (for Zach) ───────────────────────────────────────

def audit_read_admin(caller_discord_id: str, limit: int = 50) -> dict:
    """Read back the recent audit log — ADMIN ONLY (Zach). A non-admin caller is denied, and the
    attempt is itself audited. Returns {ok, entries} for an admin, or {ok: False, error} otherwise."""
    from forsch.adk_bridge.friend_memory import _admins

    if str(caller_discord_id) not in _admins():
        log_audit("audit_read_denied", caller_discord_id, {"reason": "not an admin"})
        return {"ok": False, "error": "the audit log is admin-only."}
    return {"ok": True, "entries": read_audit_log(limit)}
