"""Tests for validation engine: structural, behavioral, TTL decay, confidence model.

Runs under pytest (the project's configured runner).
"""

import pytest
from datetime import datetime, timedelta, timezone
from forsch.adk_factory.validation import (
    StructuralValidator,
    BehavioralValidator,
    ToolValidationResult,
    ValidationReport,
    StructuralResult,
    BehavioralResult,
    validate_tools,
    format_report_text,
)


# ── structural validator ──────────────────────────────────────────────────────

def test_structural_real_tool():
    """A real importable function should pass structural checks."""
    result = StructuralValidator.validate(
        "forsch.adk_factory.tool_metadata.tool"
    )
    assert result.import_ok, f"import failed: {result.errors}"
    assert result.signature_ok
    assert result.docstring_ok
    assert result.checked_at  # timestamp present


def test_structural_nonexistent():
    """A nonexistent module should fail with import error."""
    result = StructuralValidator.validate("nonexistent.module.func")
    assert not result.passed
    assert not result.import_ok
    assert any("import" in e.lower() for e in result.errors)


def test_structural_missing_function():
    """An existing module but missing function should fail."""
    result = StructuralValidator.validate(
        "forsch.adk_factory.tool_metadata.nonexistent_func"
    )
    assert not result.passed
    assert result.import_ok  # module imported fine
    assert any("not found" in e for e in result.errors)


def test_structural_no_docstring():
    """A function without a docstring should fail docstring check."""
    result = StructuralResult()
    assert not result.docstring_ok
    assert not result.passed


# ── behavioral validator ──────────────────────────────────────────────────────

def test_behavioral_authsome_live():
    """Authsome should be reachable on the cloud box."""
    bv = BehavioralValidator(target="cloud")
    result = bv.validate("forsch.adk_factory.tool_metadata.tool")
    assert result.authsome_live, f"Authsome not reachable: {result.errors}"
    assert result.checked_at
    assert result.target == "cloud"


def test_behavioral_default_target():
    """Default target should be 'cloud'."""
    bv = BehavioralValidator()
    assert bv.target == "cloud"


def test_behavioral_ttl():
    """TTL should be configurable."""
    bv = BehavioralValidator(ttl_hours=48)
    assert bv.ttl_hours == 48


def test_behavioral_no_auth_provider():
    """Tool with no auth provider should have api_reachable=True (not a failure)."""
    bv = BehavioralValidator(target="cloud")
    result = bv.validate("some.tool.without.auth")
    assert result.api_reachable  # default True when no auth to check


# ── confidence model ──────────────────────────────────────────────────────────

def test_confidence_green():
    """Structural pass + behavioral pass + within TTL = green."""
    r = ToolValidationResult(
        tool_name="test.tool",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(
            passed=True,
            checked_at=datetime.now(timezone.utc).isoformat(),
            ttl_hours=24,
        ),
    )
    assert r.confidence == "green"
    assert r.dot == "\u25cf"


def test_confidence_red():
    """Structural failure = red, regardless of behavioral."""
    r = ToolValidationResult(
        tool_name="test.tool",
        structural=StructuralResult(passed=False, errors=["import failed"]),
        behavioral=BehavioralResult(passed=True),
    )
    assert r.confidence == "red"
    assert r.dot == "\u25cb"


def test_confidence_yellow_behavioral_fail():
    """Structural pass + behavioral fail = yellow."""
    r = ToolValidationResult(
        tool_name="test.tool",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(passed=False, errors=["authsome down"]),
    )
    assert r.confidence == "yellow"
    assert r.dot == "\u25c9"


def test_confidence_yellow_stale():
    """Behavioral pass but past TTL = yellow (stale)."""
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    r = ToolValidationResult(
        tool_name="test.tool",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(
            passed=True,
            checked_at=stale_time,
            ttl_hours=24,
        ),
    )
    assert r.confidence == "yellow", f"expected yellow, got {r.confidence}"


def test_confidence_yellow_no_behavioral():
    """Structural pass + behavioral not passed (default) = yellow."""
    r = ToolValidationResult(
        tool_name="test.tool",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(passed=False),
    )
    assert r.confidence == "yellow"


# ── validation report ─────────────────────────────────────────────────────────

def test_report_summary():
    """Report should correctly count green/yellow/red."""
    report = ValidationReport(target="cloud")
    report.tools["a"] = ToolValidationResult(
        tool_name="a",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(
            passed=True,
            checked_at=datetime.now(timezone.utc).isoformat(),
            ttl_hours=24,
        ),
    )
    report.tools["b"] = ToolValidationResult(
        tool_name="b",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(passed=False),
    )
    report.tools["c"] = ToolValidationResult(
        tool_name="c",
        structural=StructuralResult(passed=False),
        behavioral=BehavioralResult(passed=True),
    )
    s = report.summary
    assert s["green"] == 1
    assert s["yellow"] == 1
    assert s["red"] == 1
    assert s["total"] == 3


def test_report_to_dict():
    """to_dict should produce valid structure."""
    report = ValidationReport(target="cloud")
    report.tools["test"] = ToolValidationResult(
        tool_name="test",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(
            passed=True,
            checked_at=datetime.now(timezone.utc).isoformat(),
            ttl_hours=24,
        ),
    )
    d = report.to_dict()
    assert d["target"] == "cloud"
    assert "tools" in d
    assert "test" in d["tools"]
    assert d["tools"]["test"]["confidence"] == "green"
    assert d["tools"]["test"]["dot"] == "\u25cf"


def test_empty_report():
    """Empty report should have zero counts."""
    report = ValidationReport(target="hetzner")
    s = report.summary
    assert s == {"green": 0, "yellow": 0, "red": 0, "total": 0}


# ── format_report_text ────────────────────────────────────────────────────────

def test_format_report_text():
    """format_report_text should produce readable output."""
    report = ValidationReport(target="cloud")
    report.tools["test.tool"] = ToolValidationResult(
        tool_name="test.tool",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(
            passed=True,
            checked_at=datetime.now(timezone.utc).isoformat(),
            ttl_hours=24,
        ),
    )
    text = format_report_text(report)
    assert "Validation Report" in text
    assert "target: cloud" in text
    assert "\u25cf" in text
    assert "test.tool" in text or "tool" in text


# ── validate_tools ────────────────────────────────────────────────────────────

def test_validate_tools_real():
    """validate_tools should work on a real importable function."""
    report = validate_tools(
        ["forsch.adk_factory.tool_metadata.ToolRegistry.all_tools"],
        target="cloud",
    )
    assert report.target == "cloud"
    assert len(report.tools) == 1
    result = list(report.tools.values())[0]
    assert result.structural.import_ok


def test_validate_tools_empty():
    """Empty tool list should produce empty report."""
    report = validate_tools([], target="cloud")
    assert report.summary["total"] == 0
