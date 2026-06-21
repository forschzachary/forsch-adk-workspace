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


@cl.on_message
async def on_message(message: cl.Message):
    who = cl.user_session.get("who")
    out = cl.Message(content="")
    if who == "hubert":
        hist = cl.user_session.get("history")
        hist.append({"role": "user", "content": message.content})
        async with httpx.AsyncClient(timeout=120) as client:
            acc = ""
            async for tok in stream_hubert(client, _LITE, _KEY, "gpt-5.5", hist, system=_SOUL + _VOICE):
                acc += tok
                await out.stream_token(tok)
        hist.append({"role": "assistant", "content": acc})
    else:  # claude
        client = cl.user_session.get("claude")
        if client is None:
            client = ClaudeSDKClient(options=ClaudeAgentOptions(cwd=_WS, permission_mode="bypassPermissions"))
            await client.connect()
            cl.user_session.set("claude", client)
        await client.query(message.content)
        async for msg in client.receive_response():
            for block in getattr(msg, "content", []) or []:
                ev = map_block(block)
                if not ev:
                    continue
                if ev[0] == "token":
                    await out.stream_token(ev[1])
                elif ev[0] == "tool":
                    async with cl.Step(name=f"tool: {ev[1]}", type="tool") as s:
                        s.input = ev[2]
    await out.update()
