"""Tests for the sidecar dashboard app (Phase 1 TDD, step 6).

The app re-collects the workspace per request (no stale cache) and serves the
read-only dashboard. Phase 1 exposes only safe HTTP methods.
"""

from pathlib import Path

from starlette.testclient import TestClient

from forsch.adk_builder.app import create_app


def _write_contract(root: Path, agent_id: str) -> None:
    (root / "agent_specs").mkdir(exist_ok=True)
    (root / "agent_specs" / "agents.yaml").write_text(
        f"agents:\n  {agent_id}:\n    package: forsch.agent_{agent_id}.agent\n"
        f"    safety_level: read_only\n    purpose: Audit.\n"
    )


def test_app_serves_dashboard_200_html(tmp_path):
    _write_contract(tmp_path, "stability")
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    resp = client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "READ ONLY" in resp.text
    assert "stability" in resp.text


def test_app_reflects_current_workspace_not_stale(tmp_path):
    _write_contract(tmp_path, "alpha")
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    assert "alpha" in client.get("/").text

    # Mutate the workspace; the next request must reflect it (re-collected, not cached).
    _write_contract(tmp_path, "beta")
    body = client.get("/").text
    assert "beta" in body
    assert "alpha" not in body


def test_app_exposes_only_safe_methods(tmp_path):
    app = create_app(workspace_root=str(tmp_path))
    methods: set[str] = set()
    for route in app.routes:
        methods |= set(getattr(route, "methods", set()) or set())
    assert methods <= {"GET", "HEAD"}  # Phase 1 is read-only
