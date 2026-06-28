import json
import sys
import time
import urllib.request

import pytest
import yaml

from forsch.adk_components.patterns.cluster_spawn import make_agent_files
from forsch.adk_components.patterns.jsonl_store import JSONLStore
from forsch.adk_components.patterns.mimo_stream_runner import run as mimo_stream_run
from forsch.adk_components.patterns.oauth_client import OAuthAPIClient, OAuthError


class DummyTokenStore:
    def __init__(self, records=None, fail_write=False):
        self.records = records or []
        self.fail_write = fail_write

    def read(self):
        return self.records

    def write_atomic(self, records):
        if self.fail_write:
            raise RuntimeError("disk full")
        self.records = list(records)
        return len(self.records)


class DummyOAuthClient(OAuthAPIClient):
    auth_endpoint = "https://auth.example.test/oauth"
    token_endpoint = "https://auth.example.test/token"
    default_scopes = ["read"]
    provider_name = "dummy"


def test_jsonl_store_atomic_write_cleans_own_tmp_files(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_PATTERNS_DATA_DIR", str(tmp_path))
    store = JSONLStore("events.jsonl", basename_dir="audit")
    stale_tmp = store.path.parent / f".{store.path.name}.stale.tmp"
    unrelated_tmp = store.path.parent / "other.tmp"
    stale_tmp.write_text("left behind")
    unrelated_tmp.write_text("leave alone")

    assert store.write_atomic([{"event": "ok"}]) == 1

    assert not stale_tmp.exists()
    assert unrelated_tmp.exists()
    assert store.read() == [{"event": "ok"}]


def test_oauth_refresh_failure_is_reported():
    client = DummyOAuthClient(
        client_id="id",
        client_secret="secret",
        token_store=DummyTokenStore([{"refresh_token": "old"}]),
    )

    def fail_refresh(_refresh_token):
        raise OAuthError("provider rejected refresh")

    client._refresh = fail_refresh
    with pytest.raises(OAuthError, match="provider rejected refresh"):
        client._ensure_token()


def test_oauth_exchange_code_keeps_memory_state_when_persistence_fails(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"access_token": "access-1", "expires_in": 120}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    client = DummyOAuthClient(
        client_id="id",
        client_secret="secret",
        token_store=DummyTokenStore(fail_write=True),
    )

    with pytest.raises(OAuthError, match="token persistence failed"):
        client.exchange_code("code-1")

    assert client._access_token == "access-1"


def test_make_agent_files_validates_ids_and_tools(tmp_path):
    with pytest.raises(ValueError, match="agent_id"):
        make_agent_files("../bad", "desc", "instructions", ["sample_tool"], workspace=tmp_path)

    with pytest.raises(ValueError, match="at least one"):
        make_agent_files("test_bot", "desc", "instructions", [], workspace=tmp_path)


def test_make_agent_files_writes_web_yaml_and_canonical_manifest(tmp_path):
    manifest_path = tmp_path / "agent_specs" / "agents.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("version: 1\nagents: {}\n")

    result = make_agent_files(
        "test_bot",
        "Tracks test work",
        "You are a careful test bot.",
        ["sample_tool"],
        workspace=tmp_path,
        model="gpt-5-mini",
    )

    web_yaml = yaml.safe_load((tmp_path / "web_agents" / "test_bot" / "root_agent.yaml").read_text())
    manifest = yaml.safe_load(manifest_path.read_text())

    assert web_yaml["instruction"] == "You are a careful test bot."
    assert web_yaml["tools"] == [{"name": "forsch.adk_components.tools.sample_tool"}]
    assert manifest["agents"]["test_bot"]["web_entrypoint"] == "web_agents/test_bot"
    assert manifest["agents"]["test_bot"]["instruction"] == "You are a careful test bot."
    assert manifest["agents"]["test_bot"]["tools"] == ["forsch.adk_components.tools.sample_tool"]
    assert "registry/agents/agents.yaml" not in "\n".join(result["files_written"])

    second = make_agent_files(
        "test_bot",
        "Tracks test work",
        "You are a careful test bot.",
        ["sample_tool"],
        workspace=tmp_path,
        model="gpt-5-mini",
    )
    assert second["files_written"] == {}


def test_mimo_stream_runner_kills_after_json_error_event():
    script = (
        "import json, sys, time; "
        "print(json.dumps({'type':'error','sessionID':'s1','error':{'data':{'message':'Model not found: test-model'}}}), flush=True); "
        "time.sleep(30)"
    )

    started = time.monotonic()
    result = mimo_stream_run([sys.executable, "-c", script], timeout=10)

    assert time.monotonic() - started < 2
    assert result["ok"] is False
    assert "Model not found: test-model" in result["error"]
    assert result["session_id"] == "s1"


def test_mimo_stream_runner_reports_non_json_failure():
    script = "import sys; print('Model not found: plain-text-model'); sys.exit(1)"

    result = mimo_stream_run([sys.executable, "-c", script], timeout=5)

    assert result["ok"] is False
    assert "Model not found: plain-text-model" in result["error"]
