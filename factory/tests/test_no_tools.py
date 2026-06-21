"""A no-tools agent must still generate valid python, and a pinned model must
be hardcoded (win over the global FORSCH_ADK_MODEL)."""

from forsch.adk_factory.models import AgentSpec
from forsch.adk_factory.renderer import render_agent_package


def _spec(**kw):
    base = dict(
        id="solo",
        package="forsch.agent_solo.agent",
        adk_name="solo_agent",
        model_code="forsch.agent_solo.agent.solo_model",
        instruction="Be helpful.",
        tools=[],
    )
    base.update(kw)
    return AgentSpec(**base)


def test_no_tools_agent_compiles():
    src = next(iter(render_agent_package(_spec()).values()))
    compile(src, "<solo agent.py>", "exec")  # SyntaxError if the empty-import bug returns
    assert "import (" not in src  # no empty `from ... import ()`


def test_pinned_model_is_hardcoded():
    src = next(iter(render_agent_package(_spec(model="glm-5.2")).values()))
    assert "_LITELLM_MODEL = 'glm-5.2'" in src  # pinned wins, not the env default


def test_unpinned_model_uses_env_default():
    src = next(iter(render_agent_package(_spec()).values()))
    assert 'os.environ.get("FORSCH_ADK_MODEL"' in src
