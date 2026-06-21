"""analyze_bridge reconciles the manifest against the bridge routes.

Uses a fixture workspace (not the live manifest) so adding real agents never
breaks this — it tests the classification logic, not the current fleet state.
"""

from forsch.adk_factory.bridge import analyze_bridge

_MANIFEST = """
agents:
  alpha:
    package: forsch.agent_alpha.agent
    adk_name: alpha_agent
    model_code: forsch.agent_alpha.agent.alpha_model
    discord_channels: ["#team-alpha"]
  beta:
    package: forsch.agent_beta.agent
    adk_name: beta_agent
    model_code: forsch.agent_beta.agent.beta_model
    discord_channels: ["#team-x"]
"""

_BRIDGE = """
agents:
  alpha:
    channels: ["#team-alpha"]
  beta:
    channels: ["#team-beta"]
  gamma:
    channels: ["#team-gamma"]
  dm_fallback: alpha
"""


def test_analyze_classifies_in_sync_mismatch_and_drift(tmp_path):
    m = tmp_path / "agents.yaml"
    b = tmp_path / "bridge_config.yaml"
    m.write_text(_MANIFEST)
    b.write_text(_BRIDGE)

    r = analyze_bridge(m, b)
    assert r["in_sync"] == ["alpha"]            # routed + channels match
    assert r["channel_mismatch"] == ["beta"]    # routed but channels differ
    assert r["drift"] == ["gamma"]              # routed, no manifest contract
    assert r["missing_route"] == []             # every manifest agent is routed
    assert "dm_fallback" not in r["drift"]      # scalar entry ignored
