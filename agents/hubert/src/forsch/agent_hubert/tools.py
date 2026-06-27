"""Hubert orchestrator tools — backed by shared graph_tools module."""

from __future__ import annotations

import logging
from typing import Any

from forsch.adk_components.tools.graph_tools import (
    get_factory_status as get_factory_status,
    get_graph_overview as get_graph_overview,
    manage_cluster as manage_cluster,
)

logger = logging.getLogger(__name__)


def route_to_agent_logic_specialist(task_description: str) -> dict[str, Any]:
    """Route a task to the Agent·Logic specialist.

    Uses ADK's InMemoryRunner to spin up the specialist agent, send it the
    task, and return its response as a JSON-serialisable dict.
    """
    try:
        from forsch.agent_agent_logic_specialist.agent import root_agent
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        runner = InMemoryRunner(agent=root_agent, app_name="hubert-delegation")
        runner.auto_create_session = True
        user_id = "hubert"
        session_id = "agent-logic-delegation"
        new_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=task_description)],
        )

        response_text = ""
        for event in runner.run(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text

        if not response_text:
            return {
                "status": "error",
                "message": "Agent·Logic specialist returned no response",
                "task": task_description,
            }

        return {
            "status": "ok",
            "response": response_text,
            "task": task_description,
        }

    except Exception as e:
        logger.exception("Agent·Logic specialist delegation failed")
        return {
            "status": "error",
            "message": str(e),
            "task": task_description,
        }
