"""Fail-closed behavior of the bridge _TokenBridge ASGI gate.

http.py pulls Gradio + the full ADK runtime at import, none of which _TokenBridge
uses, so we stub those heavy modules and import the REAL middleware class."""
from __future__ import annotations

import asyncio
import sys
import types

import pytest


def _load_http(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("CHAT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("CHAT_TOKEN", token)

    def stub(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        monkeypatch.setitem(sys.modules, name, m)
        return m

    gr = stub("gradio", mount_gradio_app=lambda *a, **k: None)
    stub("forsch.adk_bridge.gradio_app", build_gradio_app=lambda *a, **k: object())
    stub("forsch.adk_bridge.sidecar_config", ENTER_TO_SEND_JS="")
    stub("forsch.adk_bridge.gateway.sources_spectrum", spectrum_to_canonical=lambda *a, **k: None)
    stub("forsch.adk_bridge.gateway.router", resolve_agent=lambda *a, **k: None, build_source_defaults=lambda *a, **k: {})
    stub("forsch.adk_bridge.run", stream_agent=lambda *a, **k: None)
    stub("forsch.adk_bridge.runtime", get_runtime=lambda *a, **k: None)

    import importlib
    import forsch.adk_bridge.http as http
    importlib.reload(http)
    return http


async def _drive(http, path, headers=None, qs=b""):
    """Run _TokenBridge over one http scope; return (status, passed_through)."""
    passed = {"ok": False}

    async def inner_app(scope, receive, send):
        passed["ok"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    captured = {"status": None}

    async def send(m):
        if m["type"] == "http.response.start":
            captured["status"] = m["status"]

    scope = {"type": "http", "path": path, "query_string": qs, "headers": headers or []}
    await http._TokenBridge(inner_app)(scope, None, send)
    return captured["status"], passed["ok"]


def test_chat_path_blocked_when_token_unset(monkeypatch):
    # FAIL CLOSED: empty CHAT_TOKEN must 401 /chat/, not pass through to Gradio
    # (the old `or not _CHAT_TOKEN` short-circuit opened the surface to everyone).
    http = _load_http(monkeypatch, None)
    status, passed = asyncio.run(_drive(http, "/chat/"))
    assert status == 401
    assert passed is False


def test_chat_path_blocked_without_token(monkeypatch):
    http = _load_http(monkeypatch, "s3cret")
    status, passed = asyncio.run(_drive(http, "/chat/"))
    assert status == 401 and passed is False


def test_valid_token_passes_through(monkeypatch):
    http = _load_http(monkeypatch, "s3cret")
    status, passed = asyncio.run(_drive(http, "/chat/", qs=b"chat_token=s3cret"))
    assert passed is True  # authenticated -> reaches the app


def test_non_chat_path_passes_through_even_without_token(monkeypatch):
    # /healthz etc. are not gated; only /chat/ is protected.
    http = _load_http(monkeypatch, None)
    status, passed = asyncio.run(_drive(http, "/healthz"))
    assert passed is True
