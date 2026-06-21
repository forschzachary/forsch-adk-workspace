"""Tests for the cockpit app: interactive canvas at /, view JSON, edit action."""

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


def test_api_view_has_agents_and_toolbox(tmp_path):
    _write_contract(tmp_path, "alpha")
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    data = client.get("/api/view").json()
    assert [a["id"] for a in data["agents"]] == ["alpha"]
    assert "toolbox" in data  # present (empty drawers in a bare workspace)


def test_only_agent_route_accepts_post(tmp_path):
    app = create_app(workspace_root=str(tmp_path))
    post_paths = {
        r.path for r in app.routes if "POST" in (getattr(r, "methods", set()) or set())
    }
    assert post_paths == {"/api/agent/{agent_id}"}
