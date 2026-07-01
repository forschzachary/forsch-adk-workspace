#!/usr/bin/env python3
"""Round-trip liveness check for the stability slice.

Pushes a synthetic message through the stability agent, verifies it calls a tool
and receives a response. A node only flips to 'live' when this succeeds.
(Previously targeted the ops agent + a CRM tool; ops is persona-only after the
CRM prune, so this now exercises stability, which still has real tools.)

Runs inside the adk-bridge container (docker exec) because google-adk is only
installed there.

Usage:
  python3 roundtrip_check.py [--json] [--timeout 60]
"""

import json
import subprocess
import sys
import time
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent

ROUNDTRIP_SCRIPT = """
import asyncio, time, json
from forsch.agent_stability.agent import root_agent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner, RunConfig
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.genai import types

async def check():
    start = time.monotonic()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent, app_name='roundtrip_check',
        session_service=session_service,
        artifact_service=InMemoryArtifactService(),
        memory_service=InMemoryMemoryService(),
        auto_create_session=False,
    )
    await session_service.create_session(
        app_name='roundtrip_check', user_id='roundtrip', session_id='rt-1'
    )
    content = types.Content(parts=[types.Part.from_text(
        text='Run get_git_state and tell me the result. Be brief.'
    )], role='user')
    mode = RunConfig.model_fields['streaming_mode'].annotation
    cfg = RunConfig(streaming_mode=mode.SSE)

    tool_called = False
    tool_response = False
    response_text = ''
    async for event in runner.run_async(
        user_id='roundtrip', session_id='rt-1',
        new_message=content, run_config=cfg,
    ):
        # Check content parts for function_call (ADK puts tool calls here)
        if event.content and event.content.parts:
            for p in event.content.parts:
                if hasattr(p, 'function_call') and p.function_call:
                    # Any tool call proves the round-trip tool path works.
                    tool_called = True
                if hasattr(p, 'function_response') and p.function_response:
                    tool_response = True
        if event.is_final_response():
            if event.content and event.content.parts:
                for p in event.content.parts:
                    if hasattr(p, 'text') and p.text:
                        response_text += p.text
            break

    elapsed = int((time.monotonic() - start) * 1000)
    # Success = tool was called AND a response was received.
    # The response may contain a tool-level error (unreachable service, etc.) —
    # that's an infra issue, not a graph issue. The round-trip path still works.
    success = tool_called and tool_response
    print(json.dumps({
        'success': success,
        'tool_called': tool_called,
        'tool_response': tool_response,
        'elapsed_ms': elapsed,
        'response_preview': response_text[:300],
    }))

asyncio.run(check())
"""


def run_roundtrip(timeout: int = 60) -> dict:
    """Run the roundtrip check inside the adk-bridge container."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["docker", "exec", "adk-bridge", "python3", "-c", ROUNDTRIP_SCRIPT],
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result.returncode == 0:
            # Parse the last JSON line (skip OpenTelemetry noise)
            lines = [l for l in result.stdout.strip().split("\n") if l.strip().startswith("{")]
            if lines:
                data = json.loads(lines[-1])
                data["elapsed_ms"] = elapsed_ms
                return data
        return {
            "success": False,
            "tool_called": False,
            "tool_response": False,
            "elapsed_ms": elapsed_ms,
            "response_preview": "",
            "error": result.stderr[:500] if result.stderr else f"exit code {result.returncode}",
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "success": False, "tool_called": False, "tool_response": False,
            "elapsed_ms": elapsed_ms, "response_preview": "",
            "error": f"timeout after {timeout}s",
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "success": False, "tool_called": False, "tool_response": False,
            "elapsed_ms": elapsed_ms, "response_preview": "", "error": str(e),
        }


def main():
    args = sys.argv[1:]
    timeout = 60
    json_out = False

    for a in args:
        if a == "--json":
            json_out = True
        elif a.startswith("--timeout="):
            timeout = int(a.split("=", 1)[1])

    result = run_roundtrip(timeout=timeout)

    if json_out:
        print(json.dumps(result, indent=2))
    else:
        status = "✓ LIVE" if result["success"] else "✗ DEAD"
        print(f"{status}  tool_called={result['tool_called']}  tool_response={result['tool_response']}  {result['elapsed_ms']}ms")
        if result.get("error"):
            print(f"  error: {result['error']}")
        if result.get("response_preview"):
            print(f"  response: {result['response_preview']}")

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
