import os
import chainlit as cl
import httpx
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from forsch.adk_chat.hubert import stream_hubert
from forsch.adk_chat.claudewrap import map_block

_TOKEN = os.environ.get("CHAT_TOKEN", "")
_LITE = os.environ.get("LITELLM_BASE", "http://127.0.0.1:4000")
_KEY = os.environ.get("LITELLM_HERMES_KEY", "")
_WS = "/root/.hermes/workspace/adk"
_SOUL = open(os.environ["HUBERT_SOUL_PATH"]).read() if os.environ.get("HUBERT_SOUL_PATH") else "You are Hubert."
_VOICE = ("\n\nChat voice: real texting cadence, mostly lowercase, ASCII punctuation only "
          "(no em dashes or curly quotes), at most one emoji.")

# AskActionMessage timeout (seconds). On timeout the user can still type a reply.
_ASK_TIMEOUT = 600


@cl.header_auth_callback
def auth(headers) -> cl.User | None:
    if _TOKEN and headers.get("x-chat-token") == _TOKEN:
        return cl.User(identifier="zach")
    return None if _TOKEN else cl.User(identifier="zach")


@cl.set_chat_profiles
async def profiles(user):
    return [cl.ChatProfile(name="claude", markdown_description="**Claude** - tool-using coder (full bypass, in the workspace)."),
            cl.ChatProfile(name="hubert", markdown_description="**Hubert** - his persona on gpt-5.5 (SOUL-faithful; not his full runtime).")]


@cl.on_chat_start
async def start():
    cl.user_session.set("who", cl.user_session.get("chat_profile") or "claude")
    cl.user_session.set("history", [])


def _render_ask_user_markdown(question: dict) -> str:
    """Format ONE AskUserQuestion question as readable markdown (header + prompt + hint).

    Options are rendered as clickable buttons separately (see _ask_question), so
    this only produces the text body that sits above the buttons.
    """
    lines = []
    header = (question.get("header") or "").strip()
    prompt = (question.get("question") or "").strip()
    multi = question.get("multi_select", False)
    if header:
        lines.append(f"**{header}**")
    if prompt:
        lines.append(prompt)
    if multi:
        lines.append("")
        lines.append("*Select all that apply (click each), or type your own reply.*")
    else:
        lines.append("")
        lines.append("*Click an option below, or type your own reply.*")
    return "\n".join(lines)


def _option_actions(question: dict) -> list[cl.Action]:
    """Build a clickable cl.Action button per option for one question."""
    actions = []
    for i, opt in enumerate(question.get("options") or []):
        label = (opt.get("label") or "").strip() or f"Option {i + 1}"
        desc = (opt.get("description") or "").strip()
        actions.append(cl.Action(
            name="ask_user_option",
            payload={"label": label, "header": question.get("header", "")},
            label=label,
            tooltip=desc or label,
        ))
    return actions


async def _ask_question(question: dict) -> str | None:
    """Render one AskUserQuestion question as text + clickable option buttons.

    Returns the chosen option label (str) if the user clicks one, or None if they
    let it time out (in which case they can type a reply, which on_message handles).
    """
    actions = _option_actions(question)
    if not actions:
        # No options to click; fall back to a plain readable message.
        await cl.Message(content=_render_ask_user_markdown(question)).send()
        return None
    res = await cl.AskActionMessage(
        content=_render_ask_user_markdown(question),
        actions=actions,
        timeout=_ASK_TIMEOUT,
    ).send()
    if res is None:
        return None
    payload = res.get("payload") or {}
    return payload.get("label") or res.get("label")


async def _run_claude(client, prompt: str, out: cl.Message) -> list[dict]:
    """Send one prompt to Claude, stream the response into `out`, and return any
    AskUserQuestion questions encountered (so the caller can render clickable
    buttons after the turn ends).

    The SDK auto-dismisses AskUserQuestion in bypassPermissions mode and the
    turn ends, so we cannot answer the tool inline. Instead we collect the
    questions and surface them as buttons; a click resubmits as a new message.
    """
    pending: list[dict] = []
    await client.query(prompt)
    async for msg in client.receive_response():
        for block in getattr(msg, "content", []) or []:
            ev = map_block(block)
            if not ev:
                continue
            if ev[0] == "token":
                await out.stream_token(ev[1])
            elif ev[0] == "ask_user":
                pending.extend(ev[1])
            elif ev[0] == "tool":
                async with cl.Step(name=f"tool: {ev[1]}", type="tool") as s:
                    s.input = ev[2]
    await out.update()
    return pending


async def _claude_turn(client, prompt: str):
    """Run a Claude turn and, if it asked questions, render clickable buttons and
    loop on the user's choice so Claude continues from the selection."""
    while True:
        out = cl.Message(content="")
        questions = await _run_claude(client, prompt, out)
        if not questions:
            return
        # Render each question's options as clickable buttons. A click submits
        # the chosen label as the next prompt, continuing the conversation.
        answers: list[str] = []
        for q in questions:
            choice = await _ask_question(q)
            if choice:
                header = (q.get("header") or "").strip()
                answers.append(f"{header}: {choice}" if header else choice)
        if not answers:
            # User did not click anything (timed out); they can type a reply,
            # which on_message will handle as a normal message. Stop the loop.
            return
        prompt = "; ".join(answers)


@cl.action_callback("ask_user_option")
async def _on_ask_user_option(action: cl.Action):
    """No-op: AskActionMessage consumes the click directly. This handler exists
    so Chainlit registers the action name; the value is returned by .send()."""
    return None


@cl.on_message
async def on_message(message: cl.Message):
    who = cl.user_session.get("who")
    if who == "hubert":
        out = cl.Message(content="")
        hist = cl.user_session.get("history")
        hist.append({"role": "user", "content": message.content})
        async with httpx.AsyncClient(timeout=120) as client:
            acc = ""
            async for tok in stream_hubert(client, _LITE, _KEY, "gpt-5.5", hist, system=_SOUL + _VOICE):
                acc += tok
                await out.stream_token(tok)
        hist.append({"role": "assistant", "content": acc})
        await out.update()
    else:  # claude
        client = cl.user_session.get("claude")
        if client is None:
            client = ClaudeSDKClient(options=ClaudeAgentOptions(cwd=_WS, permission_mode="bypassPermissions"))
            await client.connect()
            cl.user_session.set("claude", client)
        await _claude_turn(client, message.content)
