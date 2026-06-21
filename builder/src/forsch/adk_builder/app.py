"""Agent Builder cockpit — interactive canvas + edit actions.

``/`` serves the canvas (live manifest inlined). ``/api/view`` returns that data
as JSON; ``/api/agent/{id}`` (POST) applies an edit (instruction/tools) and
regenerates via the Factory. The read-only Phase-1 dashboard stays at
``/dashboard``. When ``COCKPIT_TOKEN`` is set every route requires it (``?token=``
or ``X-Cockpit-Token``) — the Frappe reverse-proxy attaches it server-side.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute

from forsch.adk_builder.canvas_api import build_view
from forsch.adk_builder.collector import collect_workspace
from forsch.adk_builder.editor import update_agent
from forsch.adk_builder.renderer import render_dashboard
from forsch.adk_builder.terminal import pty_bridge

DEFAULT_WORKSPACE = "/opt/data/workspace/adk"
_CANVAS = Path(__file__).resolve().parents[3] / "templates" / "canvas.html"
_TERM = Path(__file__).resolve().parents[3] / "templates" / "term.html"
# The terminal needs WebSockets, which the Frappe HTTP proxy can't forward, so
# the canvas embeds it straight from the Funnel (same token gate).
FUNNEL_TERM = "https://hubert-cloud-sp6.tail818cf8.ts.net:8443/term"


def _forbidden(request, token):
    if not token:
        return None
    provided = request.query_params.get("token") or request.headers.get("x-cockpit-token")
    if provided != token:
        return PlainTextResponse("forbidden", status_code=403)
    return None


def create_app(*, workspace_root: str, token: str | None = None) -> Starlette:
    async def index(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        view = build_view(workspace_root)
        term_url = f"{FUNNEL_TERM}?token={token or ''}"
        html = (
            _CANVAS.read_text()
            .replace("/*__VIEW__*/", json.dumps(view))
            .replace("/*__TERMURL__*/", json.dumps(term_url))
        )
        return HTMLResponse(html)

    async def api_view(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        return JSONResponse(build_view(workspace_root))

    async def api_agent(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        agent_id = request.path_params["agent_id"]
        try:
            if request.method == "POST":
                patch = await request.json()
            else:
                # GET tunnel: Frappe 15 blocks POST to whitelisted methods at the
                # route layer, so the proxied canvas sends the patch base64'd here.
                import base64

                q = request.query_params.get("q", "")
                pad = "=" * (-len(q) % 4)
                patch = json.loads(base64.urlsafe_b64decode(q + pad).decode("utf-8")) if q else {}
            result = update_agent(workspace_root, agent_id, patch)
            return JSONResponse(result)
        except Exception as exc:  # surface the message to the UI, don't 500 blindly
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def dashboard(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        return HTMLResponse(render_dashboard(collect_workspace(workspace_root)))

    async def term_page(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        return HTMLResponse(_TERM.read_text().replace("__TOKEN__", token or ""))

    async def term_ws(websocket):
        if token and websocket.query_params.get("token") != token:
            await websocket.close(code=1008)
            return
        await pty_bridge(websocket, workspace_root)

    return Starlette(
        routes=[
            Route("/", index, methods=["GET"]),
            Route("/api/view", api_view, methods=["GET"]),
            Route("/api/agent/{agent_id}", api_agent, methods=["GET", "POST"]),
            Route("/dashboard", dashboard, methods=["GET"]),
            Route("/term", term_page, methods=["GET"]),
            WebSocketRoute("/term/ws", term_ws),
        ]
    )


def serve(
    workspace_root: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
) -> None:
    import uvicorn

    uvicorn.run(create_app(workspace_root=workspace_root, token=token), host=host, port=port)


if __name__ == "__main__":
    serve(
        os.environ.get("FORSCH_ADK_WORKSPACE", DEFAULT_WORKSPACE),
        host=os.environ.get("FORSCH_ADK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FORSCH_ADK_PORT", "8765")),
        token=os.environ.get("COCKPIT_TOKEN") or None,
    )
