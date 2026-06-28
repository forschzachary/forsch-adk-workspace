"""make_agent — ADK Agent factory that kills the LiteLlm boilerplate.

---
keywords: [agent, adk, litellm, model, gpt-5.5, claude, gemini, factory, skeleton, boilerplate]
intention: "Saves you from copy-pasting the same 30 lines of LiteLlm env-var resolution + key fallback chain + Agent() constructor into every new agent. One call returns a configured Agent."
function: "make_agent(name, description, instruction, tools, model='gpt-5.5') -> google.adk.Agent."
depends_on: []
used_by: [shelby, assistant, ops, stability, all-new-agents]
example: "agent = make_agent('shelby', '...', '...', [log_groceries, add_reminder])"
---
"""
from __future__ import annotations

import os
from typing import Any, Optional

# google.adk imports are lazy — this module is importable without adk installed
# (so agents can be planned before runtime is provisioned).


def _litellm_model_string(model: str) -> str:
    """Pass-through for now; future: 'gpt-5.5' -> 'openai/gpt-5.5'."""
    if "/" not in model:
        return f"openai/{model}"
    return model


def _resolve_litellm() -> tuple[str, str]:
    """Resolve base URL + key from env. Per-agent key > shared > master."""
    base_url = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    key = (
        os.environ.get("ADK_LITELLM_KEY")  # shared default
        or os.environ.get("LITELLM_HERMES_KEY")
        or os.environ.get("LITELLM_MASTER_KEY")
        or os.environ.get("LITELLM_API_KEY")
    )
    if not key:
        raise RuntimeError(
            "make_agent: no LiteLLM key found. Set LITELLM_HERMES_KEY or "
            "LITELLM_API_KEY in the environment."
        )
    return base_url, key


def make_agent(
    name: str,
    description: str,
    instruction: str,
    tools: Optional[list[Any]] = None,
    *,
    model: str = "gpt-5.5",
    agent_class: Optional[Any] = None,
) -> Any:
    """Build a configured google.adk.Agent with all the LiteLlm boilerplate done.

    Returns google.adk.Agent. Pass agent_class to override (testing, custom subclasses).
    """
    try:
        from google.adk import Agent
        from google.adk.models.lite_llm import LiteLlm
    except ImportError as exc:
        raise RuntimeError(
            "make_agent: google.adk not installed. Run `pip install google-adk`."
        ) from exc

    base_url, key = _resolve_litellm()
    AgentClass = agent_class or Agent

    return AgentClass(
        name=name,
        model=LiteLlm(model=_litellm_model_string(model), api_base=base_url, api_key=key),
        description=description,
        instruction=instruction,
        tools=tools or [],
    )


def make_model(model: str = "gpt-5.5") -> Any:
    """Return just the LiteLlm model, useful for advanced cases."""
    try:
        from google.adk.models.lite_llm import LiteLlm
    except ImportError as exc:
        raise RuntimeError("make_model: google.adk not installed.") from exc
    base_url, key = _resolve_litellm()
    return LiteLlm(model=_litellm_model_string(model), api_base=base_url, api_key=key)
