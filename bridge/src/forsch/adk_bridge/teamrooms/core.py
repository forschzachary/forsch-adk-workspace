"""Trigger-agnostic core: route one Gameplan comment to an agent and post the reply.

Called by either the poller (PULL) or a webhook route (PUSH) — identical logic. Pure
of any HTTP/poll concern: takes an injected ``client`` (GameplanClient), ``runtime``
(get_runtime()), a ``ledger`` (idempotency), and ``run_fn`` (agent runner; injectable
for tests). Guards against reply loops (self-authored), double replies (ledger), and
closed discussions.
"""
from __future__ import annotations

import re

from forsch.adk_bridge.teamrooms.router import resolve_agent
from forsch.adk_bridge.run import stream_agent

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html):
    return _TAG_RE.sub("", html or "").strip()


def to_reply_html(text, agent_name, config):
    """Wrap an agent's plain-text reply as Gameplan comment HTML, with optional signature."""
    body = (text or "").strip().replace("\n", "<br>")
    sig_tmpl = config.get("reply_signature") or ""
    sig = sig_tmpl.format(agent=agent_name) if sig_tmpl else ""
    html = f"<p>{body}</p>"
    if sig:
        html += f'<p><em>{sig}</em></p>'
    return html


class InMemoryLedger:
    """Idempotency ledger (handled ids) + poll cursor. Prod uses SqliteLedger (poller.py).

    Ledger interface (both impls): seen(id)->bool, mark(id), get_cursor(default), set_cursor(v).
    """

    def __init__(self):
        self._seen = set()
        self._cursor = None

    def seen(self, cid):
        return cid in self._seen

    def mark(self, cid):
        self._seen.add(cid)

    def get_cursor(self, default=None):
        return self._cursor if self._cursor is not None else default

    def set_cursor(self, value):
        self._cursor = value


async def _default_run(agent, agent_name, session_service, user_id, session_id, text):
    chunks = []
    async for tok in stream_agent(agent, agent_name, session_service, user_id, session_id, text):
        chunks.append(tok)
    return "".join(chunks)


async def handle_comment(comment, *, client, runtime, config, ledger, bot_email, run_fn=_default_run):
    """Route + run + reply for one GP Comment dict. Returns a result dict (for logs/tests)."""
    cid = comment.get("name")
    if ledger.seen(cid):
        return {"ok": False, "skipped": "already_handled", "comment": cid}
    if comment.get("owner") == bot_email:  # never reply to our own comments → no loops
        ledger.mark(cid)
        return {"ok": False, "skipped": "self_authored", "comment": cid}

    disc_name = comment.get("reference_name")
    discussion = client.get_discussion(disc_name)
    if discussion is None:
        # Discussion deleted/unreadable (or no reference_name). Mark seen so this
        # comment is not retried forever — otherwise a single poison comment would
        # raise every poll cycle and wedge all later comments behind it.
        ledger.mark(cid)
        return {"ok": False, "skipped": "no_discussion", "comment": cid}
    if discussion.get("closed_at"):  # Frappe rejects comments on closed discussions
        return {"ok": False, "skipped": "closed", "comment": cid}

    agent_name = resolve_agent(
        project=discussion.get("project"),
        content=comment.get("content"),
        agents=set(runtime.agents),
        config=config,
    )
    if agent_name is None:
        return {"ok": False, "skipped": "no_agent", "comment": cid}
    agent = runtime.agents.get(agent_name)
    if agent is None:
        ledger.mark(cid)
        return {"ok": False, "error": "agent_not_loaded", "agent": agent_name, "comment": cid}

    text = strip_html(comment.get("content"))
    user_id = comment.get("owner") or "teamroom"
    session_id = f"teamroom:{disc_name}"  # one ADK session per discussion → continuity
    reply = await run_fn(agent, agent_name, runtime.session_service, user_id, session_id, text)

    client.post_comment(disc_name, to_reply_html(reply, agent_name, config))
    ledger.mark(cid)
    return {"ok": True, "agent": agent_name, "comment": cid, "discussion": disc_name}
