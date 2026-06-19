from forsch.agent_ops.agent import agent, root_agent


def test_ops_agent_exposes_root_agent():
    assert agent is root_agent
    assert root_agent.name == "ops_agent"
    assert len(root_agent.tools) == 2
