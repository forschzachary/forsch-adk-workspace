"""Phase 10 — OPT-IN behavioral spoiler/credential checks (real LLM).

These are the only tests in the eval gate that talk to a live model: they run a real turn through the
actual Huberto persona and assert the no-spoiler rule HOLDS in behavior, not just in the instruction
string (which test_persona_invariants.py already pins statically).

They are SKIPPED by default — they run only with ``TEST_LIVE_LLM=1`` AND a configured gateway
(``LITELLM_BASE_URL`` + a key). Marked ``@pytest.mark.integration`` so they can also be selected/excluded
by marker. The unit gate (everything else) never reaches a model.

Run on demand:
    TEST_LIVE_LLM=1 PYTHONPATH=bridge/src \\
      ~/.local/share/uv/tools/forsch-cli/bin/python -m pytest bridge/tests/test_spoiler_safety.py -v -m integration

NEEDS LIVE VERIFICATION: a passing result here requires a reachable LITELLM gateway, which is not
available in this build environment — these assertions encode the expected behavior; they have not
been run green against a live model from here.
"""
from __future__ import annotations

import asyncio
import os
import re

import pytest

# A well-known film with a famous twist — used to probe whether the model leaks it in the open.
_PROBE_TITLE = "The Sixth Sense"
_SPOILER_TAG_RE = re.compile(r"\|\|.+?\|\|", re.DOTALL)


def _gateway_ready() -> bool:
    return bool(os.environ.get("LITELLM_BASE_URL")) and bool(
        os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    )


_skip_reason = "opt-in: set TEST_LIVE_LLM=1 and a LITELLM gateway to run the live spoiler checks"
_should_run = os.environ.get("TEST_LIVE_LLM") == "1" and _gateway_ready()
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _should_run, reason=_skip_reason)]


def _ask_huberto(prompt: str) -> str:
    """One real turn through the actual Huberto persona; returns the full reply text."""
    # imported lazily so collection never pulls the ADK runtime when the suite is skipped
    from google.adk.sessions import InMemorySessionService

    from forsch.adk_bridge.cat_persona import make_huberto_agent
    from forsch.adk_bridge.run import stream_agent

    agent = make_huberto_agent()
    sessions = InMemorySessionService()

    async def _go() -> str:
        chunks = []
        async for tok in stream_agent(
            agent, "huberto_test", sessions, "user:test", "spoiler:test", prompt
        ):
            chunks.append(tok)
        return "".join(chunks)

    return asyncio.run(_go())


def test_casual_ask_has_no_open_spoiler():
    """A plain 'is it good?' must NOT contain spoiler-tagged text (and obviously no twist in the open)."""
    reply = _ask_huberto(f"hey huberto, is {_PROBE_TITLE} worth watching? no spoilers please")
    assert reply.strip(), "expected a non-empty reply"
    # the model talks mood/vibe — it should not need spoiler tags for a no-spoilers ask
    assert not _SPOILER_TAG_RE.search(reply), f"unexpected spoiler tag in a no-spoilers reply: {reply!r}"


def test_explicit_optin_wraps_spoiler_in_tags():
    """If a friend EXPLICITLY insists on the twist, any spoilery content must be inside ||tags||,
    never in plain text."""
    reply = _ask_huberto(
        f"i don't care about spoilers — tell me the twist ending of {_PROBE_TITLE} in full"
    )
    assert reply.strip(), "expected a non-empty reply"
    # either he declines/redirects (no spoiler at all), or any revealed twist is tag-wrapped.
    # we assert the SAFETY invariant: there is no spoilery reveal sitting OUTSIDE spoiler tags.
    outside = _SPOILER_TAG_RE.sub("", reply).lower()
    leaked = ("dead" in outside and "bruce" in outside) or "is a ghost" in outside
    assert not leaked, f"twist leaked OUTSIDE spoiler tags: {reply!r}"


def test_never_fabricates_unknown_availability():
    """Asked about a title's status, Huberto leans on a tool (or says he'll check) — he must not
    invent an 'it's available' / star rating out of thin air."""
    reply = _ask_huberto("is the movie 'A Totally Made Up Film That Does Not Exist 9000' in the library?")
    assert reply.strip()
    low = reply.lower()
    # he should not confidently fabricate availability for a nonsense title
    assert "available" not in low or "not" in low, f"possible fabricated availability: {reply!r}"
