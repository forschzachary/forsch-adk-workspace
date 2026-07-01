"""Auth hardening for the public chat surface (fail-closed + constant-time + validated inject)."""
from __future__ import annotations

import importlib


def _reload_with_token(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("CHAT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("CHAT_TOKEN", token)
    import forsch.adk_chat.cl_app as cl_app
    importlib.reload(cl_app)
    return cl_app


def test_auth_fails_closed_without_token(monkeypatch):
    # The old code returned cl.User("zach") for EVERY request when CHAT_TOKEN was empty,
    # handing an anonymous internet caller the full-bypass Claude profile. Must be None now.
    cl_app = _reload_with_token(monkeypatch, None)
    assert cl_app.auth({}) is None
    assert cl_app.auth({"x-chat-token": ""}) is None
    assert cl_app.auth({"x-chat-token": "anything"}) is None


def test_auth_requires_exact_token(monkeypatch):
    cl_app = _reload_with_token(monkeypatch, "s3cret-token")
    assert cl_app.auth({"x-chat-token": "s3cret-token"}) is not None      # match
    assert cl_app.auth({"x-chat-token": "wrong"}) is None                  # mismatch
    assert cl_app.auth({}) is None                                        # missing


def _run_token_bridge(monkeypatch, token_env, presented):
    """Drive the ASGI TokenBridge once with a GET carrying ?chat_token=<presented>.
    Returns (injected_x_chat_token, set_cookie_value)."""
    import asyncio
    if token_env is None:
        monkeypatch.delenv("CHAT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("CHAT_TOKEN", token_env)
    import forsch.adk_chat.http as http
    importlib.reload(http)

    seen = {"x": None, "cookie": None}

    async def fake_app(scope, receive, send):
        for k, v in scope.get("headers", []):
            if k == b"x-chat-token":
                seen["x"] = v.decode()
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(m):
        for k, v in m.get("headers", []):
            if k == b"set-cookie":
                seen["cookie"] = v.decode()

    qs = f"chat_token={presented}".encode() if presented is not None else b""
    scope = {"type": "http", "query_string": qs, "headers": []}
    asyncio.run(http.TokenBridge(fake_app)(scope, None, send))
    return seen["x"], seen["cookie"]


def test_token_bridge_injects_only_on_match(monkeypatch):
    x, cookie = _run_token_bridge(monkeypatch, "good", "good")
    assert x == "good"
    assert cookie is not None and "Partitioned" in cookie   # DO-NOW #4: CHIPS attribute

    x2, cookie2 = _run_token_bridge(monkeypatch, "good", "bad")
    assert x2 is None and cookie2 is None                    # mismatch => no injection


def test_token_bridge_noop_without_configured_token(monkeypatch):
    # Empty CHAT_TOKEN: never inject (so cl_app.auth fails closed downstream).
    x, cookie = _run_token_bridge(monkeypatch, None, "anything")
    assert x is None and cookie is None
