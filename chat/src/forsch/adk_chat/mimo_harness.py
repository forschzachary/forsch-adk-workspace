"""Run the real mimocode harness (Hubert) and stream its run into Chainlit.

`mimo run --format json` emits newline-delimited JSON events on stdout:
  {"type":"text",        "part":{"text":"..."}}     assistant text (deltas, appended)
  {"type":"step_start"|"step_finish", "part":{...}}  turn boundaries (+ tokens/cost)
  {"type":"error",       "error":{...}}              provider/model error
  tool events: the type contains "tool", or a tool-name field is present

Text is streamed token-by-token into the message; each tool call is rendered as a
Chainlit Step (the run inspection). Tool/error detection mirrors the proven
forsch.adk_components.patterns.mimo_stream_runner heuristics, kept self-contained
here so the chat package has no cross-package import.

Set HUBERT_DEBUG=1 to log unrecognized + tool events to stderr (the adk-chat
journal) so the Step mapping can be refined against live data.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import chainlit as cl

_DEBUG = os.environ.get("HUBERT_DEBUG") == "1"
_TOOL_NAME_KEYS = ("tool", "toolName", "tool_name", "name")
_DETAIL_KEYS = ("input", "args", "arguments", "result", "output", "detail", "details")
_ID_KEYS = ("callID", "toolCallId", "tool_call_id", "id")


def _log(*a: Any) -> None:
    if _DEBUG:
        print("[hubert]", *a, file=sys.stderr, flush=True)


def _preview(value: Any, limit: int = 800) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        s = value
    else:
        try:
            s = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            s = str(value)
    s = s.strip()
    return s if len(s) <= limit else s[:limit] + " …"


def _tool_name(evt: dict, part: dict) -> str:
    for src in (evt, part):
        for key in _TOOL_NAME_KEYS:
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:120]
    for src in (evt, part):
        for key in ("call", "toolCall", "tool_call"):
            v = src.get(key)
            if isinstance(v, dict):
                fn = v.get("function")
                if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                    return fn["name"].strip()[:120]
                for k in ("name", "toolName", "tool_name"):
                    n = v.get(k)
                    if isinstance(n, str) and n.strip():
                        return n.strip()[:120]
    return ""


def _detail(evt: dict, part: dict) -> Any:
    for src in (part, evt):
        for k in _DETAIL_KEYS:
            if src.get(k) is not None:
                return src.get(k)
    return None


def _step_key(evt: dict, part: dict, tname: str, etype: str) -> str:
    for src in (part, evt):
        for k in _ID_KEYS:
            v = src.get(k)
            if isinstance(v, (str, int)) and str(v).strip():
                return str(v)
    return tname or etype


def _error_text(evt: dict) -> str:
    err = evt.get("error") or {}
    if isinstance(err, dict):
        data = err.get("data")
        if isinstance(data, dict):
            msg = data.get("message") or data.get("responseBody") or data.get("error")
            if msg:
                return str(msg)[:500]
        return str(err.get("name") or "mimo error")[:500]
    return str(err or "mimo error")[:500]


async def run_hubert(
    message: str,
    out: cl.Message,
    *,
    workdir: str,
    session_id: str | None = None,
    model: str | None = None,
    timeout: float = 180.0,
) -> tuple[str | None, str]:
    """Stream one Hubert (mimo) turn into `out`.

    Returns (new_session_id, error_text). error_text is "" on success.
    """
    cmd = ["mimo", "run", "--format", "json", "--dir", workdir]
    if model:
        cmd += ["-m", model]
    if session_id:
        cmd += ["-s", session_id]
    cmd.append(message)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workdir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    new_session = session_id
    error_text = ""
    open_steps: dict[str, cl.Step] = {}
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout

    async def _close(step: cl.Step, output: str | None) -> None:
        if output:
            step.output = output
        try:
            await step.update()
        except Exception:  # noqa: BLE001 - never let a UI update kill the turn
            pass

    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                error_text = error_text or "Hubert timed out."
                break
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                error_text = error_text or "Hubert timed out."
                break
            if not line:
                break
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            if not s.startswith("{"):
                low = s.lower()
                if not error_text and ("model not found" in low or "unauthorized" in low or "api key" in low):
                    error_text = s[:400]
                continue
            try:
                evt = json.loads(s)
            except json.JSONDecodeError:
                continue

            etype = str(evt.get("type") or "")
            part = evt.get("part") if isinstance(evt.get("part"), dict) else {}
            sid = evt.get("sessionID") or part.get("sessionID")
            if sid and not new_session:
                new_session = sid

            if etype == "text":
                txt = part.get("text") or evt.get("text")
                if txt:
                    await out.stream_token(txt)
                continue
            if etype == "error":
                error_text = error_text or _error_text(evt)
                continue

            tname = _tool_name(evt, part)
            if "tool" in etype.lower() or tname:
                key = _step_key(evt, part, tname, etype)
                finished = any(w in etype.lower() for w in ("finish", "end", "result", "complete"))
                detail = _preview(_detail(evt, part))
                _log("tool", etype, "name=", tname, "key=", key, "fin=", finished)
                step = open_steps.get(key)
                if step is None:
                    step = cl.Step(name=tname or etype.replace("_", " "), type="tool")
                    if detail:
                        step.input = detail
                    await step.send()
                    if finished:
                        await _close(step, detail)
                    else:
                        open_steps[key] = step
                else:
                    if finished:
                        open_steps.pop(key, None)
                        await _close(step, detail)
                    elif detail:
                        step.output = detail
                        await step.update()
                continue

            if etype not in ("step_start", "step_finish"):
                _log("unhandled", etype, list(evt.keys()))

        await proc.wait()
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        for step in open_steps.values():
            await _close(step, None)

    await out.update()
    return new_session, error_text
