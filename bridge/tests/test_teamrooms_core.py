"""handle_comment — the trigger-agnostic core. Mocks the Gameplan client + the agent
runner (run_fn injected) so we test routing/posting/idempotency without ADK or network.
"""
import asyncio

from forsch.adk_bridge.teamrooms.core import handle_comment, InMemoryLedger

CONFIG = {"spaces": {"stab-space": "stability"}, "mention_routing": True}


class _FakeClient:
    def __init__(self, project="stab-space", closed=False):
        self._project, self._closed = project, closed
        self.posted = []

    def get_discussion(self, name):
        d = {"name": name, "project": self._project, "title": "T"}
        if self._closed:
            d["closed_at"] = "2026-01-01 00:00:00"
        return d

    def post_comment(self, discussion, html):
        self.posted.append((discussion, html))
        return {"name": "newc"}


class _Runtime:
    def __init__(self, names):
        self.agents = {n: object() for n in names}
        self.session_service = None


async def _fake_run(agent, agent_name, ss, uid, sid, text):
    return f"ran {agent_name} on: {text}"


def _call(comment, client, rt, ledger):
    return asyncio.run(handle_comment(
        comment, client=client, runtime=rt, config=CONFIG,
        ledger=ledger, bot_email="bot@x", run_fn=_fake_run,
    ))


def test_routes_runs_and_posts():
    client, rt, ledger = _FakeClient("stab-space"), _Runtime(["stability", "ops"]), InMemoryLedger()
    res = _call({"name": "c1", "content": "<p>hello</p>", "reference_name": "d1", "owner": "human@x"}, client, rt, ledger)
    assert res["ok"] is True and res["agent"] == "stability" and res["discussion"] == "d1"
    assert len(client.posted) == 1
    disc, html = client.posted[0]
    assert disc == "d1" and "ran stability on: hello" in html


def test_idempotent_no_double_reply():
    client, rt, ledger = _FakeClient(), _Runtime(["stability"]), InMemoryLedger()
    c = {"name": "c1", "content": "<p>hi</p>", "reference_name": "d1", "owner": "human@x"}
    _call(c, client, rt, ledger)
    res2 = _call(c, client, rt, ledger)
    assert res2["ok"] is False and res2["skipped"] == "already_handled"
    assert len(client.posted) == 1


def test_self_authored_skipped_no_loop():
    client, rt, ledger = _FakeClient(), _Runtime(["stability"]), InMemoryLedger()
    res = _call({"name": "c1", "content": "<p>x</p>", "reference_name": "d1", "owner": "bot@x"}, client, rt, ledger)
    assert res["skipped"] == "self_authored" and client.posted == []


def test_unmapped_space_no_agent_no_post():
    client, rt, ledger = _FakeClient("random"), _Runtime(["stability"]), InMemoryLedger()
    res = _call({"name": "c1", "content": "<p>just chatting</p>", "reference_name": "d1", "owner": "human@x"}, client, rt, ledger)
    assert res["skipped"] == "no_agent" and client.posted == []


def test_closed_discussion_skipped():
    client, rt, ledger = _FakeClient("stab-space", closed=True), _Runtime(["stability"]), InMemoryLedger()
    res = _call({"name": "c1", "content": "<p>hi</p>", "reference_name": "d1", "owner": "human@x"}, client, rt, ledger)
    assert res["ok"] is False and res["skipped"] == "closed" and client.posted == []


def test_mention_routes_outside_space():
    client, rt, ledger = _FakeClient("random"), _Runtime(["stability", "ops"]), InMemoryLedger()
    res = _call({"name": "c1", "content": "<p>hey @ops look here</p>", "reference_name": "d1", "owner": "human@x"}, client, rt, ledger)
    assert res["ok"] is True and res["agent"] == "ops"
