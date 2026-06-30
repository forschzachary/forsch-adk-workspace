from forsch.agent_brand.agent import agent, root_agent


def test_brand_agent_exposes_root_agent():
    assert agent is root_agent
    assert root_agent.name == "brand_agent"
    tool_names = {tool.__name__ for tool in root_agent.tools}
    assert {
        "get_linkedin_brand_brief",
        "score_linkedin_draft",
        "stage_linkedin_profile_update",
        "get_personal_site_launch_brief",
        "audit_personal_site_launch",
        "get_linkedin_metric_dashboard",
        "list_linkedin_autonomous_actions",
    } <= tool_names
