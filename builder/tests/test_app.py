"""Tests for the cockpit app: interactive canvas at /, read-only dashboard at /dashboard.

The canvas exposes edit actions (POST /api/agent/{id}); the read-only Phase-1
dashboard moved to /dashboard.
"""

from pathlib import Path

from starlette.testclient import TestClient

from forsch.adk_builder.app import create_app


def _write_contract(root: Path, agent_id: str) -> None:
    (root / "agent_specs").mkdir(exist_ok=True)
    (root / "agent_specs" / "agents.yaml").write_text(
        f"agents:\n  {agent_id}:\n    package: forsch.agent_{agent_id}.agent\n"
        f"    adk_name: {agent_id}_agent\n    safety_level: read_only\n    purpose: Audit.\n"
    )


def test_canvas_served_at_root(tmp_path):
    _write_contract(tmp_path, "stability")
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "stability" in resp.text


def test_api_view_returns_agents(tmp_path):
    _write_contract(tmp_path, "alpha")
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    data = client.get("/api/view").json()
    assert [a["id"] for a in data["agents"]] == ["alpha"]


def test_dashboard_moved_to_dashboard_route(tmp_path):
    _write_contract(tmp_path, "stability")
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "READ ONLY" in resp.text


def test_edit_action_exposed_phase2(tmp_path):
    app = create_app(workspace_root=str(tmp_path))
    methods: set[str] = set()
    for route in app.routes:
        methods |= set(getattr(route, "methods", set()) or set())
    assert "POST" in methods  # edit actions exist now
    assert "PUT" not in methods and "DELETE" not in methods
