from forsch.agent_website.agent import agent, root_agent


def test_website_agent_exposes_root_agent():
    assert agent is root_agent
    assert root_agent.name == "website_agent"
    tool_names = {tool.__name__ for tool in root_agent.tools}
    assert {
        "get_personal_site_launch_brief",
        "audit_personal_site_launch",
        "create_website_launch_task",
        "get_linkedin_brand_brief",
        "get_linkedin_metric_dashboard",
        "list_linkedin_autonomous_actions",
    } <= tool_names
