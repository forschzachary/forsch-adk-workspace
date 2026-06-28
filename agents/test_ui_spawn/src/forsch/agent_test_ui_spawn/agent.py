"""agent_test_ui_spawn_agent — blank agent (spawned from Live Agent Graph).

State: blank → building (this file exists) → built (on bridge PYTHONPATH) → live (smoke passes).
"""

from __future__ import annotations

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = (
    os.environ.get("ADK_LITELLM_KEY_TEST_UI_SPAWN")
    or os.environ.get("LITELLM_HERMES_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or os.environ.get("LITELLM_API_KEY")
)
_LITELLM_MODEL = os.environ.get("FORSCH_ADK_MODEL", "openai/gpt-5.5")

test_ui_spawn_model = LiteLlm(
    model=_LITELLM_MODEL,
    api_base=_LITELLM_BASE_URL,
    api_key=_LITELLM_API_KEY,
)

root_agent = Agent(
    name="test_ui_spawn_agent",
    model=test_ui_spawn_model,
    description="UI spawned test",
    instruction="""You are a blank agent spawned from the Live Agent Graph. You can receive messages and reply. Your capabilities will grow as tools and instructions are added.""",
    tools=[],
)

agent = root_agent
