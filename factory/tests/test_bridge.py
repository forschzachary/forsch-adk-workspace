from pathlib import Path

from forsch.adk_factory.bridge import analyze_bridge

WS = Path("/root/.hermes/workspace/adk")


def test_analyze_surfaces_the_five_agent_drift():
    report = analyze_bridge(
        WS / "agent_specs" / "agents.yaml",
        WS / "bridge" / "bridge_config.yaml",
    )
    # stability is the only contracted agent and its channels match the route.
    assert report["in_sync"] == ["stability"]
    # the five bridge-routed-but-contract-less leads are flagged as drift.
    assert sorted(report["drift"]) == ["assistant", "brand", "build", "ops", "social"]
    # the scalar `dm_fallback: assistant` is not mistaken for a route.
    assert "dm_fallback" not in report["drift"]
