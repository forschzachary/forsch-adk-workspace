"""Ops agent graph definition."""

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from forsch.adk_components.tools import get_crm_health_snapshot, list_recent_crm_leads

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("LITELLM_API_KEY")

root_agent = Agent(
    name="ops_agent",
    model=LiteLlm(
        model=os.environ.get("FORSCH_ADK_MODEL", "openai/gpt-5.5"),
        api_base=_LITELLM_BASE_URL,
        api_key=_LITELLM_API_KEY,
    ),
    description="Infrastructure and operations lead for Forsch.",
    instruction=(
        "You are the ops team lead for Forsch. Focus on infrastructure health, "
        "deployment state, incident triage, and read-only business telemetry. "
        "Use CRM tools for factual checks before making claims about leads or "
        "newsletter subscriptions. Keep recommendations concise and operational."
    ),
    tools=[get_crm_health_snapshot, list_recent_crm_leads],
)

agent = root_agent
