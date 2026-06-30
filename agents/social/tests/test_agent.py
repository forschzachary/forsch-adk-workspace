from forsch.agent_social.agent import agent, root_agent


def test_social_agent_exposes_root_agent():
    assert agent is root_agent
    assert root_agent.name == "social_agent"
    tool_names = {tool.__name__ for tool in root_agent.tools}
    assert {
        "get_linkedin_brand_brief",
        "create_linkedin_draft",
        "list_linkedin_drafts",
        "score_linkedin_draft",
        "create_linkedin_go_live_plan",
        "record_linkedin_metric_snapshot",
        "get_linkedin_metric_dashboard",
        "run_linkedin_observability_cycle",
        "list_linkedin_autonomous_actions",
    } <= tool_names
