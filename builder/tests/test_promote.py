"""Unit tests for the pure promotion logic (no ruamel/jinja/factory needed).

These cover the risky inversions: stripping the group preamble back off the composed
instruction, and deciding when tools actually changed vs. matched a wildcard.
"""

from __future__ import annotations

import pytest

from forsch.adk_builder.promote import (
    PromoteError,
    _recover_job,
    _tool_patch,
    build_promotion_patch,
)


# --- _recover_job: invert compose_instruction (preamble + "\n\n" + job) ---

def test_recover_job_no_group_is_identity():
    assert _recover_job("just the job\n", "") == "just the job"


def test_recover_job_strips_leading_preamble():
    composed = "PREAMBLE LINE 1\nPREAMBLE LINE 2\n\nthe job\nmore job"
    assert _recover_job(composed, "PREAMBLE LINE 1\nPREAMBLE LINE 2") == "the job\nmore job"


def test_recover_job_preamble_only_yields_empty_job():
    assert _recover_job("PRE", "PRE") == ""


def test_recover_job_mismatch_raises_rather_than_double():
    with pytest.raises(PromoteError):
        _recover_job("totally different text", "PREAMBLE")


# --- _tool_patch: unchanged -> None (preserve manifest), changed -> explicit list ---

def test_tool_patch_explicit_unchanged_returns_none():
    tools = ["forsch.adk_components.tools.a", "forsch.adk_components.tools.b"]
    assert _tool_patch(tools, tools) is None


def test_tool_patch_explicit_added_returns_full_list():
    manifest = ["forsch.adk_components.tools.a"]
    edited = ["forsch.adk_components.tools.a", "forsch.adk_components.tools.b"]
    assert _tool_patch(edited, manifest) == edited


def test_tool_patch_explicit_removed_returns_remaining():
    manifest = ["forsch.adk_components.tools.a", "forsch.adk_components.tools.b"]
    edited = ["forsch.adk_components.tools.a"]
    assert _tool_patch(edited, manifest) == edited


# --- build_promotion_patch: the shelby-like case (no group, explicit tools) ---

def test_build_patch_shelby_like_no_tool_change():
    root = {
        "instruction": "do the thing\n",
        "description": "a helper",
        "tools": [
            {"name": "forsch.adk_components.tools.a"},
            {"name": "forsch.adk_components.tools.b"},
        ],
    }
    manifest_tools = ["forsch.adk_components.tools.a", "forsch.adk_components.tools.b"]
    patch = build_promotion_patch(root, manifest_tools, preamble="")
    assert patch["instruction"] == "do the thing"
    assert patch["description"] == "a helper"
    assert "tools" not in patch  # unchanged -> manifest tools preserved


def test_build_patch_carries_tool_addition():
    root = {
        "instruction": "x",
        "tools": [
            {"name": "forsch.adk_components.tools.a"},
            {"name": "forsch.adk_components.tools.c"},
        ],
    }
    manifest_tools = ["forsch.adk_components.tools.a"]
    patch = build_promotion_patch(root, manifest_tools, preamble="")
    assert patch["tools"] == [
        "forsch.adk_components.tools.a",
        "forsch.adk_components.tools.c",
    ]


def test_build_patch_strips_group_preamble_from_instruction():
    root = {"instruction": "JACKET\n\nthe real job", "tools": []}
    patch = build_promotion_patch(root, manifest_tools=[], preamble="JACKET")
    assert patch["instruction"] == "the real job"
