from pathlib import Path

import yaml

from forsch.adk_bridge.bridge import (
    _build_channel_map,
    _import_agent,
    _load_config,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "bridge_config.yaml"


def test_bridge_config_routes_team_stability_to_stability_agent():
    config = _load_config(CONFIG_PATH)

    channel_map = _build_channel_map(config)

    assert channel_map["team-stability"] == "stability"


def test_bridge_config_imports_stability_agent():
    config = _load_config(CONFIG_PATH)
    spec = config["agents"]["stability"]

    agent = _import_agent(spec["agent_package"], spec["agent_attr"])

    assert agent.name == "stability_agent"
    assert len(agent.tools) == 7


def test_bridge_pyproject_declares_stability_agent_dependency():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"

    assert '"forsch-agent-stability>=0.1.0"' in pyproject_path.read_text()


def test_agent_spec_matches_bridge_route():
    spec_path = Path(__file__).resolve().parents[2] / "agent_specs" / "agents.yaml"
    manifest = yaml.safe_load(spec_path.read_text())

    stability = manifest["agents"]["stability"]

    assert stability["package"] == "forsch.agent_stability.agent"
    assert stability["attr"] == "root_agent"
    assert "#team-stability" in stability["discord_channels"]
    assert stability["safety_level"] == "local_write"
