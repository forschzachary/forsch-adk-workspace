"""Unit tests for the pure CLI helpers (no click / ADK needed)."""
from forsch.cli.scaffold import new_agent_block
from forsch.cli.workspace import find_workspace


def test_new_agent_block_naming():
    b = new_agent_block("foo-bar")
    assert b["package"] == "forsch.agent_foo_bar.agent"
    assert b["adk_name"] == "foo_bar_agent"
    assert b["model_code"] == "forsch.agent_foo_bar.agent.foo_bar_model"
    assert b["web_entrypoint"] == "web_agents/foo-bar"
    assert b["tools"] == []
    assert b["safety_level"] == "read_only"


def test_new_agent_block_description_fills_purpose():
    b = new_agent_block("x", description="does the X thing")
    assert b["description"] == "does the X thing"
    assert b["purpose"] == "does the X thing"


def test_find_workspace_prefers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    assert find_workspace() == tmp_path


def test_find_workspace_walks_up_to_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)
    (tmp_path / "agent_specs").mkdir()
    (tmp_path / "agent_specs" / "agents.yaml").write_text("version: 1\nagents: {}\n")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert find_workspace(sub) == tmp_path


def test_find_workspace_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)
    assert find_workspace(tmp_path) is None
