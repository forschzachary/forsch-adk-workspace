"""Hermetic tests for the reference-library tools.

Builds a tiny docs/reference/ tree in a tmp workspace and points
FORSCH_ADK_WORKSPACE at it, so the tests do not depend on the live 7MB library.
"""
from __future__ import annotations

import pytest

from forsch.adk_components.tools.reference_tools import read_reference, search_reference


@pytest.fixture()
def ref_ws(tmp_path, monkeypatch):
    adk = tmp_path / "docs" / "reference" / "adk"
    adk.mkdir(parents=True)
    (adk / "adk-llms-full.md").write_text(
        "# Agent Development Kit\n\n"
        "## Tools\n"
        "Use FunctionTool to expose a Python function as an agent tool.\n\n"
        "## Sessions\n"
        "A session holds conversation state across turns.\n"
    )
    gradio = tmp_path / "docs" / "reference" / "gradio"
    gradio.mkdir(parents=True)
    (gradio / "gradio-llms.md").write_text("# Gradio\n\nUse gr.Blocks for custom layout.\n")
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    return tmp_path


def test_search_finds_hits_with_heading(ref_ws):
    r = search_reference("FunctionTool")
    assert r["count"] >= 1
    hit = r["hits"][0]
    assert hit["source"] == "adk"
    assert "FunctionTool" in hit["snippet"]
    assert hit["heading"] == "Tools"
    assert hit["file"] == "adk/adk-llms-full.md"


def test_search_source_filter(ref_ws):
    r = search_reference("Blocks", source="gradio")
    assert r["count"] == 1
    assert r["hits"][0]["source"] == "gradio"
    assert search_reference("Blocks", source="adk")["count"] == 0


def test_search_unknown_source(ref_ws):
    r = search_reference("x", source="nope")
    assert r["hits"] == []
    assert "unknown source" in r["error"]


def test_search_empty_query(ref_ws):
    assert search_reference("   ")["hits"] == []


def test_search_missing_library(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))  # no docs/reference
    r = search_reference("anything")
    assert r["hits"] == []
    assert "not found" in r["error"]


def test_read_whole_file(ref_ws):
    r = read_reference("adk/adk-llms-full.md")
    assert "FunctionTool" in r["content"]
    assert r["truncated"] is False


def test_read_tolerates_prefix(ref_ws):
    r = read_reference("docs/reference/gradio/gradio-llms.md")
    assert "gr.Blocks" in r["content"]


def test_read_section_only(ref_ws):
    r = read_reference("adk/adk-llms-full.md", section="Tools")
    assert "FunctionTool" in r["content"]
    assert "Sessions" not in r["content"]


def test_read_section_not_found(ref_ws):
    r = read_reference("adk/adk-llms-full.md", section="Nonexistent")
    assert r["content"] == ""
    assert "not found" in r["error"]


def test_read_traversal_rejected(ref_ws):
    r = read_reference("../../../../etc/passwd")
    assert r["content"] == ""
    assert "outside" in r["error"]


def test_read_missing_file(ref_ws):
    r = read_reference("adk/nope.md")
    assert r["content"] == ""
    assert r["error"] == "not found"
