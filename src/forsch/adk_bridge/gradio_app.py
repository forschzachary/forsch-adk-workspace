"""Gradio chat surface for ADK agents — mounted alongside Chainlit in the bridge.

Uses the shared runtime (get_runtime) so agents and sessions are identical
across Chainlit, Discord, CRM, and Gradio. Tool calls render as collapsible
metadata "thoughts" (title + log + status spinner).
"""

from __future__ import annotations

import json
import time
from typing import Union

import gradio as gr

from forsch.adk_bridge.runtime import get_runtime
from forsch.adk_bridge.run import stream_agent_structured


# ── Gradio chat function ────────────────────────────────────────────────────

async def chat_fn(message: str, history: list, agent_name: str):
    """Gradio ChatInterface fn — streams ADK agent response with tool viz.

    Yields gr.ChatMessage objects. Tool calls render as metadata "thoughts"
    (collapsible accordions with title, log, and status spinner).
    """
    rt = get_runtime()
    agent = rt.agents.get(agent_name)
    if agent is None:
        yield gr.ChatMessage(role="assistant", content=f"Agent '{agent_name}' not found.")
        return

    session_id = f"gradio:{agent_name}:{int(time.time())}"
    full_text = ""
    tool_thoughts: list[dict] = []  # {id, title, log, status}

    async for kind, data in stream_agent_structured(
        agent, agent_name, rt.session_service,
        user_id="gradio-user", session_id=session_id, text=message,
    ):
        if kind == "text":
            assert isinstance(data, str)
            full_text += data
            msg = gr.ChatMessage(role="assistant", content=full_text)
            if tool_thoughts:
                msg.metadata = _build_metadata(tool_thoughts)
            yield msg
        elif kind == "tool_call":
            assert isinstance(data, dict)
            tid = len(tool_thoughts)
            tool_thoughts.append({
                "id": tid,
                "title": f"🔧 {data['name']}",
                "log": f"args: {json.dumps(data['args'])}",
                "status": "pending",
            })
            msg = gr.ChatMessage(role="assistant", content=full_text or "…")
            msg.metadata = _build_metadata(tool_thoughts)
            yield msg
        elif kind == "tool_result":
            assert isinstance(data, dict)
            for t in tool_thoughts:
                if t["status"] == "pending":
                    t["status"] = "done"
                    t["log"] += f" → {json.dumps(data['result'])}"
                    break
            msg = gr.ChatMessage(role="assistant", content=full_text or "…")
            msg.metadata = _build_metadata(tool_thoughts)
            yield msg

    # Final message
    msg = gr.ChatMessage(role="assistant", content=full_text)
    if tool_thoughts:
        msg.metadata = _build_metadata(tool_thoughts)
    yield msg


def _build_metadata(thoughts: list[dict]) -> dict:
    """Build a nested metadata dict from tool thoughts.

    Gradio's MetadataDict supports: title, id, parent_id, log, duration, status.
    We use the first thought as the root with nested children.
    """
    if not thoughts:
        return {}
    root = thoughts[0]
    meta: dict = {
        "title": root["title"],
        "id": root["id"],
        "log": root.get("log", ""),
        "status": root.get("status", "done"),
    }
    return meta


# ── Build Gradio UI ─────────────────────────────────────────────────────────

def build_gradio_app() -> gr.Blocks:
    """Create the Gradio Blocks app with ChatInterface and agent dropdown."""
    rt = get_runtime()
    agent_choices = list(rt.agents.keys())
    default_agent = agent_choices[0] if agent_choices else ""

    with gr.Blocks(title="ADK Chat (Gradio)") as demo:
        gr.Markdown("# ADK Chat — Gradio")
        gr.Markdown(
            "Streaming chat with ADK agents. "
            "Tool calls render as collapsible metadata thoughts below the message."
        )

        agent_dd = gr.Dropdown(
            choices=agent_choices,
            value=default_agent,
            label="Agent",
            interactive=True,
        )

        chat = gr.ChatInterface(
            fn=chat_fn,
            chatbot=gr.Chatbot(height=500),
            additional_inputs=[agent_dd],
            title="",
            description="",
        )

    return demo
