"""Stream an ADK agent's text tokens. Extracted from bridge.py's run loop so the
Chainlit surface and the Discord/CRM surfaces share one path."""

from __future__ import annotations

from collections.abc import AsyncIterator

from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner, RunConfig
from google.genai import types

from forsch.adk_bridge.gateway.render import _visible_parts_text


async def tokens_from_events(events) -> AsyncIterator[str]:
    """Yield user-visible text tokens (reasoning/thought parts EXCLUDED) from an ADK
    run_async() event stream, stopping after the final response."""
    streamed = False
    async for event in events:
        final = event.is_final_response()
        if event.content and event.content.parts:
            visible = _visible_parts_text(event.content.parts)
            if getattr(event, "partial", False):
                if visible:
                    streamed = True
                    yield visible
            elif final and not streamed:
                # Non-streaming run: the final event carries the only text. In a
                # streaming run the final event re-sends the FULL aggregate, which we
                # skip (deltas already streamed) to avoid doubling the reply.
                if visible:
                    yield visible
        if final:
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


async def stream_agent_structured(
    agent, agent_name, session_service, user_id, session_id, text
) -> AsyncIterator[tuple[str, str | dict]]:
    """Run one user message through the agent, yielding (kind, data) tuples.

    Yields:
        ("text", str)          — visible text delta
        ("tool_call", dict)    — {name, args}
        ("tool_result", dict)  — {name, result}
    """
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
    streamed_text = False
    async for event in events:
        final = event.is_final_response()
        if event.content and event.content.parts:
            for p in event.content.parts:
                fc = getattr(p, "function_call", None)
                fr = getattr(p, "function_response", None)
                if fc is not None:
                    yield ("tool_call", {
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                    })
                elif fr is not None:
                    yield ("tool_result", {
                        "name": fr.name,
                        "result": dict(fr.response) if fr.response else {},
                    })
                else:
                    visible = (
                        getattr(p, "text", "")
                        if not getattr(p, "thought", False)
                        else ""
                    )
                    if getattr(event, "partial", False) and visible:
                        streamed_text = True
                        yield ("text", visible)
                    elif final and not streamed_text and visible:
                        yield ("text", visible)
        if final:
            break
