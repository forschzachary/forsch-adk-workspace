"""Poller — the PULL trigger: fetch new comments since the cursor, handle each,
advance the cursor; plus SqliteLedger persistence. Agent runner is faked.
"""
import asyncio
import os
import tempfile

from forsch.adk_bridge.teamrooms.poller import poll_once, SqliteLedger
from forsch.adk_bridge.teamrooms.core import InMemoryLedger

CONFIG = {"spaces": {"stab-space": "stability"}, "mention_routing": False, "start_cursor": "2026-06-22 00:00:00"}


class _FakeClient:
    def __init__(self, comments):
        self._comments = comments
        self.posted = []

    def list_comments_since(self, since, limit=100):
        return [c for c in self._comments if c["creation"] > since]

    def get_discussion(self, name):
        return {"name": name, "project": "stab-space"}

    def post_comment(self, d, html):
        self.posted.append((d, html))
        return {"name": "x"}


class _Runtime:
    def __init__(self):
        self.agents = {"stability": object()}
        self.session_service = None


async def _fake_run(a, an, ss, uid, sid, text):
    return f"reply from {an}"


def test_poll_handles_each_and_advances_cursor():
    comments = [
        {"name": "c1", "content": "<p>hi</p>", "reference_name": "d1", "owner": "h@x", "creation": "2026-06-22 01:00:00"},
        {"name": "c2", "content": "<p>yo</p>", "reference_name": "d2", "owner": "h@x", "creation": "2026-06-22 02:00:00"},
    ]
    client, rt, ledger = _FakeClient(comments), _Runtime(), InMemoryLedger()
    summary = asyncio.run(poll_once(client, rt, CONFIG, ledger, "bot@x", run_fn=_fake_run))
    assert summary["polled"] == 2
    assert len(client.posted) == 2
    assert ledger.get_cursor() == "2026-06-22 02:00:00"


def test_second_poll_fetches_nothing_after_cursor():
    comments = [{"name": "c1", "content": "<p>hi</p>", "reference_name": "d1", "owner": "h@x", "creation": "2026-06-22 01:00:00"}]
    client, rt, ledger = _FakeClient(comments), _Runtime(), InMemoryLedger()
    asyncio.run(poll_once(client, rt, CONFIG, ledger, "bot@x", run_fn=_fake_run))
    summary2 = asyncio.run(poll_once(client, rt, CONFIG, ledger, "bot@x", run_fn=_fake_run))
    assert summary2["polled"] == 0
    assert len(client.posted) == 1  # no double-post


def test_sqlite_ledger_persists_across_instances():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "ledger.db")
        l1 = SqliteLedger(db)
        l1.mark("c1")
        l1.set_cursor("2026-06-22 03:00:00")
        l2 = SqliteLedger(db)  # reopen — simulates a restart
        assert l2.seen("c1") is True
        assert l2.seen("c2") is False
        assert l2.get_cursor() == "2026-06-22 03:00:00"
