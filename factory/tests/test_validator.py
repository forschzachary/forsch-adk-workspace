from forsch.adk_factory.models import AgentSpec
from forsch.adk_factory.validator import classify_tools

KNOWN = {"forsch.adk_components.tools.get_git_state"}


def test_unknown_tool_is_flagged_new_not_error():
    spec = AgentSpec(
        id="x",
        package="p",
        adk_name="x",
        model_code="m",
        tools=[
            "forsch.adk_components.tools.get_git_state",
            "forsch.adk_components.tools.brand_new",
        ],
    )
    known, new = classify_tools(spec, KNOWN)
    assert known == ["forsch.adk_components.tools.get_git_state"]
    assert new == ["forsch.adk_components.tools.brand_new"]  # mint-new signal, not a crash
