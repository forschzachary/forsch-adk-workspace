"""Ops agent graph definition."""

from google.adk import Agent
from forsch.adk_components.tools import get_crm_health_snapshot, list_recent_crm_leads

root_agent = Agent(
    name="ops_agent",
    model="gemini-2.5-flash",
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
