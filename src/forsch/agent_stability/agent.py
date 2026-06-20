"""Stability governor agent definition."""

from __future__ import annotations

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from forsch.adk_components.tools import (
    check_service_health,
    get_git_state,
    get_workspace_inventory,
    validate_agent_imports,
)

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = (
    os.environ.get("LITELLM_HERMES_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or os.environ.get("LITELLM_API_KEY")
)
_LITELLM_MODEL = os.environ.get("FORSCH_ADK_MODEL", "openai/gpt-5.5")

stability_model = LiteLlm(
    model=_LITELLM_MODEL,
    api_base=_LITELLM_BASE_URL,
    api_key=_LITELLM_API_KEY,
)

root_agent = Agent(
    name="stability_agent",
    model=stability_model,
    description="Read-only stability governor for the Forsch ADK workspace.",
    instruction=(
        "You are the stability governor for the Forsch ADK workspace. Inspect only; do not "
        "edit files, restart services, install packages, or perform destructive actions. Use "
        "the provided tools to inventory workspace structure, inspect git state, validate agent "
        "imports, and check service health. Report findings with severity, evidence, and the "
        "smallest safe next action."
    ),
    tools=[
        get_workspace_inventory,
        get_git_state,
        validate_agent_imports,
        check_service_health,
    ],
)

agent = root_agent
