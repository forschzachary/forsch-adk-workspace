from pathlib import Path

from forsch.adk_factory.loader import load_manifest
from forsch.adk_factory.renderer import render_agent

WS = Path("/root/.hermes/workspace/adk")


def test_stability_root_agent_yaml_is_byte_identical():
    m = load_manifest(WS / "agent_specs" / "agents.yaml")
    files = render_agent(m.agents["stability"])
    rendered = files["web_agents/stability/root_agent.yaml"]
    golden = (WS / "web_agents" / "stability" / "root_agent.yaml").read_text()
    assert rendered == golden
