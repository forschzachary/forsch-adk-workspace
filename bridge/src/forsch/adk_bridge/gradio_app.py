"""Modular Gradio sidecar for ADK agents.

Mounted at /chat by http.py. This is the golden-template chat surface: persistent
agent chat, compact operator controls, theme/copy isolated in sidecar_config.py.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import gradio as gr

from forsch.adk_bridge.run import stream_agent_structured
from forsch.adk_bridge.runtime import get_runtime
from forsch.adk_bridge.sidecar_config import BRAND, ENTER_TO_SEND_JS, PROMPTS, build_css


# ── Runtime helpers ──────────────────────────────────────────────────────────

def _agent_choices() -> list[str]:
    return sorted(get_runtime().agents.keys())


def _default_agent(choices: list[str]) -> str:
    preferred = BRAND.get("default_agent")
    return preferred if preferred in choices else (choices[0] if choices else "")


def _new_session_id(agent_name: str) -> str:
    safe_agent = (agent_name or "agent").replace(":", "-")
    return f"gradio:{safe_agent}:{uuid.uuid4().hex}"


def _normalize_session_id(agent_name: str, session_id: str | None) -> str:
    return session_id if session_id and session_id.startswith("gradio:") else _new_session_id(agent_name)


def _short_session(session_id: str | None) -> str:
    return (session_id or "")[-8:] or "new"


def _runtime_summary(agent_name: str, session_id: str | None = None) -> str:
    choices = _agent_choices()
    active = agent_name or _default_agent(choices)
    return (
        "<div class='ff-status-row'>"
        f"<span class='ff-chip'><span class='ff-dot'></span>{len(choices)} agents loaded</span>"
        f"<span class='ff-chip'>active: {active or 'none'}</span>"
        f"<span class='ff-chip'>session: {_short_session(session_id)}</span>"
        f"<span class='ff-chip'>surface: {BRAND['surface']}</span>"
        "</div>"
    )


def _status(agent_name: str, tools: list[dict[str, Any]], running: bool, session_id: str) -> str:
    state = "running" if running else "ready"
    pending = sum(1 for tool in tools if tool.get("status") == "pending")
    done = sum(1 for tool in tools if tool.get("status") == "done")
    return (
        f"{state} · agent {agent_name} · session {_short_session(session_id)} "
        f"· tools {done} done / {pending} pending"
    )


# ── State helpers ────────────────────────────────────────────────────────────

def _apply_prompt(label: str | None, current_prompt: str) -> str:
    if label is None:
        return current_prompt or ""
    return PROMPTS.get(label, current_prompt or "")


def _select_agent(agent_name: str):
    session_id = _new_session_id(agent_name)
    return (
        _runtime_summary(agent_name, session_id),
        [],
        "ready · new agent session",
        session_id,
        "",
        _trace_text([]),
    )


def _clear_chat(agent_name: str):
    session_id = _new_session_id(agent_name)
    return [], "", "ready · new session", session_id, "", _trace_text([])


def _reuse_last_prompt(last_prompt: str):
    return last_prompt or ""


# ── Chat execution ───────────────────────────────────────────────────────────

async def _send_message(
    message: str,
    agent_name: str,
    history: list[dict[str, Any]] | None,
    session_id: str,
):
    """Stream one operator message through an ADK agent."""
    history = list(history or [])
    text = (message or "").strip()
    if not text:
        yield history, "", "Write a message first. Ambitious otherwise.", text, _trace_text([])
        return

    rt = get_runtime()
    agent = rt.agents.get(agent_name)
    if agent is None:
        history.append({"role": "assistant", "content": f"Agent '{agent_name}' is not loaded."})
        yield history, message, "Agent unavailable.", text, _trace_text([])
        return

    session_id = _normalize_session_id(agent_name, session_id)
    history.append({"role": "user", "content": text})
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": ""}
    history.append(assistant_msg)

    full_text = ""
    tools: list[dict[str, Any]] = []
    trace = _trace_text(tools)

    async for kind, data in stream_agent_structured(
        agent,
        agent_name,
        rt.session_service,
        user_id="gradio-user",
        session_id=session_id,
        text=text,
    ):
        if kind == "text":
            if not isinstance(data, str):
                yield history, "", f"skipped malformed text event: {type(data).__name__}", text, trace
                continue
            full_text += data
            assistant_msg["content"] = full_text
            if tools:
                assistant_msg["metadata"] = _metadata(tools, trace)
            yield history, "", _status(agent_name, tools, True, session_id), text, trace
        elif kind == "tool_call":
            if not isinstance(data, dict):
                yield history, "", f"skipped malformed tool call: {type(data).__name__}", text, trace
                continue
            tools.append({
                "name": data.get("name", "tool"),
                "args": data.get("args", {}),
                "result": None,
                "status": "pending",
                "started": time.time(),
            })
            trace = _trace_text(tools)
            assistant_msg["content"] = full_text or "working..."
            assistant_msg["metadata"] = _metadata(tools, trace)
            yield history, "", _status(agent_name, tools, True, session_id), text, trace
        elif kind == "tool_result":
            if not isinstance(data, dict):
                yield history, "", f"skipped malformed tool result: {type(data).__name__}", text, trace
                continue
            for tool in reversed(tools):
                if tool["status"] == "pending":
                    tool["status"] = "done"
                    tool["result"] = data.get("result", {})
                    tool["duration"] = time.time() - tool["started"]
                    break
            trace = _trace_text(tools)
            assistant_msg["content"] = full_text or "working..."
            assistant_msg["metadata"] = _metadata(tools, trace)
            yield history, "", _status(agent_name, tools, True, session_id), text, trace

    assistant_msg["content"] = full_text or "No visible response returned."
    if tools:
        assistant_msg["metadata"] = _metadata(tools, trace)
    yield history, "", _status(agent_name, tools, False, session_id), text, trace


async def _regenerate_last(agent_name: str, history: list[dict[str, Any]] | None, session_id: str, last_prompt: str):
    history = list(history or [])
    if not last_prompt:
        yield history, "", "nothing to regenerate", last_prompt, _trace_text([])
        return
    if history and history[-1].get("role") == "assistant":
        history.pop()
    if history and history[-1].get("role") == "user":
        history.pop()
    async for update in _send_message(last_prompt, agent_name, history, session_id):
        yield update


# ── Rendering helpers ────────────────────────────────────────────────────────

def _metadata(tools: list[dict[str, Any]], trace: str | None = None) -> dict[str, Any]:
    latest = tools[-1]
    meta: dict[str, Any] = {
        "title": f"tool: {latest['name']}",
        "id": latest["name"],
        "log": trace if trace is not None else _trace_text(tools),
        "status": latest.get("status", "done"),
    }
    if latest.get("duration") is not None:
        meta["duration"] = latest["duration"]
    return meta


def _trace_text(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return "No tool calls yet."
    lines: list[str] = []
    for idx, tool in enumerate(tools, start=1):
        duration = ""
        if tool.get("duration") is not None:
            duration = f" · {tool['duration']:.2f}s"
        lines.append(f"{idx}. {tool['name']} [{tool.get('status', 'done')}]{duration}")
        lines.append(f"   args: {_compact_json(tool.get('args'))}")
        if tool.get("result") is not None:
            lines.append(f"   result: {_compact_json(tool.get('result'))}")
    return "\n".join(lines)


def _compact_json(value: Any) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        rendered = str(value)
    if len(rendered) <= 700:
        return rendered
    return json.dumps(
        {"truncated": True, "chars": len(rendered), "preview": rendered[:650]},
        ensure_ascii=False,
    )


# ── UI assembly ──────────────────────────────────────────────────────────────

def build_gradio_app() -> gr.Blocks:
    """Create the Gradio Blocks app for the ADK sidecar."""
    choices = _agent_choices()
    default_agent = _default_agent(choices)
    initial_session_id = _new_session_id(default_agent)

    with gr.Blocks(title=BRAND["title"], elem_id="ff-sidecar") as demo:
        gr.HTML(f"<style>{build_css()}</style>", visible=False)

        with gr.Column(elem_id="ff-hero"):
            gr.Markdown(f"# {BRAND['title']}")
            gr.Markdown(BRAND["subtitle"])
            runtime_html = gr.HTML(_runtime_summary(default_agent, initial_session_id))

        session_state = gr.State(initial_session_id)
        last_prompt_state = gr.State("")

        with gr.Row(elem_id="ff-workspace"):
            with gr.Column(scale=1, min_width=260, elem_id="ff-rail"):
                gr.Markdown("<div class='ff-section-title'>Agent</div>")
                agent_dd = gr.Dropdown(choices=choices, value=default_agent, label="", interactive=True, container=False)
                gr.Markdown(f"<div class='ff-note'>{BRAND['agent_note']}</div>")
                gr.Markdown("<div class='ff-section-title'>Quick prompts</div>")
                quick = gr.Radio(choices=list(PROMPTS.keys()), label="", container=False, elem_id="ff-quick")
                status = gr.Textbox(value="ready", label="Status", interactive=False, lines=2)
                with gr.Row():
                    new_chat = gr.Button("New session")
                    reuse = gr.Button("Reuse last")

            with gr.Column(scale=3):
                with gr.Column(elem_id="ff-chat-card"):
                    chatbot = gr.Chatbot(label="Conversation", height=520, elem_id="ff-chatbot")
                with gr.Column(elem_id="ff-compose-card"):
                    prompt = gr.Textbox(label="Message", placeholder=BRAND["prompt_placeholder"], lines=5, elem_id="ff-prompt")
                    with gr.Row():
                        send = gr.Button("Run", variant="primary", elem_id="ff-run-btn")
                        stop = gr.Button("Stop", elem_id="ff-stop-btn")
                        regen = gr.Button("Regenerate")
                        clear = gr.Button("Clear", elem_id="ff-clear-btn")
                with gr.Accordion("Tool trace", open=False, elem_id="ff-trace-card"):
                    trace_box = gr.Textbox(value=_trace_text([]), label="Latest run", interactive=False, lines=9, elem_id="ff-tool-trace")

        run_event = send.click(
            _send_message,
            inputs=[prompt, agent_dd, chatbot, session_state],
            outputs=[chatbot, prompt, status, last_prompt_state, trace_box],
        )
        submit_event = prompt.submit(
            _send_message,
            inputs=[prompt, agent_dd, chatbot, session_state],
            outputs=[chatbot, prompt, status, last_prompt_state, trace_box],
        )
        regen_event = regen.click(
            _regenerate_last,
            inputs=[agent_dd, chatbot, session_state, last_prompt_state],
            outputs=[chatbot, prompt, status, last_prompt_state, trace_box],
        )

        quick.change(_apply_prompt, inputs=[quick, prompt], outputs=prompt)
        agent_dd.change(
            _select_agent,
            inputs=agent_dd,
            outputs=[runtime_html, chatbot, status, session_state, last_prompt_state, trace_box],
        )
        new_chat.click(_clear_chat, inputs=agent_dd, outputs=[chatbot, prompt, status, session_state, last_prompt_state, trace_box])
        reuse.click(_reuse_last_prompt, inputs=last_prompt_state, outputs=prompt)
        clear.click(_clear_chat, inputs=agent_dd, outputs=[chatbot, prompt, status, session_state, last_prompt_state, trace_box])
        stop.click(None, cancels=[run_event, submit_event, regen_event])

    return demo
