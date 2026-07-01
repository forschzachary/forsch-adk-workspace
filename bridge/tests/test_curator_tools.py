"""Curator tools — the non-sr-CLI bits (suggest_to_main's local queue)."""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    import forsch.adk_bridge.curator_tools as ct
    importlib.reload(ct)
    return ct


def test_suggest_to_main_persists_to_queue(ct):
    out = ct.suggest_to_main("feature a Studio Ghibli block")
    assert "queued" in out
    lines = ct._suggestions_path().read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["idea"] == "feature a Studio Ghibli block"
    assert rec["status"] == "pending"
    assert rec["at"]  # timestamp present


def test_suggest_to_main_appends(ct):
    ct.suggest_to_main("one")
    ct.suggest_to_main("two")
    lines = ct._suggestions_path().read_text().strip().splitlines()
    assert [json.loads(l)["idea"] for l in lines] == ["one", "two"]


def test_suggest_to_main_empty_is_noop(ct):
    out = ct.suggest_to_main("   ")
    assert "nothing to suggest" in out
    # Nothing should have been written (the queue file need not even exist).
    p = ct._suggestions_path()
    assert not p.exists() or p.read_text().strip() == ""
