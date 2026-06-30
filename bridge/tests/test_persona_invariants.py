"""Phase 10 — persona invariants (the eval/quality regression gate for the NATIVE bots).

`forsch eval` can't reach a hand-coded Discord bot, so these tests lock the hard rules at the
*source* level: the persona instruction strings that ship to the model, and the tool wiring behind
them. They are pure static assertions — NO live LLM, NO Discord, NO `sr` — so they can gate every
merge cheaply. The behavioral spoiler/credential check that needs a real model lives in
``test_spoiler_safety.py`` (opt-in, ``@pytest.mark.integration``).

Invariants asserted here:
- Huberto: NEVER spoil, NEVER fabricate, NEVER leak credentials, invite-only onboarding, admin-gated
  invites, password-goes-only-in-the-DM.
- ops: NEVER fabricate ("use the tools, never guess"), surface-don't-deploy/delete.
- curator: NEVER fabricate a title/time/slot, NEVER spoil, dry-run before a live SR-1 mutation.
- wiring: Huberto's tools carry the *gated* entry points (invite_friend_admin, not the raw approve),
  and ops is configured mention-only in the live launcher.
"""
from __future__ import annotations

import re

from forsch.adk_bridge.cat_persona import HUBERTO_INSTRUCTION, make_huberto_agent
from forsch.adk_bridge.curator_persona import CURATOR_INSTRUCTION
from forsch.adk_bridge.ops_persona import OPS_INSTRUCTION


def _norm(s: str) -> str:
    """Lower-case + collapse whitespace so a phrase check survives line-wrapping in the source."""
    return re.sub(r"\s+", " ", s.lower())


HUBERTO = _norm(HUBERTO_INSTRUCTION)
OPS = _norm(OPS_INSTRUCTION)
CURATOR = _norm(CURATOR_INSTRUCTION)


def _contains_all(haystack: str, needles) -> list[str]:
    """Return the needles that are MISSING (empty list == all present)."""
    return [n for n in needles if n.lower() not in haystack]


# ── Huberto — the four hard rules ──────────────────────────────────────────

def test_huberto_never_spoils():
    # the no-spoiler rule must be present, stated as a hard rule, and explain the ||spoiler tag|| escape
    assert "never spoil" in HUBERTO
    assert "spoiler tag" in HUBERTO or "||" in HUBERTO_INSTRUCTION
    # it must be framed as overriding personality (a HARD rule), not a soft preference
    assert "hard rule" in HUBERTO


def test_huberto_never_fabricates():
    assert "never make anything up" in HUBERTO
    # the positive corollary: facts come from tools
    assert "use the tools, never guess" in HUBERTO or "use your tools for real facts" in HUBERTO
    # explicit no-invention list (plots/ratings/years/availability)
    assert "never invent" in HUBERTO


def test_huberto_never_leaks_credentials():
    # the password must be DM-only — never a channel, never back to Zach
    assert "password" in HUBERTO
    assert "only in their dm" in HUBERTO or "only go in" in HUBERTO or "goes only in" in HUBERTO
    assert "never in a channel" in HUBERTO
    # and never echoed to the admin
    assert "never back to zach" in HUBERTO or "never quote credentials" in HUBERTO


def test_huberto_is_invite_only():
    assert "invite-only" in HUBERTO or "invite only" in HUBERTO
    # un-invited people are NOT provisioned — taken-name-and-check-with-zach instead
    assert "do not make an account" in HUBERTO or "do not make a second one" in HUBERTO or "don't make an account" in HUBERTO
    assert "is_invited" in HUBERTO


def test_huberto_invite_is_admin_gated_in_instruction():
    # only the admin can approve; the gate is enforced by the caller-id arg, not by the prompt's say-so
    assert "only zach" in HUBERTO or "only an admin" in HUBERTO
    assert "invite_friend_admin" in HUBERTO
    # a non-admin asking to invite is deflected, not actioned
    assert "let me check with zach" in HUBERTO


def test_huberto_lifecycle_is_admin_only():
    # suspend/offboard are admin-only and never described as a hard delete
    assert "admin only" in HUBERTO or "admin-only" in HUBERTO
    assert "offboard_friend" in HUBERTO
    assert "does not hard-delete" in HUBERTO or "never delete an account" in HUBERTO


# ── ops — facts-only, surface-don't-act ────────────────────────────────────

def test_ops_never_fabricates():
    assert "never make anything up" in OPS
    assert "use the tools, never guess" in OPS
    # every number/status traces to a tool
    assert "comes from a tool" in OPS


def test_ops_does_not_deploy_or_delete():
    # ops diagnoses + recommends; a human runs the destructive command
    assert "do not deploy or delete" in OPS or "don't deploy or delete" in OPS
    assert "for a human to run" in OPS or "human to run" in OPS


# ── curator — never fabricate a slot, never spoil, dry-run first ───────────

def test_curator_never_fabricates():
    assert "never fabricate" in CURATOR
    assert "every fact comes from a tool" in CURATOR


def test_curator_never_spoils():
    assert "never spoil" in CURATOR


def test_curator_dry_runs_before_live_mutation():
    # placing a title live on SR-1 needs an explicit ask; dry-run shows the reflow first
    assert "dry-run" in CURATOR or "dry run" in CURATOR
    assert "unless you've been explicitly asked" in CURATOR or "only when explicitly asked" in CURATOR
    # and it never unilaterally deletes a program/bump/event
    assert "never unilaterally delete" in CURATOR


# ── wiring: the persona ships the GATED tools, not the raw primitives ──────

def test_huberto_tools_use_admin_gated_invite(set_admin_env, monkeypatch):
    """The agent must be built with invite_friend_admin (the gated entry point), never the raw
    _approve_invite/invite_friend primitive — so a non-admin can't slip an invite through."""
    # building the agent constructs a LiteLlm model; stub the network-touching pieces so this stays
    # a pure wiring assertion (no gateway call).
    import forsch.adk_bridge.cat_persona as cp

    class _FakeModel:
        def __init__(self, *a, **k):
            pass

    captured = {}

    class _FakeAgent:
        def __init__(self, *a, **k):
            captured["tools"] = k.get("tools", [])
            captured["instruction"] = k.get("instruction", "")

    monkeypatch.setattr(cp, "LiteLlm", _FakeModel, raising=False)
    # Agent/LiteLlm are imported lazily inside make_huberto_agent; patch them on the modules they come
    # from so the lazy import picks up the fakes.
    import google.adk as adk
    from google.adk.models import lite_llm
    monkeypatch.setattr(adk, "Agent", _FakeAgent, raising=False)
    monkeypatch.setattr(lite_llm, "LiteLlm", _FakeModel, raising=False)

    make_huberto_agent()
    tool_names = {getattr(t, "__name__", "") for t in captured["tools"]}
    assert "invite_friend_admin" in tool_names
    # the unauthenticated primitive must NOT be exposed to the model
    assert "invite_friend" not in tool_names
    assert "_approve_invite" not in tool_names


def test_ops_is_mention_only_in_launcher(isolate_env, monkeypatch):
    """The live launcher must wire the ops bot mention_only=True (so it doesn't barge into every line
    of team chatter). Build the specs with only the ops token set, stub the agent factories."""
    monkeypatch.setenv("HUBERTO_DISCORD_BOT_TOKEN", "")
    monkeypatch.setenv("COMPANION_LEAD_DISCORD_BOT_TOKEN", "ops-token")
    monkeypatch.delenv("CURATOR_DISCORD_BOT_TOKEN", raising=False)

    import forsch.adk_bridge.discord_main as dm
    import forsch.adk_bridge.ops_persona as op
    monkeypatch.setattr(op, "make_ops_agent", lambda *a, **k: object())

    specs = dm.build_specs()
    ops_specs = [s for s in specs if s.name == "screening_ops"]
    assert len(ops_specs) == 1
    spec = ops_specs[0]
    assert spec.mention_only is True
    assert spec.dm is False  # ops is channel-only, never DMs


def test_curator_is_optional_off_by_default(isolate_env, monkeypatch):
    """With no CURATOR_DISCORD_BOT_TOKEN the third bot must NOT be built — the system runs on two."""
    monkeypatch.setenv("HUBERTO_DISCORD_BOT_TOKEN", "huberto-token")
    monkeypatch.delenv("COMPANION_LEAD_DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CURATOR_DISCORD_BOT_TOKEN", raising=False)

    import forsch.adk_bridge.cat_persona as cp
    import forsch.adk_bridge.discord_main as dm
    monkeypatch.setattr(cp, "make_cat_agent", lambda *a, **k: object())

    specs = dm.build_specs()
    assert not any(s.name == "screening_curator" for s in specs)
