import json
import subprocess

import pytest

from forsch.adk_components.tools.authsome_client import AuthsomeHTTPClient, AuthsomeHTTPError


def test_authsome_client_builds_curl_command_with_provider_and_json(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, env, timeout):
        calls.append((cmd, env, timeout))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"ok": True}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    client = AuthsomeHTTPClient(base_url="http://127.0.0.1:7998", authsome_bin="/usr/local/bin/authsome")
    result = client.request(
        "POST",
        "https://example.test/api",
        params={"kind": "lead"},
        json_data={"name": "CRM Lead"},
    )

    assert result == {"ok": True}
    cmd, env, timeout = calls[0]
    assert cmd[:5] == ["/usr/local/bin/authsome", "run", "--", "python3", "-c"]
    assert "https://example.test/api" in cmd
    assert "POST" in cmd
    assert '{"params": {"kind": "lead"}, "json": {"name": "CRM Lead"}}' in cmd
    assert env["AUTHSOME_BASE_URL"] == "http://127.0.0.1:7998"
    assert timeout == 30


def test_authsome_client_raises_on_failed_command(monkeypatch):
    def fake_run(cmd, capture_output, text, env, timeout):
        return subprocess.CompletedProcess(cmd, 22, stdout="", stderr="401 nope")

    monkeypatch.setattr(subprocess, "run", fake_run)

    client = AuthsomeHTTPClient(authsome_bin="/usr/local/bin/authsome")
    with pytest.raises(AuthsomeHTTPError, match="401 nope"):
        client.request("GET", "https://example.test/api")
