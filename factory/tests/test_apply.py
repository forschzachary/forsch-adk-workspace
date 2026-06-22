from pathlib import Path

import pytest

from forsch.adk_factory.cli import apply, write_files

WS = Path("/root/.hermes/workspace/adk")


def test_apply_writes_both_surfaces_then_is_idempotent(tmp_path: Path):
    # Apply the real stability manifest into a throwaway workspace root.
    out = apply(WS / "agent_specs" / "agents.yaml", "stability", tmp_path)
    web = tmp_path / "web_agents" / "stability" / "root_agent.yaml"
    pkg = tmp_path / "agents" / "stability" / "src" / "forsch" / "agent_stability" / "agent.py"
    # apply must render BOTH the web wrapper AND the runnable package (the bridge
    # imports the package; rendering only the wrapper is how the manifest drifted).
    assert web.exists() and pkg.exists()
    golden = (WS / "web_agents" / "stability" / "root_agent.yaml").read_text()
    assert web.read_text() == golden
    assert set(out["written"]) == {str(web), str(pkg)}

    # Re-applying the unchanged manifest changes nothing (idempotent).
    before = (web.read_text(), pkg.read_text())
    apply(WS / "agent_specs" / "agents.yaml", "stability", tmp_path)
    assert (web.read_text(), pkg.read_text()) == before


def test_apply_composes_group_preamble_into_grouped_agents(tmp_path: Path):
    # build is in the hubert-team-lead group; its generated package must carry the
    # group preamble + its job (not the bare job). Regression guard: apply() must
    # compose_instruction like the cockpit, or grouped agents render preamble-stripped.
    apply(WS / "agent_specs" / "agents.yaml", "build", tmp_path)
    pkg = (tmp_path / "agents" / "build" / "src" / "forsch" / "agent_build" / "agent.py").read_text()
    # distinctive preamble phrase (no quotes, so repr-escaping can't hide it)
    assert "wearing a team-lead jacket" in pkg
    # and the agent's own job is still present (preamble + job, not preamble only)
    assert "engineering and product-management lead" in pkg


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
