from pathlib import Path

from forsch.adk_factory.cli import plan

WS = Path("/root/.hermes/workspace/adk")


def test_plan_lists_targets_and_writes_nothing():
    result = plan(WS / "agent_specs" / "agents.yaml", agent_id="stability")
    targets = [f["path"] for f in result["files"]]
    assert "web_agents/stability/root_agent.yaml" in targets
    # dry-run: result carries content but the function performs no writes
    assert all("content" in f for f in result["files"])
