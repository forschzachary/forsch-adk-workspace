"""mimo_stream_runner — reusable streaming subprocess for the MiMo CLI.

Streams the mimo CLI's JSON event output and surfaces terminal events
(error / step_finish) without hanging on provider errors.

Implementation: a worker thread reads stdout (and stderr) into a queue.
The main thread polls the queue. On an error event, the worker thread
terminates and we kill the subprocess. On step_finish, the worker
drains any remaining output and we return.

Why a thread: readline() in non-blocking mode returns '' (EOF) on a
pipe with no data, which looks identical to actual EOF. Several
attempts at polling-with-os.read() failed to actually receive the error
event. Thread + queue is the simplest reliable approach.

Pure stdlib. No external deps. Reusable from any project that calls
the MiMo CLI.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional


def run(
    cmd: list[str],
    *,
    cwd: Optional[Path | str] = None,
    timeout: float = 120.0,
) -> dict:
    """Run a mimo-style streaming JSON subprocess and return terminal state."""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd,
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"{cmd[0] if cmd else 'mimo'} not installed", "response": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500], "response": ""}

    q: "queue.Queue[str]" = queue.Queue()
    response_text = ""
    error_text = ""
    output_tail: list[str] = []
    events: list[dict] = []
    tools: list[dict] = []
    session_id = ""
    finished_cleanly = False

    def _reader():
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                q.put(line)
        except Exception as e:
            q.put(f"__READER_ERROR__:{e}")
        finally:
            q.put("__EOF__")

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    def _preview(value, limit: int = 180) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, sort_keys=True)
            except (TypeError, ValueError):
                text = str(value)
        text = " ".join(text.split())
        return text[:limit]

    def _event_label(evt: dict) -> str:
        for key in ("title", "message", "name", "label", "summary"):
            value = evt.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
        part = evt.get("part")
        if isinstance(part, dict):
            for key in ("title", "message", "name"):
                value = part.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:120]
        return str(evt.get("type") or "event")[:120]

    def _tool_name(evt: dict) -> str:
        for key in ("tool", "toolName", "tool_name", "name"):
            value = evt.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
            if isinstance(value, dict):
                nested = value.get("name") or value.get("id")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()[:120]
        for key in ("call", "toolCall", "tool_call", "part"):
            value = evt.get(key)
            if not isinstance(value, dict):
                continue
            fn = value.get("function")
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                return fn["name"][:120]
            nested = value.get("name") or value.get("toolName") or value.get("tool_name")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()[:120]
        return ""

    def _record_event(evt: dict) -> None:
        etype = str(evt.get("type") or "event")[:80]
        if etype == "text":
            return
        event = {
            "type": etype,
            "label": _event_label(evt),
            "status": str(evt.get("status") or evt.get("state") or "").strip()[:40],
            "at_ms": int((time.time() - start) * 1000),
        }
        tool_name = _tool_name(evt)
        if tool_name:
            event["tool"] = tool_name
        detail = (
            evt.get("detail") or evt.get("details") or evt.get("input") or
            evt.get("args") or evt.get("arguments") or evt.get("result")
        )
        preview = _preview(detail)
        if preview:
            event["preview"] = preview
        events.append(event)
        del events[:-120]

        looks_like_tool = "tool" in etype.lower() or bool(tool_name)
        if looks_like_tool:
            tool = {
                "name": tool_name or event["label"],
                "type": etype,
                "status": event["status"] or ("finished" if "finish" in etype.lower() else "started"),
                "at_ms": event["at_ms"],
            }
            if preview:
                tool["preview"] = preview
            tools.append(tool)
            del tools[:-80]

    def _process(line: str) -> None:
        nonlocal response_text, error_text, session_id, finished_cleanly, error_event_seen
        s = line.strip()
        if s:
            output_tail.append(s[:500])
            del output_tail[:-12]
        if not s or not s.startswith("{"):
            if not error_text and ("Model not found:" in s or "API key" in s or "Unauthorized" in s):
                error_text = s[:500]
                error_event_seen = True
            return
        try:
            evt = json.loads(s)
        except json.JSONDecodeError:
            return
        _record_event(evt)
        etype = evt.get("type")
        if etype == "text" and evt.get("part", {}).get("text"):
            response_text += evt["part"]["text"]
        elif etype == "error":
            error = evt.get("error") or {}
            data = error.get("data") if isinstance(error, dict) else {}
            if isinstance(data, dict):
                error_text = (
                    data.get("message")
                    or data.get("responseBody")
                    or data.get("error")
                    or ""
                )
            if not error_text and isinstance(error, dict):
                error_text = error.get("name") or "MiMo error"
            error_event_seen = True
        elif etype == "step_finish":
            finished_cleanly = True
        if evt.get("sessionID") and not session_id:
            session_id = evt["sessionID"]

    start = time.time()
    error_event_seen = False
    try:
        while True:
            if time.time() - start > timeout:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "ok": False, "response": response_text,
                    "error": f"timeout after {timeout}s", "session_id": session_id,
                    "events": events, "tools": tools,
                }
            try:
                line = q.get(timeout=0.1)
            except queue.Empty:
                # If process exited and reader thread is done, exit loop.
                if proc.poll() is not None and not t.is_alive():
                    # Drain any remaining lines.
                    while True:
                        try:
                            line = q.get_nowait()
                            if line == "__EOF__":
                                break
                            _process(line)
                        except queue.Empty:
                            break
                    break
                continue

            if line == "__EOF__":
                break
            if line.startswith("__READER_ERROR__:"):
                # Reader crashed; continue to drain.
                continue
            _process(line)

            if error_event_seen:
                try:
                    proc.kill()
                except Exception:
                    pass
                break
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "ok": False, "response": response_text, "error": f"stream error: {e}",
            "session_id": session_id, "events": events, "tools": tools,
        }

    try:
        returncode = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            returncode = proc.wait(timeout=2)
        except Exception:
            returncode = proc.returncode
            pass

    if error_text:
        return {
            "ok": False, "response": response_text, "error": error_text[:500],
            "session_id": session_id, "finished_cleanly": finished_cleanly,
            "events": events, "tools": tools,
        }
    if returncode not in (0, None):
        diagnostic = "\n".join(output_tail[-4:]).strip()
        return {
            "ok": False,
            "response": response_text,
            "error": (diagnostic or f"mimo exited with code {returncode}")[:500],
            "session_id": session_id,
            "finished_cleanly": finished_cleanly,
            "events": events,
            "tools": tools,
        }
    if not response_text and not finished_cleanly:
        diagnostic = "\n".join(output_tail[-4:]).strip()
        return {
            "ok": False,
            "response": "",
            "error": (diagnostic or "mimo produced no response")[:500],
            "session_id": session_id,
            "finished_cleanly": finished_cleanly,
            "events": events,
            "tools": tools,
        }
    return {
        "ok": True,
        "response": response_text or "(no response)",
        "session_id": session_id,
        "finished_cleanly": finished_cleanly,
        "events": events,
        "tools": tools,
    }
