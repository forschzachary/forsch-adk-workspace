"""Stream an ADK agent's text tokens. Extracted from bridge.py's run loop so the
Chainlit surface and the Discord/CRM surfaces share one path."""

from __future__ import annotations

from collections.abc import AsyncIterator

from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner, RunConfig
from google.genai import types


async def tokens_from_events(events) -> AsyncIterator[str]:
    """Yield text tokens from an ADK run_async() event stream, stopping after the
    final response."""
    async for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    yield part.text
        if event.is_final_response():
            break


async def stream_agent(agent, agent_name, session_service, user_id, session_id, text) -> AsyncIterator[str]:
    """Run one user message through the agent and yield response text tokens."""
    content = types.Content(parts=[types.Part.from_text(text=text)], role="user")
    session = await session_service.get_session(app_name=agent_name, user_id=user_id, session_id=session_id)
    if session is None:
        await session_service.create_session(app_name=agent_name, user_id=user_id, session_id=session_id)
    runner = Runner(
        agent=agent, app_name=agent_name, session_service=session_service,
        artifact_service=InMemoryArtifactService(), memory_service=InMemoryMemoryService(),
        auto_create_session=False,
    )
    mode = RunConfig.model_fields["streaming_mode"].annotation
    cfg = RunConfig(streaming_mode=mode.SSE)
    events = runner.run_async(user_id=user_id, session_id=session_id, new_message=content, run_config=cfg)
    async for tok in tokens_from_events(events):
        yield tok
