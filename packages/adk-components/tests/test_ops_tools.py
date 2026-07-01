from forsch.adk_components.tools import ops_tools


def test_read_host_file_allows_inside_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("FORSCH_ADK_ALLOW_HOST_READS", raising=False)
    f = tmp_path / "note.txt"
    f.write_text("hello workspace")
    out = ops_tools.read_host_file(str(f))
    assert out.get("content") == "hello workspace"
    assert "error" not in out


def test_read_host_file_refuses_outside_workspace(tmp_path, monkeypatch):
    # A secret-ish file living OUTSIDE the confined workspace must be refused.
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    monkeypatch.delenv("FORSCH_ADK_ALLOW_HOST_READS", raising=False)
    secret = tmp_path / "secret.env"
    secret.write_text("TOKEN=supersecret")
    out = ops_tools.read_host_file(str(secret))
    assert "content" not in out
    assert "outside the workspace" in out["error"]


def test_read_host_file_override_allows_outside(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_ADK_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    monkeypatch.setenv("FORSCH_ADK_ALLOW_HOST_READS", "1")
    outside = tmp_path / "var_log.txt"
    outside.write_text("log line")
    out = ops_tools.read_host_file(str(outside))
    assert out.get("content") == "log line"


def test_read_host_file_fails_closed_without_workspace(tmp_path, monkeypatch):
    # No workspace set + not overridden => the seatbelt can't be applied, so refuse.
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)
    monkeypatch.delenv("FORSCH_ADK_ALLOW_HOST_READS", raising=False)
    f = tmp_path / "anything.txt"
    f.write_text("x")
    out = ops_tools.read_host_file(str(f))
    assert "content" not in out
    assert "FORSCH_ADK_WORKSPACE is not set" in out["error"]
