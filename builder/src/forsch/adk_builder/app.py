"""Sidecar dashboard app (Phase 1, read-only).

A minimal Starlette app that re-collects the workspace on every request (so the
page never shows stale data) and serves the read-only dashboard. Only GET is
exposed in Phase 1; guarded write routes arrive in Phase 2.

When ``COCKPIT_TOKEN`` is set, every request must present it (``?token=`` query
param or ``X-Cockpit-Token`` header) or get a 403. This lets the Cockpit sit
behind a public Tailscale Funnel safely: only the Frappe reverse-proxy (which
holds the token server-side, behind CRM login) can reach it.
"""

from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

from forsch.adk_builder.collector import collect_workspace
from forsch.adk_builder.renderer import render_dashboard

DEFAULT_WORKSPACE = "/opt/data/workspace/adk"


def create_app(*, workspace_root: str, token: str | None = None) -> Starlette:
    async def index(request):
        if token:
            provided = request.query_params.get("token") or request.headers.get("x-cockpit-token")
            if provided != token:
                return PlainTextResponse("forbidden", status_code=403)
        workspace = collect_workspace(workspace_root)  # fresh per request, not cached
        return HTMLResponse(render_dashboard(workspace))

    return Starlette(routes=[Route("/", index, methods=["GET"])])


def serve(
    workspace_root: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
) -> None:
    import uvicorn

    uvicorn.run(create_app(workspace_root=workspace_root, token=token), host=host, port=port)


if __name__ == "__main__":
    # Host/port/token overridable via env so the systemd service can bind the
    # Tailscale IP and require a token without code changes. Defaults stay open.
    serve(
        os.environ.get("FORSCH_ADK_WORKSPACE", DEFAULT_WORKSPACE),
        host=os.environ.get("FORSCH_ADK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FORSCH_ADK_PORT", "8765")),
        token=os.environ.get("COCKPIT_TOKEN") or None,
    )
