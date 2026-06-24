"""Tests for the deploy gate: apply() validates before writing, blocks on red.

Runs under pytest.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from forsch.adk_factory.validation import (
    DeployGateBlocked,
    check_deploy_gate,
    ValidationReport,
    ToolValidationResult,
    StructuralResult,
    BehavioralResult,
)
from forsch.adk_factory.cli import apply


def _make_manifest(tmp_path: Path, tools: list[str]) -> Path:
    """Create a minimal agents.yaml with one agent."""
    manifest = tmp_path / "agent_specs" / "agents.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(f"""\
defaults:
  model: openai/gpt-4o
  provider: openai
  instruction: "test"
  tools: []
  package: forsch.agent_test_agent
  adk_name: test_agent
  model_code: gpt-4o
  web_entrypoint: test-agent
agents:
  test-agent:
    tools: {tools}
""")
    return manifest


# ── unit: check_deploy_gate ───────────────────────────────────────────────────

def test_check_deploy_gate_passes_when_no_red():
    """Gate should not raise when there are zero red tools."""
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
    # Should not raise
    check_deploy_gate("test-agent", report)


def test_check_deploy_gate_blocks_when_red():
    """Gate should raise DeployGateBlocked when any tool is red."""
    report = ValidationReport(target="cloud")
    report.tools["a"] = ToolValidationResult(
        tool_name="a",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(passed=True, checked_at=datetime.now(timezone.utc).isoformat()),
    )
    report.tools["b"] = ToolValidationResult(
        tool_name="b",
        structural=StructuralResult(passed=False, errors=["import failed"]),
        behavioral=BehavioralResult(passed=False),
    )
    with pytest.raises(DeployGateBlocked) as exc:
        check_deploy_gate("test-agent", report)
    assert exc.value.agent_id == "test-agent"
    assert exc.value.report.summary["red"] == 1


def test_check_deploy_gate_passes_on_yellow():
    """Gate should NOT block on yellow (stale / behavioral-only failure)."""
    report = ValidationReport(target="cloud")
    report.tools["a"] = ToolValidationResult(
        tool_name="a",
        structural=StructuralResult(passed=True),
        behavioral=BehavioralResult(passed=False, errors=["authsome down"]),
    )
    # Should not raise — yellow doesn't block
    check_deploy_gate("test-agent", report)


# ── integration: apply() gate behavior ────────────────────────────────────────

def test_gate_blocks_red(tmp_path: Path):
    """apply() with a nonexistent tool should raise DeployGateBlocked."""
    manifest = _make_manifest(tmp_path, ["nonexistent.module.func"])
    with pytest.raises(DeployGateBlocked) as exc:
        apply(manifest, "test-agent", tmp_path)
    assert exc.value.agent_id == "test-agent"
    assert exc.value.report.summary["red"] >= 1


def test_force_bypasses_gate(tmp_path: Path):
    """apply(force=True) should write even when tools are red."""
    manifest = _make_manifest(tmp_path, ["nonexistent.module.func"])
    result = apply(manifest, "test-agent", tmp_path, force=True)
    assert result["agent"] == "test-agent"
    assert len(result["written"]) == 2  # root_agent.yaml + agent.py


def test_skip_validate_bypasses_gate(tmp_path: Path):
    """apply(skip_validate=True) should skip validation entirely."""
    manifest = _make_manifest(tmp_path, ["nonexistent.module.func"])
    result = apply(manifest, "test-agent", tmp_path, skip_validate=True)
    assert result["agent"] == "test-agent"
    assert len(result["written"]) == 2


def test_gate_blocks_red_but_force_writes(tmp_path: Path):
    """force=True writes files even with red tools, and files are valid."""
    manifest = _make_manifest(tmp_path, ["nonexistent.module.func"])
    result = apply(manifest, "test-agent", tmp_path, force=True)
    web = tmp_path / "test-agent" / "root_agent.yaml"
    pkg = tmp_path / "agents" / "test-agent" / "src" / "forsch" / "agent_test-agent" / "agent.py"
    assert web.exists()
    assert pkg.exists()
