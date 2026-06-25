import re
import os
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse

import gradio as gr
from forsch.adk_bridge.gradio_app import build_gradio_app

app = FastAPI()

_CHAT_TOKEN = os.environ.get("CHAT_TOKEN", "")
_COOKIE = "chat_token"


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
gr.mount_gradio_app(app, _gradio_demo, path="/chat")


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
        if headers.get(b"x-chat-token", b"").decode() == _CHAT_TOKEN:
            return await self.app(scope, receive, send)

        # Pull the token from query string or cookie.
        token = None
        qs = scope.get("query_string", b"").decode()
        for pair in qs.split("&"):
            if pair.startswith(f"{_COOKIE}="):
                token = pair.split("=", 1)[1]
                break
        if token is None:
            cookie_hdr = headers.get(b"cookie", b"").decode()
            for c in cookie_hdr.split(";"):
                c = c.strip()
                if c.startswith(f"{_COOKIE}="):
                    token = c.split("=", 1)[1]
                    break

        if token == _CHAT_TOKEN:
            # Inject the header Chainlit's auth callback reads.
            new_headers = [
                (k, v) for (k, v) in scope.get("headers", []) if k != b"x-chat-token"
            ]
            new_headers.append((b"x-chat-token", _CHAT_TOKEN.encode()))
            scope = dict(scope)
            scope["headers"] = new_headers

            set_cookie = (
                f"{_COOKIE}={_CHAT_TOKEN}; Path=/; HttpOnly; SameSite=None; Secure"
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
                        new_headers.append((k, v_str.encode("utf-8")))
                    else:
                        new_headers.append((k, v))
                message["headers"] = new_headers
            await send(message)
        return await self.app(scope, receive, send_wrapper)

app.add_middleware(_SameSiteNoneMiddleware)



def main():
    import uvicorn
    uvicorn.run(app, host=os.environ.get("BRIDGE_HTTP_HOST", "127.0.0.1"),
                port=int(os.environ.get("BRIDGE_HTTP_PORT", "8800")))


if __name__ == "__main__":
    main()
