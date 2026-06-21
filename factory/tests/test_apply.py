from pathlib import Path

import pytest

from forsch.adk_factory.cli import apply, write_files

WS = Path("/root/.hermes/workspace/adk")


def test_apply_writes_then_is_idempotent(tmp_path: Path):
    # Apply the real stability manifest into a throwaway workspace root.
    out = apply(WS / "agent_specs" / "agents.yaml", "stability", tmp_path)
    target = tmp_path / "web_agents" / "stability" / "root_agent.yaml"
    assert target.exists()
    golden = (WS / "web_agents" / "stability" / "root_agent.yaml").read_text()
    assert target.read_text() == golden
    assert out["written"] == [str(target)]

    # Re-applying the unchanged manifest changes nothing (idempotent).
    before = target.read_text()
    apply(WS / "agent_specs" / "agents.yaml", "stability", tmp_path)
    assert target.read_text() == before


def test_write_files_rolls_back_on_verify_failure(tmp_path: Path):
    # Pre-existing file must be RESTORED; a brand-new file must be REMOVED.
    existing = tmp_path / "existing.txt"
    existing.write_text("OLD")
    files = [
        {"path": "existing.txt", "content": "NEW"},
        {"path": "fresh.txt", "content": "FRESH"},
    ]
    with pytest.raises(RuntimeError):
        write_files(tmp_path, files, verify=lambda _t: False)
    assert existing.read_text() == "OLD"  # restored from backup
    assert not (tmp_path / "fresh.txt").exists()  # newly-created removed
