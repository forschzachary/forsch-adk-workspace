"""Clean Gradio sidecar for ADK agents.

Mounted at /chat by http.py. This is an operator surface: pick an agent, send a
message, watch tool calls, keep the chrome quiet.
"""

from __future__ import annotations

import json
import time
from typing import Any

import gradio as gr

from forsch.adk_bridge.run import stream_agent_structured
from forsch.adk_bridge.runtime import get_runtime

CSS = """
:root {
  --ff-bg: #f7f3ea;
  --ff-panel: #fffdf7;
  --ff-ink: #241f1a;
  --ff-muted: #6d655d;
  --ff-line: #ded6c8;
  --ff-accent: #8a5f2d;
  --ff-accent-soft: #efe2cf;
  --ff-ok: #287a55;
}
.gradio-container {
  max-width: none !important;
  min-height: 100vh;
  background:
    radial-gradient(circle at 20% 0%, rgba(138, 95, 45, 0.10), transparent 28rem),
    var(--ff-bg) !important;
  color: var(--ff-ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
#ff-sidecar {
  max-width: 1180px;
  margin: 0 auto;
  padding: 22px;
}
#ff-hero {
  border: 1px solid var(--ff-line);
  border-radius: 22px;
  padding: 18px 20px;
  background: rgba(255, 253, 247, 0.82);
  box-shadow: 0 18px 60px rgba(36, 31, 26, 0.08);
}
#ff-hero h1 {
  margin: 0;
  font-size: 28px;
  line-height: 32px;
  letter-spacing: -0.04em;
}
#ff-hero p {
  margin: 6px 0 0;
  color: var(--ff-muted);
  font-size: 15px;
}
.ff-status-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}
.ff-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--ff-line);
  border-radius: 999px;
  padding: 6px 10px;
  background: #fffaf0;
  color: var(--ff-muted);
  font-size: 13px;
  line-height: 16px;
}
.ff-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ff-ok);
}
#ff-workspace {
  margin-top: 14px;
  align-items: stretch;
}
#ff-rail, #ff-compose-card, #ff-chat-card {
  border: 1px solid var(--ff-line);
  border-radius: 20px;
  background: rgba(255, 253, 247, 0.92);
  box-shadow: 0 12px 38px rgba(36, 31, 26, 0.06);
}
#ff-rail {
  padding: 14px;
}
#ff-rail .wrap {
  gap: 12px;
}
#ff-compose-card {
  padding: 14px;
}
#ff-chat-card {
  padding: 8px 12px 12px;
}
.ff-section-title {
  font-size: 12px;
  line-height: 16px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ff-muted);
  font-weight: 700;
  margin-bottom: 8px;
}
.ff-note {
  color: var(--ff-muted);
  font-size: 13px;
  line-height: 18px;
}
#ff-quick .secondary, #ff-quick button {
  border-radius: 14px !important;
  justify-content: flex-start !important;
  min-height: 36px !important;
}
#ff-run-btn button, #ff-clear-btn button {
  border-radius: 14px !important;
  min-height: 40px !important;
}
#ff-run-btn button {
  background: var(--ff-ink) !important;
  color: white !important;
  border-color: var(--ff-ink) !important;
}
#ff-chatbot {
  border: 0 !important;
  background: transparent !important;
}
#ff-chatbot .message {
  border-radius: 16px !important;
}
#ff-chatbot .bot, #ff-chatbot .assistant {
  background: #fffaf0 !important;
}
#ff-chatbot .user {
  background: #efe2cf !important;
}
textarea, input, select {
  border-radius: 14px !important;
}
#ff-prompt textarea {
  min-height: 128px !important;
  font-size: 15px !important;
  line-height: 21px !important;
}
footer { display: none !important; }
"""

PROMPTS = {
    "Health check": "Run your smallest useful health check. Tell me what passed, what failed, and the next safe move.",
    "Explain this agent": "Explain what this agent is responsible for, what tools it has, and where the risky assumptions are.",
    "Runbook": "Give me a short operator runbook for this agent: normal path, failure signals, and recovery steps.",
    "Eval idea": "Propose three small eval cases for this agent. Keep them concrete and easy to automate.",
}


def _agent_choices() -> list[str]:
    rt = get_runtime()
    return sorted(rt.agents.keys())


def _default_agent(choices: list[str]) -> str:
    if "ops" in choices:
        return "ops"
    return choices[0] if choices else ""


def _runtime_summary(agent_name: str) -> str:
    choices = _agent_choices()
    active = agent_name or _default_agent(choices)
    return (
        "<div class='ff-status-row'>"
        f"<span class='ff-chip'><span class='ff-dot'></span>{len(choices)} agents loaded</span>"
        f"<span class='ff-chip'>active: {active or 'none'}</span>"
        "<span class='ff-chip'>surface: gradio sidecar</span>"
        "</div>"
    )


def _apply_prompt(label: str) -> str:
    return PROMPTS.get(label, "")


async def _send_message(
    message: str,
    agent_name: str,
    history: list[dict[str, Any]] | None,
):
    """Stream one operator message through an ADK agent.

    Returns OpenAI-style message dicts for Gradio Chatbot. Tool calls are exposed
    as metadata so Gradio renders them as collapsible thought panels.
    """
    history = list(history or [])
    text = (message or "").strip()
    if not text:
        yield history, "", "Write a message first. Ambitious otherwise."
        return

    rt = get_runtime()
    agent = rt.agents.get(agent_name)
    if agent is None:
        history.append({"role": "assistant", "content": f"Agent '{agent_name}' is not loaded."})
        yield history, message, "Agent unavailable."
        return

    session_id = f"gradio:{agent_name}:{int(time.time())}"
    history.append({"role": "user", "content": text})
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": ""}
    history.append(assistant_msg)

    full_text = ""
    tools: list[dict[str, Any]] = []

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
                yield history, "", f"skipped malformed text event: {type(data).__name__}"
                continue
            full_text += data
            assistant_msg["content"] = full_text
            if tools:
                assistant_msg["metadata"] = _metadata(tools)
            yield history, "", _status(agent_name, tools, running=True)
        elif kind == "tool_call":
            if not isinstance(data, dict):
                yield history, "", f"skipped malformed tool call: {type(data).__name__}"
                continue
            tools.append(
                {
                    "name": data.get("name", "tool"),
                    "args": data.get("args", {}),
                    "result": None,
                    "status": "pending",
                    "started": time.time(),
                }
            )
            assistant_msg["content"] = full_text or "working..."
            assistant_msg["metadata"] = _metadata(tools)
            yield history, "", _status(agent_name, tools, running=True)
        elif kind == "tool_result":
            if not isinstance(data, dict):
                yield history, "", f"skipped malformed tool result: {type(data).__name__}"
                continue
            for tool in reversed(tools):
                if tool["status"] == "pending":
                    tool["status"] = "done"
                    tool["result"] = data.get("result", {})
                    tool["duration"] = time.time() - tool["started"]
                    break
            assistant_msg["content"] = full_text or "working..."
            assistant_msg["metadata"] = _metadata(tools)
            yield history, "", _status(agent_name, tools, running=True)

    assistant_msg["content"] = full_text or "No visible response returned."
    if tools:
        assistant_msg["metadata"] = _metadata(tools)
    yield history, "", _status(agent_name, tools, running=False)


def _metadata(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Build Gradio metadata for the latest tool call.

    Gradio shows one metadata block per message. Keep it compact: latest tool in
    the title, full tool trace in the log.
    """
    latest = tools[-1]
    log_lines = []
    for idx, tool in enumerate(tools, start=1):
        log_lines.append(f"{idx}. {tool['name']}")
        log_lines.append(f"   args: {_compact_json(tool.get('args'))}")
        if tool.get("result") is not None:
            log_lines.append(f"   result: {_compact_json(tool.get('result'))}")
    return {
        "title": f"tool: {latest['name']}",
        "id": latest["name"],
        "log": "\n".join(log_lines),
        "status": latest.get("status", "done"),
        "duration": latest.get("duration"),
    }


def _compact_json(value: Any) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        rendered = str(value)
    return rendered if len(rendered) <= 700 else rendered[:700] + "..."


def _status(agent_name: str, tools: list[dict[str, Any]], running: bool) -> str:
    state = "running" if running else "ready"
    pending = sum(1 for tool in tools if tool.get("status") == "pending")
    done = sum(1 for tool in tools if tool.get("status") == "done")
    return f"{state} · agent {agent_name} · tools {done} done / {pending} pending"


def _clear_chat():
    return [], "", "ready"


def build_gradio_app() -> gr.Blocks:
    """Create the Gradio Blocks app for the ADK sidecar."""
    choices = _agent_choices()
    default_agent = _default_agent(choices)

    with gr.Blocks(title="ADK Sidecar", elem_id="ff-sidecar") as demo:
        # Gradio 6 moved Blocks(css=...) to launch(); this app is mounted, not
        # launched, so inject the stylesheet directly.
        gr.HTML(f"<style>{CSS}</style>", visible=False)
        with gr.Column(elem_id="ff-hero"):
            gr.Markdown("# ADK Sidecar")
            gr.Markdown("Focused operator chat for the agent graph. Pick an agent, run a task, inspect the tool trace.")
            runtime_html = gr.HTML(_runtime_summary(default_agent))

        with gr.Row(elem_id="ff-workspace"):
            with gr.Column(scale=1, min_width=260, elem_id="ff-rail"):
                gr.Markdown("<div class='ff-section-title'>Agent</div>")
                agent_dd = gr.Dropdown(
                    choices=choices,
                    value=default_agent,
                    label="",
                    interactive=True,
                    container=False,
                )
                gr.Markdown(
                    "<div class='ff-note'>Use this as the fast interaction layer. Durable config stays in the graph/control plane.</div>"
                )
                gr.Markdown("<div class='ff-section-title'>Quick prompts</div>")
                quick = gr.Radio(
                    choices=list(PROMPTS.keys()),
                    label="",
                    container=False,
                    elem_id="ff-quick",
                )
                status = gr.Textbox(
                    value="ready",
                    label="Status",
                    interactive=False,
                    lines=2,
                )

            with gr.Column(scale=3):
                with gr.Column(elem_id="ff-chat-card"):
                    chatbot = gr.Chatbot(
                        label="Conversation",
                        height=520,
                        elem_id="ff-chatbot",
                    )
                with gr.Column(elem_id="ff-compose-card"):
                    prompt = gr.Textbox(
                        label="Message",
                        placeholder="Ask the selected agent to run a focused check, explain itself, or draft an eval...",
                        lines=5,
                        elem_id="ff-prompt",
                    )
                    with gr.Row():
                        send = gr.Button("Run", variant="primary", elem_id="ff-run-btn")
                        clear = gr.Button("Clear", elem_id="ff-clear-btn")

        quick.change(_apply_prompt, inputs=quick, outputs=prompt)
        agent_dd.change(_runtime_summary, inputs=agent_dd, outputs=runtime_html)
        send.click(_send_message, inputs=[prompt, agent_dd, chatbot], outputs=[chatbot, prompt, status])
        prompt.submit(_send_message, inputs=[prompt, agent_dd, chatbot], outputs=[chatbot, prompt, status])
        clear.click(_clear_chat, outputs=[chatbot, prompt, status])

    return demo
