"""Agent Builder cockpit — interactive canvas, edit + deploy actions, terminal.

Routes (all token-gated when ``COCKPIT_TOKEN`` is set; the Frappe reverse-proxy
attaches the token server-side):
  GET  /                     the canvas (live manifest + toolbox inlined)
  GET  /api/view             that data as JSON
  GET  /api/agent/{id}       edit (base64 ``q`` patch) -> regenerate wrapper+package
  POST /api/agent/{id}       same, JSON body (direct use; Frappe blocks POST)
  GET  /api/restart          docker restart adk-bridge (make edits go live)
  GET  /term                 xterm.js page
  WS   /term/ws              PTY (tmux) bridge
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute

from forsch.adk_builder.canvas_api import build_view
from forsch.adk_builder.editor import update_agent
from forsch.adk_builder.terminal import pty_bridge

DEFAULT_WORKSPACE = "/opt/data/workspace/adk"
_CANVAS = Path(__file__).resolve().parents[3] / "templates" / "canvas.html"
_TERM = Path(__file__).resolve().parents[3] / "templates" / "term.html"
# The terminal needs WebSockets, which the Frappe HTTP proxy can't forward, so
# the canvas embeds it straight from the Funnel (same token gate).
FUNNEL_TERM = "https://hubert-cloud-sp6.tail818cf8.ts.net:8443/term"
BRIDGE_CONTAINER = "adk-bridge"


def _forbidden(request, token):
    if not token:
        return None
    provided = request.query_params.get("token") or request.headers.get("x-cockpit-token")
    return PlainTextResponse("forbidden", status_code=403) if provided != token else None


def create_app(*, workspace_root: str, token: str | None = None) -> Starlette:
    async def index(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        html = (
            _CANVAS.read_text()
            .replace("/*__VIEW__*/", json.dumps(build_view(workspace_root)))
            .replace("/*__TERMURL__*/", json.dumps(f"{FUNNEL_TERM}?token={token or ''}"))
        )
        return HTMLResponse(html)

    async def api_view(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        return JSONResponse(build_view(workspace_root))

    async def api_agent(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        try:
            if request.method == "POST":
                patch = await request.json()
            else:
                import base64

                q = request.query_params.get("q", "")
                pad = "=" * (-len(q) % 4)
                patch = json.loads(base64.urlsafe_b64decode(q + pad).decode("utf-8")) if q else {}
            return JSONResponse(update_agent(workspace_root, request.path_params["agent_id"], patch))
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def api_restart(request):
        if (deny := _forbidden(request, token)) is not None:
            return deny
        try:
            r = subprocess.run(
                ["docker", "restart", BRIDGE_CONTAINER],
                capture_output=True, text=True, timeout=90,
            )
            ok = r.returncode == 0
            msg = (r.stdout or r.stderr).strip()[:200]
            return JSONResponse({"ok": ok, "message": msg}, status_code=200 if ok else 500)
        except Exception as exc:
            return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)

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
            Route("/api/restart", api_restart, methods=["GET"]),
            Route("/term", term_page, methods=["GET"]),
            WebSocketRoute("/term/ws", term_ws),
        ]
    )


def serve(workspace_root: str, host: str = "127.0.0.1", port: int = 8765, token: str | None = None) -> None:
    import uvicorn

    uvicorn.run(create_app(workspace_root=workspace_root, token=token), host=host, port=port)


if __name__ == "__main__":
    serve(
        os.environ.get("FORSCH_ADK_WORKSPACE", DEFAULT_WORKSPACE),
        host=os.environ.get("FORSCH_ADK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FORSCH_ADK_PORT", "8765")),
        token=os.environ.get("COCKPIT_TOKEN") or None,
    )
