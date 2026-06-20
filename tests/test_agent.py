from forsch.agent_stability.agent import agent, root_agent


def test_stability_agent_exposes_root_agent():
    assert agent is root_agent
    assert root_agent.name == "stability_agent"
    assert len(root_agent.tools) == 4
