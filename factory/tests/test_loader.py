from pathlib import Path

from forsch.adk_factory.loader import load_manifest

FIXTURE = """
version: 1
defaults:
  agent_class: LlmAgent
agents:
  demo:
    package: forsch.agent_demo.agent
    attr: root_agent
    adk_name: demo_agent
    description: A demo.
    model_code: forsch.agent_demo.agent.demo_model
    instruction: "Be helpful."
    discord_channels: ["#team-demo"]
    tools: ["forsch.adk_components.tools.noop"]
    smoke_prompts: ["hi"]
"""


def test_load_applies_defaults_and_ids(tmp_path: Path):
    p = tmp_path / "agents.yaml"
    p.write_text(FIXTURE)
    m = load_manifest(p)
    assert list(m.agents.keys()) == ["demo"]
    demo = m.agents["demo"]
    assert demo.id == "demo"
    assert demo.agent_class == "LlmAgent"  # inherited from defaults
    assert demo.adk_name == "demo_agent"
    assert demo.tools == ["forsch.adk_components.tools.noop"]
