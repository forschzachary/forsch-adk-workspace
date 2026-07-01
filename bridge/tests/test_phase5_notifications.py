"""Phase 5 — proactive notifications (the watcher that DMs a friend when their movie lands).

All mocks/dry-runs (NO live Discord DM, NO live `sr`): friend_memory's watched_requests lifecycle,
and request_watcher's poll → notify → mark-idempotent loop using a fake `search_library` and a mock
`send_dm`. Filesystem state is isolated to a tmp FORSCH_ADK_WORKSPACE.

Live DM delivery (the real `bot.send_dm` opening a Discord DM channel) is NOT covered here — it needs
a live bot + a friend who has accepted it. That path is marked NEEDS LIVE VERIFICATION in the handoff.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest


@pytest.fixture
def fm(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.friend_memory as fm
    importlib.reload(fm)
    return fm


@pytest.fixture
def rw(tmp_path, monkeypatch, fm):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.request_watcher as rw
    importlib.reload(rw)
    # rw imported friend_memory at module load; rebind it to the reloaded, tmp-bound instance.
    rw.fm = fm
    return rw


class FakeBot:
    """A stand-in for ADKDiscordBot: records DMs; can simulate a blocked route (send fails)."""

    def __init__(self, deliver: bool = True):
        self.deliver = deliver
        self.sent: list[tuple[str, str]] = []

    async def send_dm(self, user_id, content) -> bool:
        if not self.deliver:
            return False
        self.sent.append((str(user_id), content))
        return True


# ── friend_memory: watched_requests lifecycle ──────────────────────────────

def test_add_and_get_watched_request(fm):
    fm.onboard_friend("42", "Dave")
    fm.add_watched_request("42", "603", "The Matrix")
    open_watches = fm.get_watched_requests("42")
    assert len(open_watches) == 1
    assert open_watches[0]["title"] == "The Matrix"
    assert open_watches[0]["tmdb_id"] == "603"
    assert open_watches[0]["notified"] is False


def test_add_watched_request_is_idempotent(fm):
    fm.add_watched_request("42", "603", "The Matrix")
    fm.add_watched_request("42", "603", "The Matrix")  # same title — no duplicate
    assert len(fm.get_watched_requests("42", include_notified=True)) == 1


def test_mark_notified_hides_from_open(fm):
    fm.add_watched_request("42", "603", "The Matrix")
    fm.mark_watched_request_notified("42", "The Matrix", "603")
    assert fm.get_watched_requests("42") == []  # no longer open
    assert len(fm.get_watched_requests("42", include_notified=True)) == 1


def test_rearm_reopens_a_watch(fm):
    fm.add_watched_request("42", "603", "The Matrix")
    fm.mark_watched_request_notified("42", "The Matrix", "603")
    out = fm.rearm_watched_request("42", "The Matrix", "603")
    # ok reflects the on-disk state (read back), so a real re-arm reports True.
    assert out["ok"] is True
    assert len(fm.get_watched_requests("42")) == 1


def test_rearm_missing_watch_reports_not_ok(fm):
    # No such watch (or no record): callers must be able to detect the miss so a
    # blocked DM isn't silently left suppressed.
    assert fm.rearm_watched_request("42", "Nonexistent", "0")["ok"] is False
    fm.add_watched_request("42", "603", "The Matrix")
    assert fm.rearm_watched_request("42", "Different Movie", "999")["ok"] is False


def test_clear_watched_request(fm):
    fm.add_watched_request("42", "603", "The Matrix")
    out = fm.clear_watched_request("42", "The Matrix", "603")
    assert out["ok"] is True and out["remaining"] == 0
    assert fm.get_watched_requests("42", include_notified=True) == []


def test_all_friend_ids_skips_bookkeeping(fm):
    fm.onboard_friend("42", "Dave")
    fm.invite_friend("zoe")  # writes _invites.json — must be skipped
    assert fm.all_friend_ids() == ["42"]


def test_is_watch_stale(fm):
    fresh = {"requested_at": fm._now_iso()}
    assert fm.is_watch_stale(fresh) is False
    old = {"requested_at": "2000-01-01T00:00:00+00:00"}
    assert fm.is_watch_stale(old) is True
    assert fm.is_watch_stale({}) is False  # no timestamp → never stale


# ── request_watcher: poll → notify → idempotent ────────────────────────────

def test_watcher_notifies_once_when_available(rw, fm, monkeypatch):
    fm.add_watched_request("42", "603", "The Matrix")
    monkeypatch.setattr(rw, "search_library", lambda t: "The Matrix (1999) available")
    bot = FakeBot()

    asyncio.run(rw.watch_requests(bot, poll_interval=0, iterations=1))
    assert len(bot.sent) == 1
    uid, content = bot.sent[0]
    assert uid == "42" and "The Matrix" in content and "ready" in content.lower()
    # idempotent: a second pass sends nothing more
    asyncio.run(rw.watch_requests(bot, poll_interval=0, iterations=1))
    assert len(bot.sent) == 1


def test_watcher_silent_when_not_available(rw, fm, monkeypatch):
    fm.add_watched_request("42", "603", "The Matrix")
    monkeypatch.setattr(rw, "search_library", lambda t: "The Matrix (1999) downloading")
    bot = FakeBot()
    asyncio.run(rw.watch_requests(bot, poll_interval=0, iterations=1))
    assert bot.sent == []
    assert len(fm.get_watched_requests("42")) == 1  # still open, not notified


def test_watcher_rearms_on_blocked_send(rw, fm, monkeypatch):
    """If the DM can't be delivered (route closed), the watch is re-armed and retried next pass."""
    fm.add_watched_request("42", "603", "The Matrix")
    monkeypatch.setattr(rw, "search_library", lambda t: "The Matrix available")
    blocked = FakeBot(deliver=False)
    asyncio.run(rw.watch_requests(blocked, poll_interval=0, iterations=1))
    assert blocked.sent == []
    assert len(fm.get_watched_requests("42")) == 1  # re-armed, still open

    # route opens → next pass delivers exactly once
    ok = FakeBot(deliver=True)
    asyncio.run(rw.watch_requests(ok, poll_interval=0, iterations=1))
    assert len(ok.sent) == 1
    assert fm.get_watched_requests("42") == []


def test_watcher_clears_stale_watch(rw, fm, monkeypatch):
    fm.add_watched_request("42", "603", "Old Title")
    # backdate the watch past the stale window
    rec = fm._load("42")
    rec["watched_requests"][0]["requested_at"] = "2000-01-01T00:00:00+00:00"
    fm._save(rec)
    monkeypatch.setattr(rw, "search_library", lambda t: "not in library")
    bot = FakeBot()
    asyncio.run(rw.watch_requests(bot, poll_interval=0, iterations=1))
    assert bot.sent == []
    assert fm.get_watched_requests("42", include_notified=True) == []  # cleared


def test_watcher_drains_pending_dm(rw, fm, monkeypatch):
    """The Phase-4 pending-DM queue is drained by the same loop once the route opens."""
    fm.queue_pending_dm("42", "here is your login: sr-cafef00d")
    monkeypatch.setattr(rw, "search_library", lambda t: "not in library")
    bot = FakeBot()
    asyncio.run(rw.watch_requests(bot, poll_interval=0, iterations=1))
    assert len(bot.sent) == 1 and bot.sent[0][0] == "42"
    assert fm.get_pending_dm("42") is None  # delivered → cleared


def test_watcher_skips_empty_pending_marker(rw, fm, monkeypatch):
    """A route-blocked marker with no payload (Phase-4 _note_blocked_dm) is not a deliverable DM."""
    fm.queue_pending_dm("42", "")  # marker only, no content
    monkeypatch.setattr(rw, "search_library", lambda t: "not in library")
    bot = FakeBot()
    asyncio.run(rw.watch_requests(bot, poll_interval=0, iterations=1))
    assert bot.sent == []


def test_watcher_handles_search_failure(rw, fm, monkeypatch):
    """A throwing search_library is treated as 'not available', not a crash."""
    fm.add_watched_request("42", "603", "The Matrix")

    def boom(_):
        raise RuntimeError("stack down")

    monkeypatch.setattr(rw, "search_library", boom)
    bot = FakeBot()
    asyncio.run(rw.watch_requests(bot, poll_interval=0, iterations=1))
    assert bot.sent == []
    assert len(fm.get_watched_requests("42")) == 1  # untouched
