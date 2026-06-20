import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "stability_audit.py"


def test_stability_audit_does_not_validate_imports_for_missing_workspace():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--workspace",
            "/tmp/does-not-exist-for-stability-test",
            "--skip-services",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)

    assert report["workspace"]["exists"] is False
    assert report["summary"]["failed_agent_imports"] == [
        "stability",
        "ops",
        "assistant",
        "brand",
        "build",
        "social",
    ]
    assert report["agents"][0]["error"] == "workspace path not allowed"
    assert report["git"] == []


def test_stability_audit_refuses_non_default_workspace_without_git_scan(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--workspace", str(tmp_path), "--skip-services"],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)

    assert report["git"] == []
    assert report["agents"][0]["error"] == "workspace path not allowed"


def test_agent_source_paths_include_all_configured_agent_packages():
    spec = importlib.util.spec_from_file_location("stability_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    paths = {path.as_posix() for path in module.get_agent_source_paths(Path("/workspace"))}

    assert paths == {
        "/workspace/agents/stability/src",
        "/workspace/agents/ops/src",
        "/workspace/agents/assistant/src",
        "/workspace/agents/brand/src",
        "/workspace/agents/build/src",
        "/workspace/agents/social/src",
    }
