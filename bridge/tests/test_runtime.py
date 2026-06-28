from forsch.adk_bridge.runtime import get_runtime

def test_runtime_exposes_agents_and_session_service():
    rt = get_runtime()
    assert "stability" in rt.agents
    assert rt.session_service is not None
