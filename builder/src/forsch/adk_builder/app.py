"""Sidecar dashboard app (Phase 1, read-only).

A minimal Starlette app that re-collects the workspace on every request (so the
page never shows stale data) and serves the read-only dashboard. Only GET is
exposed in Phase 1; guarded write routes arrive in Phase 2.
"""

from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route

from forsch.adk_builder.collector import collect_workspace
from forsch.adk_builder.renderer import render_dashboard

DEFAULT_WORKSPACE = "/opt/data/workspace/adk"


def create_app(*, workspace_root: str) -> Starlette:
    async def index(_request):
        workspace = collect_workspace(workspace_root)  # fresh per request, not cached
        return HTMLResponse(render_dashboard(workspace))

    return Starlette(routes=[Route("/", index, methods=["GET"])])


def serve(workspace_root: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(workspace_root=workspace_root), host=host, port=port)


if __name__ == "__main__":
    # Host/port overridable via env (FORSCH_ADK_HOST/PORT) so the systemd service
    # can bind the Tailscale IP without code changes. Defaults stay localhost.
    serve(
        os.environ.get("FORSCH_ADK_WORKSPACE", DEFAULT_WORKSPACE),
        host=os.environ.get("FORSCH_ADK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FORSCH_ADK_PORT", "8765")),
    )
