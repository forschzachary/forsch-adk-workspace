"""Hubert backend: stream his persona (SOUL system prompt) on gpt-5.5 via LiteLLM."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from forsch.adk_chat.sse import iter_sse_content


def build_messages(system: str, history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": system}, *history]


async def stream_hubert(client: httpx.AsyncClient, base: str, key: str, model: str,
                        history: list[dict], *, system: str) -> AsyncIterator[str]:
    body = {"model": model, "messages": build_messages(system, history), "stream": True}
    async with client.stream("POST", base.rstrip("/") + "/v1/chat/completions",
                             headers={"Authorization": "Bearer " + key,
                                      "Content-Type": "application/json"},
                             content=json.dumps(body)) as resp:
        resp.raise_for_status()
        buf = ""
        async for chunk in resp.aiter_text():
            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                for tok in iter_sse_content([line]):
                    yield tok
