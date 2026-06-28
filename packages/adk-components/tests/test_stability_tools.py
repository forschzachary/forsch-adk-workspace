from forsch.adk_components.tools import stability_tools


def test_get_workspace_inventory_reports_structural_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    (tmp_path / "components" / "src").mkdir(parents=True)
    (tmp_path / "agents" / "stability").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("workspace\n")

    inventory = stability_tools.get_workspace_inventory(str(tmp_path), max_depth=2)

    assert inventory["root"] == str(tmp_path)
    assert inventory["exists"] is True
    assert "components" in inventory["directories"]
    assert "agents/stability" in inventory["directories"]
    assert "README.md" in inventory["files"]


def test_get_workspace_inventory_rejects_paths_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path / "workspace"))

    inventory = stability_tools.get_workspace_inventory(str(tmp_path / "outside"), max_depth=2)

    assert inventory["exists"] is False
    assert inventory["error"] == "path outside workspace"


def test_get_git_state_reports_not_a_repo_for_plain_directory(tmp_path):
    state = stability_tools.get_git_state([str(tmp_path)])

    assert state[0]["path"] == str(tmp_path)
    assert state[0]["is_repo"] is False
    assert state[0]["status"] == []


def test_get_git_state_rejects_paths_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path / "workspace"))

    state = stability_tools.get_git_state([str(tmp_path / "outside")])

    assert state[0]["is_repo"] is False
    assert state[0]["error"] == "path outside workspace"


def test_validate_agent_imports_rejects_unapproved_modules():
    result = stability_tools.validate_agent_imports([
        {"name": "json", "module": "json", "attr": "loads"}
    ])

    assert result[0]["name"] == "json"
    assert result[0]["ok"] is False
    assert result[0]["error"] == "agent import not allowed"


def test_check_service_health_handles_unreachable_endpoint():
    result = stability_tools.check_service_health({"missing": "http://127.0.0.1:9/health"}, timeout=0.1)

    assert result[0]["name"] == "missing"
    assert result[0]["ok"] is False
    assert result[0]["url"] == "http://127.0.0.1:9/health"


def test_check_service_health_rejects_unapproved_endpoints():
    result = stability_tools.check_service_health({"metadata": "http://169.254.169.254/"}, timeout=0.1)

    assert result[0]["ok"] is False
    assert result[0]["error"] == "service endpoint not allowed"
