"""Shared fixtures for the ScreeningRoom native-bot tests (Phase 10 eval gate).

Two jobs:

1. **Filesystem isolation.** Every test that touches friend records / invites / the audit log binds
   ``FORSCH_ADK_WORKSPACE`` to a fresh ``tmp_path`` and reloads the affected module, so a test NEVER
   reads or writes the real ``data/friends/*`` or ``data/audit.jsonl``. ``friend_memory`` and
   ``audit_log`` resolve their dir from that env at import, so a reload after the env is set rebinds them.

2. **No live side effects.** ``mock_sr_cli`` patches the ``sr`` shell-out at the seam each tool uses
   (``onboarding_tools._sr`` returns ``(ok, out)``; ``screening_room_tools._run`` returns ``str``) so a
   test can exercise a tool's gate/parse logic without the real CLI, a real Jellyfin account, or the box.

These fixtures back the static/mocked gate assertions. The only test that talks to a real model is the
opt-in ``test_spoiler_safety`` (``@pytest.mark.integration``), skipped unless ``TEST_LIVE_LLM=1``.
"""
from __future__ import annotations

import importlib

import pytest

ZACH_ADMIN_ID = "175984567176527873"  # the one admin id (SR_ADMIN_DISCORD_IDS) — matches the live config


@pytest.fixture
def isolate_env(tmp_path, monkeypatch):
    """Point the bots' state at a throwaway workspace. No real friend/audit files are touched.

    Returns the tmp workspace Path. Sets the admin env too, so the admin-gate fixtures are consistent.
    """
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("SR_ADMIN_DISCORD_IDS", ZACH_ADMIN_ID)
    return tmp_path


@pytest.fixture
def set_admin_env(monkeypatch):
    """Just the admin id (Zach), without forcing a workspace — for pure admin-gate assertions."""
    monkeypatch.setenv("SR_ADMIN_DISCORD_IDS", ZACH_ADMIN_ID)
    return ZACH_ADMIN_ID


@pytest.fixture
def temp_friends_dir(isolate_env):
    """``friend_memory`` reloaded against the isolated workspace (so ``data/friends`` is the tmp dir)."""
    import forsch.adk_bridge.audit_log as audit
    importlib.reload(audit)  # rebinds its data/ dir to the tmp workspace too (friend_memory imports it)
    import forsch.adk_bridge.friend_memory as fm
    importlib.reload(fm)
    return fm


@pytest.fixture
def temp_audit(isolate_env):
    """``audit_log`` reloaded against the isolated workspace (``data/audit.jsonl`` -> tmp)."""
    import forsch.adk_bridge.audit_log as audit
    importlib.reload(audit)
    return audit


@pytest.fixture
def mock_sr_cli(isolate_env, monkeypatch):
    """Patch the ``sr`` shell-out for BOTH tool modules and return a recorder.

    ``onboarding_tools._sr(args, timeout) -> (ok, out)`` and
    ``screening_room_tools._run(args, timeout) -> str`` are the two seams. Each call is appended to
    ``recorder.calls`` so a test can assert the exact ``sr`` argv a tool would have run — without ever
    invoking the real binary, the box, or a live account.

    A test can override the canned responses by assigning ``recorder.sr_returns`` /
    ``recorder.run_returns`` to a callable ``(args) -> (ok, out)`` / ``(args) -> str``.
    """

    class _Recorder:
        def __init__(self):
            self.calls: list[list[str]] = []
            # default: a benign success that won't accidentally look like an error/conflict
            self.sr_returns = lambda args: (True, "(mock sr) ok")
            self.run_returns = lambda args: "(mock sr) ok"

    rec = _Recorder()

    import forsch.adk_bridge.onboarding_tools as ot
    importlib.reload(ot)
    import forsch.adk_bridge.screening_room_tools as srt
    importlib.reload(srt)

    def fake_sr(args, timeout=120):
        rec.calls.append(list(args))
        return rec.sr_returns(list(args))

    def fake_run(args, timeout=90):
        rec.calls.append(list(args))
        return rec.run_returns(list(args))

    monkeypatch.setattr(ot, "_sr", fake_sr)
    monkeypatch.setattr(srt, "_run", fake_run)
    rec.ot = ot
    rec.srt = srt
    return rec


@pytest.fixture
def reset_rate_limit():
    """The Phase-7 limiter is process-global; clear it so a test starts with a fresh budget."""
    import forsch.adk_bridge.rate_limit as rl
    importlib.reload(rl)
    rl.reset_all()
    return rl
