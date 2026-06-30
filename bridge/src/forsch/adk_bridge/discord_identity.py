"""Discord bot-identity guard — fail-closed.

A bot must refuse to boot as the wrong identity. ``verify_identity(token, expected_id)`` asks
Discord ``/users/@me`` for the token's real bot id; it returns ok ONLY when that id equals the
expected id. Missing token/expected-id, a wrong id, or any network/HTTP/JSON failure all fail
CLOSED (do not connect). Pure stdlib — ported from the companions system so the ADK bridge owns it.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DISCORD_ME_URL = "https://discord.com/api/v10/users/@me"
# Discord's API sits behind Cloudflare and REQUIRES a User-Agent; without it every request is
# rejected (403 / Cloudflare 1010) regardless of the token, which would fail the guard closed
# for valid tokens too.
USER_AGENT = "DiscordBot (https://github.com/forschzachary/forsch-adk-workspace, 1.0)"


@dataclass(frozen=True)
class IdentityResult:
    ok: bool
    actual_id: str | None
    reason: str


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    value = exc.headers.get("Retry-After") if exc.headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def fetch_bot_id(token: str, *, urlopen=urllib.request.urlopen, timeout: float = 10.0,
                 max_attempts: int = 3, sleep=time.sleep) -> str:
    """Return the bot's own user id from Discord REST (raises on any failure)."""
    req = urllib.request.Request(
        DISCORD_ME_URL,
        headers={"Authorization": f"Bot {token}", "User-Agent": USER_AGENT},
    )
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return str(data["id"])
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= attempts:
                raise
            sleep(_retry_after_seconds(exc) or min(60.0, float(2 ** attempt)))
    raise RuntimeError("unreachable")


def verify_identity(token: str | None, expected_id: str | None, *, fetcher=fetch_bot_id) -> IdentityResult:
    """Fail-closed identity check. ok=True only when the live bot id == expected_id."""
    if not expected_id:
        return IdentityResult(False, None, "no_expected_id")
    if not token:
        return IdentityResult(False, None, "no_token")
    try:
        actual = fetcher(token)
    except Exception as exc:  # network / HTTP / JSON — all fail closed
        return IdentityResult(False, None, f"lookup_failed:{type(exc).__name__}")
    if actual != str(expected_id):
        return IdentityResult(False, actual, "wrong_bot_token")
    return IdentityResult(True, actual, "ok")
