from pathlib import Path

import pytest
import yaml

from forsch.adk_bridge.bridge import (
    _build_channel_map,
    _build_crm_assignee_map,
    _crm_request_authorized,
    _decode_crm_payload,
    _format_crm_task_message,
    _handle_crm_http,
    _import_agent,
    _load_config,
    _resolve_crm_agent,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "bridge_config.yaml"


def test_bridge_config_routes_team_stability_to_stability_agent():
    config = _load_config(CONFIG_PATH)

    channel_map = _build_channel_map(config)

    assert channel_map["team-stability"] == "stability"


def test_bridge_config_imports_stability_agent():
    config = _load_config(CONFIG_PATH)
    spec = config["agents"]["stability"]

    agent = _import_agent(spec["agent_package"], spec["agent_attr"])

    assert agent.name == "stability_agent"
    assert len(agent.tools) == 7


def test_bridge_pyproject_declares_stability_agent_dependency():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"

    assert '"forsch-agent-stability>=0.1.0"' in pyproject_path.read_text()


def test_agent_spec_matches_bridge_route():
    spec_path = Path(__file__).resolve().parents[2] / "agent_specs" / "agents.yaml"
    manifest = yaml.safe_load(spec_path.read_text())

    stability = manifest["agents"]["stability"]

    assert stability["package"] == "forsch.agent_stability.agent"
    assert stability["attr"] == "root_agent"
    assert "#team-stability" in stability["discord_channels"]
    assert stability["safety_level"] == "local_write"


def test_crm_assignee_map_routes_simple_agent_names():
    config = _load_config(CONFIG_PATH)

    assignee_map = _build_crm_assignee_map(config)

    assert assignee_map["ops"] == "ops"
    assert _resolve_crm_agent({"assigned_to": "ops"}, assignee_map) == "ops"
    assert _resolve_crm_agent({"assigned_to": "unknown"}, assignee_map) is None


def test_crm_task_message_preserves_minimal_task_shape():
    message = _format_crm_task_message(
        {
            "task_id": "CRM-TASK-00042",
            "title": "Follow up with Acme",
            "description": "Ask about renewal timing",
            "assigned_to": "ops",
            "reference_doctype": "CRM Lead",
            "reference_docname": "CRM-LEAD-00012",
        }
    )

    assert "You were assigned this CRM task from Frappe CRM." in message
    assert "Task ID: CRM-TASK-00042" in message
    assert "Title: Follow up with Acme" in message
    assert "Assigned to: ops" in message
    assert "Reference docname: CRM-LEAD-00012" in message


@pytest.mark.asyncio
async def test_crm_http_endpoint_routes_payload_without_profiles(monkeypatch):
    monkeypatch.setenv("CRM_BRIDGE_SECRET", "test-secret")

    class FakeClient:
        _config = {
            "crm": {
                "secret_env": "CRM_BRIDGE_SECRET",
                "max_body_bytes": 65536,
                "timeout_sec": 5.0,
            }
        }

        async def handle_crm_task_assigned(self, payload):
            return {"ok": True, "agent": payload["assigned_to"], "task_id": payload["task_id"]}

    server = await __import__("asyncio").start_server(
        lambda reader, writer: _handle_crm_http(reader, writer, FakeClient()),
        "127.0.0.1",
        0,
    )
    host, port = server.sockets[0].getsockname()[:2]

    try:
        reader, writer = await __import__("asyncio").open_connection(host, port)
        body = b'{"task_id":"CRM-TASK-00042","assigned_to":"ops"}'
        writer.write(
            b"POST /crm/task-assigned HTTP/1.1\r\n"
            + f"Host: {host}\r\nContent-Length: {len(body)}\r\n".encode("ascii")
            + b"X-CRM-Bridge-Secret: test-secret\r\n\r\n"
            + body
        )
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()

    assert b"HTTP/1.1 200 OK" in response
    assert b'"agent": "ops"' in response
    assert b'"task_id": "CRM-TASK-00042"' in response


def test_crm_payload_rejects_non_object_json():
    with pytest.raises(ValueError, match="invalid_payload"):
        _decode_crm_payload(b"[]")


def test_crm_request_authorization_uses_shared_secret(monkeypatch):
    monkeypatch.setenv("CRM_BRIDGE_SECRET", "test-secret")
    crm_cfg = {"secret_env": "CRM_BRIDGE_SECRET"}

    assert _crm_request_authorized({"x-crm-bridge-secret": "test-secret"}, crm_cfg)
    assert not _crm_request_authorized({"x-crm-bridge-secret": "wrong"}, crm_cfg)
