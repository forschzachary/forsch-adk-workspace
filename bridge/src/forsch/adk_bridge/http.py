import re
import os
import json
import hmac
import asyncio
import urllib.parse
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import gradio as gr
from forsch.adk_bridge.gradio_app import build_gradio_app
from forsch.adk_bridge.sidecar_config import ENTER_TO_SEND_JS
from forsch.adk_bridge.gateway.sources_spectrum import spectrum_to_canonical
from forsch.adk_bridge.gateway.router import resolve_agent, build_source_defaults
from forsch.adk_bridge.run import stream_agent
from forsch.adk_bridge.runtime import get_runtime

app = FastAPI()

_CHAT_TOKEN = os.environ.get("CHAT_TOKEN", "")
_COOKIE = "chat_token"

# Spectrum webhook auth: shared secret for the TS bridge service
_SPECTRUM_SECRET = os.environ.get("SPECTRUM_SECRET", "")


@app.get("/healthz")
def healthz():
    return {"ok": True}


# Team Rooms (Gameplan) integration — a PULL poller started on app startup. Gated:
# a safe no-op unless teamrooms.enabled + bot creds are configured (see
# forsch.adk_bridge.teamrooms.wiring). The box has no public inbound, so it polls
# Gameplan outbound rather than receiving webhooks.
@app.on_event("startup")
async def _teamrooms_startup():
    from forsch.adk_bridge.teamrooms.wiring import maybe_start_poller
    maybe_start_poller()

# ── Gradio mount (replaces Chainlit) ────────────────────────────────────────
_gradio_demo = build_gradio_app()
gr.mount_gradio_app(app, _gradio_demo, path="/chat", js=ENTER_TO_SEND_JS)


# ── token bridge ────────────────────────────────────────────────────────────
# Chainlit's header_auth_callback only reads real HTTP headers — a plain <iframe
# src=".../chat?chat_token=…"> embed (the CRM page) can't set one. This ASGI
# middleware accepts the token from the ?chat_token= query or a chat_token cookie,
# and when it matches CHAT_TOKEN injects the x-chat-token request header (and sets
# the cookie on the first hit) so the SPA's later same-origin XHR/WebSocket carry
# it. Auth stays the single header_auth_callback check.
class _TokenBridge:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not _CHAT_TOKEN:
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        headers = dict(scope.get("headers") or [])
        # Already authenticated header present? pass through.
        if hmac.compare_digest(headers.get(b"x-chat-token", b"").decode(), _CHAT_TOKEN):
            return await self.app(scope, receive, send)

        # Pull the token from query string or cookie.
        token = None
        qs = scope.get("query_string", b"").decode()
        for pair in qs.split("&"):
            if pair.startswith(f"{_COOKIE}="):
                token = urllib.parse.unquote(pair.split("=", 1)[1])
                break
        if token is None:
            cookie_hdr = headers.get(b"cookie", b"").decode()
            for c in cookie_hdr.split(";"):
                c = c.strip()
                if c.startswith(f"{_COOKIE}="):
                    token = c.split("=", 1)[1]
                    break

        if token is not None and hmac.compare_digest(token, _CHAT_TOKEN):
            # Inject the header Chainlit's auth callback reads.
            new_headers = [
                (k, v) for (k, v) in scope.get("headers", []) if k != b"x-chat-token"
            ]
            new_headers.append((b"x-chat-token", _CHAT_TOKEN.encode()))
            scope = dict(scope)
            scope["headers"] = new_headers

            set_cookie = (
                f"{_COOKIE}={_CHAT_TOKEN}; Path=/; HttpOnly; SameSite=None; Secure; Partitioned"
            ).encode()

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    message = dict(message)
                    message["headers"] = list(message.get("headers", [])) + [
                        (b"set-cookie", set_cookie)
                    ]
                await send(message)

            return await self.app(scope, receive, send_wrapper)

        # Gate /chat/ routes — Gradio has no header_auth_callback, so we
        # must block at the ASGI level (same pattern as the spike's _TokenGate).
        if path.startswith("/chat/"):
            if scope["type"] == "websocket":
                # Reject the handshake cleanly — HTTP response frames are illegal
                # on a websocket scope and crash/hang the ASGI server.
                await send({"type": "websocket.close", "code": 1008})
                return
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": json.dumps({"error": "unauthorized"}).encode(),
            })
            return

        return await self.app(scope, receive, send)


app.add_middleware(_TokenBridge)

class _SameSiteNoneMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                new_headers = []
                for k, v in headers:
                    if k.lower() == b"set-cookie":
                        v_str = v.decode("utf-8", errors="ignore")
                        # Replace SameSite=lax or SameSite=Lax
                        v_str = re.sub(r"(?i)samesite=lax", "SameSite=None", v_str)
                        # Ensure Secure is present
                        if "Secure" not in v_str and "secure" not in v_str:
                            v_str += "; Secure"
                        # CHIPS: partition the cookie so it survives in a
                        # cross-site iframe with 3p cookies blocked.
                        if "artitioned" not in v_str:
                            v_str += "; Partitioned"
                        new_headers.append((k, v_str.encode("utf-8")))
                    else:
                        new_headers.append((k, v))
                message["headers"] = new_headers
            await send(message)
        return await self.app(scope, receive, send_wrapper)

app.add_middleware(_SameSiteNoneMiddleware)


# ── Spectrum iMessage webhook ──────────────────────────────────────────────
# Receives POST from the adk-sms-shelby TS service when an iMessage arrives.
# Authenticates with a shared secret (SPECTRUM_SECRET env var, checked via
# constant-time comparison). Routes the message through the gateway to the
# configured agent and returns the response text inline.

@app.post("/spectrum/webhook")
async def spectrum_webhook(request: Request):
    # Auth: shared secret in Authorization header
    if _SPECTRUM_SECRET:
        auth = request.headers.get("authorization", "")
        expected = f"Bearer {_SPECTRUM_SECRET}"
        if not hmac.compare_digest(auth, expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    runtime = get_runtime()
    config = runtime.config

    # Build routing map from config (spectrum section)
    spectrum_cfg = (config.get("spectrum") or {})
    routing_map = spectrum_cfg.get("routing", {})

    msg = spectrum_to_canonical(body, routing_map=routing_map)

    # Route: explicit target > source default
    source_defaults = build_source_defaults(config)
    agent_name = resolve_agent(msg, runtime.agents.keys(), {
        "source_defaults": {**source_defaults, "spectrum": spectrum_cfg.get("default_agent", "shelby")},
        "mention_routing": False,
    })

    if not agent_name or agent_name not in runtime.agents:
        return JSONResponse({"error": f"no agent resolved for {msg.sender}"}, status_code=404)

    agent = runtime.agents[agent_name]

    # Run the agent and collect the full response
    response_parts = []
    async for token in stream_agent(
        agent=agent,
        agent_name=agent_name,
        session_service=runtime.session_service,
        user_id=msg.sender,
        session_id=msg.session_id,
        text=msg.text,
    ):
        response_parts.append(token)

    response_text = "".join(response_parts)

    return JSONResponse({
        "agent": agent_name,
        "response": response_text,
        "session_id": msg.session_id,
    })


def main():
    import uvicorn
    uvicorn.run(app, host=os.environ.get("BRIDGE_HTTP_HOST", "127.0.0.1"),
                port=int(os.environ.get("BRIDGE_HTTP_PORT", "8800")))


if __name__ == "__main__":
    main()
