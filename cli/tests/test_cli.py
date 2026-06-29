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


def test_scaffold_eval_set_shape(tmp_path):
    import json

    from forsch.cli.evals import eval_set_path, scaffold_eval_set

    p = tmp_path / "shelby.evalset.json"
    scaffold_eval_set(p, "shelby")
    d = json.loads(p.read_text())
    assert d["eval_set_id"] == "shelby-evals"
    case = d["eval_cases"][0]
    assert case["conversation"][0]["user_content"]["role"] == "user"
    assert case["conversation"][0]["final_response"]["role"] == "model"
    assert eval_set_path(tmp_path, "shelby").name == "shelby.evalset.json"


def test_graph_bare_strips_tool_prefix():
    from forsch.cli.graph import _bare

    assert _bare("forsch.adk_components.tools.search_movies") == "search_movies"
    assert _bare("search_movies") == "search_movies"


def test_goal_preamble_includes_goal():
    from forsch.cli.goal import goal_preamble

    out = goal_preamble("  wire shelby's grocery tool  ")
    assert "wire shelby's grocery tool" in out
    assert "GOAL MODE" in out


def test_skills_lists_and_resolves_dir(tmp_path):
    from forsch.cli.skills import list_skill_names, skills_dir

    d = tmp_path / "skills"
    d.mkdir()
    (d / "alpha.md").write_text("# Alpha\nfirst line\n")
    (d / "beta.md").write_text("# Beta\nsecond line\n")
    assert list_skill_names(tmp_path) == ["alpha", "beta"]
    assert skills_dir(tmp_path) == d
