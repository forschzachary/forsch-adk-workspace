"""assistant agent definition."""

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = (
    os.environ.get("LITELLM_HERMES_KEY")
    or os.environ.get("LITELLM_API_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
)
_LITELLM_MODEL = os.environ.get("FORSCH_ADK_MODEL", "openai/gpt-5.5")

assistant_model = LiteLlm(
    model=_LITELLM_MODEL,
    api_base=_LITELLM_BASE_URL,
    api_key=_LITELLM_API_KEY,
)

root_agent = Agent(
    name="assistant_agent",
    model=assistant_model,
    description="Personal assistant lead for Forsch.",
    instruction="You are the assistant team lead for Forsch.",
)

agent = root_agent
