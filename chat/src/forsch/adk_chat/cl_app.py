import hmac
import json
import os
import chainlit as cl
from chainlit.input_widget import Select
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from forsch.adk_chat.mimo_harness import run_hubert
from forsch.adk_chat.claudewrap import map_block
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

_TOKEN = os.environ.get("CHAT_TOKEN", "")
_WS = os.environ.get("FORSCH_ADK_WORKSPACE", "/root/.hermes/workspace/adk")
_HUBERT_MODEL = os.environ.get("HUBERT_MODEL", "ollama-cloud/glm-5.2")
_HUBERT_TIMEOUT = float(os.environ.get("HUBERT_TIMEOUT", "240"))

# AskActionMessage timeout (seconds). On timeout the user can still type a reply.
_ASK_TIMEOUT = 600

# --- model picker: the chat exposes every model mimocode is configured for ---
_MIMO_CONFIG = os.environ.get("MIMOCODE_CONFIG") or os.path.expanduser("~/.config/mimocode/mimocode.jsonc")


def _available_models() -> list[str]:
    """provider/model ids mimocode can use, parsed from its config — powers the chat picker."""
    models: list[str] = []
    try:
        with open(_MIMO_CONFIG) as f:
            raw = "\n".join(ln for ln in f.read().splitlines() if not ln.lstrip().startswith("//"))
        cfg = json.loads(raw)
        for prov, pdata in (cfg.get("provider") or {}).items():
            for mid in ((pdata or {}).get("models") or {}).keys():
                models.append(f"{prov}/{mid}")
    except Exception:
        pass
    # keep the configured default selectable even if it routes via a built-in provider (e.g. Xiaomi)
    if _HUBERT_MODEL not in models:
        models.insert(0, _HUBERT_MODEL)
    return models or [_HUBERT_MODEL]


_MODELS = _available_models()


async def _send_model_settings() -> None:
    """Render the model dropdown and seed the session's model (Hubert/mimocode profile)."""
    initial = _HUBERT_MODEL if _HUBERT_MODEL in _MODELS else _MODELS[0]
    cl.user_session.set("model", initial)
    await cl.ChatSettings([
        Select(id="model", label="Hubert model (mimocode)", values=_MODELS,
               initial_index=_MODELS.index(initial)),
    ]).send()


# --- chat persistence: Chainlit history sidebar (session selection) + resume (message-history continuity) ---
_HISTORY_DB = os.environ.get("CHAINLIT_PG_URL") or "sqlite+aiosqlite:////root/.hermes/workspace/adk/chat/data/chat_history.db"


@cl.data_layer
def _get_data_layer():
    return SQLAlchemyDataLayer(conninfo=_HISTORY_DB)


@cl.on_chat_resume
async def resume(thread):
    cl.user_session.set("who", cl.user_session.get("chat_profile") or "claude")
    hist = []
    for step in (thread.get("steps") or []):
        t = step.get("type") or ""
        content = step.get("output") or ""
        if t == "user_message" and content:
            hist.append({"role": "user", "content": content})
        elif t in ("assistant_message", "llm") and content:
            hist.append({"role": "assistant", "content": content})
    cl.user_session.set("history", hist)
    await _send_model_settings()



@cl.header_auth_callback
def auth(headers) -> cl.User | None:
    # Fail CLOSED: with no configured CHAT_TOKEN, nobody authenticates. This surface
    # can run the full-bypass Claude profile, so an empty token must NOT grant a default
    # user (the old `else cl.User("zach")` authenticated every anonymous request).
    # Constant-time compare to avoid the timing side-channel the bridge already avoids.
    if _TOKEN and hmac.compare_digest(headers.get("x-chat-token", "") or "", _TOKEN):
        return cl.User(identifier="zach")
    return None


@cl.set_chat_profiles
async def profiles(user):
    return [cl.ChatProfile(name="claude", markdown_description="**Claude** - tool-using coder (full bypass, in the workspace)."),
            cl.ChatProfile(name="hubert", markdown_description="**Hubert** - the real mimocode harness on GLM 5.2 (Ollama Cloud); builds agents with tool calls inline.")]


@cl.on_chat_start
async def start():
    cl.user_session.set("who", cl.user_session.get("chat_profile") or "claude")
    cl.user_session.set("history", [])
    await _send_model_settings()


@cl.on_settings_update
async def _on_settings(settings):
    m = (settings or {}).get("model")
    if m:
        cl.user_session.set("model", m)


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
        await out.send()  # must exist before stream_token() appends to it
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
        await out.send()
        session_id = cl.user_session.get("mimo_session")
        new_session, error = await run_hubert(
            message.content, out, workdir=_WS,
            session_id=session_id,
            model=cl.user_session.get("model") or _HUBERT_MODEL,
            timeout=_HUBERT_TIMEOUT,
        )
        if new_session:
            cl.user_session.set("mimo_session", new_session)
        if error:
            await cl.Message(content=f"Hubert error: {error}").send()
    else:  # claude
        client = cl.user_session.get("claude")
        if client is None:
            client = ClaudeSDKClient(options=ClaudeAgentOptions(cwd=_WS, permission_mode="bypassPermissions"))
            await client.connect()
            cl.user_session.set("claude", client)
        await _claude_turn(client, message.content)
