from starlette.testclient import TestClient

from forsch.adk_builder.app import create_app

WS = "/root/.hermes/workspace/adk"


def test_open_when_token_unset():
    client = TestClient(create_app(workspace_root=WS))
    assert client.get("/").status_code == 200


def test_gated_when_token_set():
    client = TestClient(create_app(workspace_root=WS, token="s3cret"))
    assert client.get("/").status_code == 403
    assert client.get("/?token=wrong").status_code == 403
    assert client.get("/?token=s3cret").status_code == 200
    assert client.get("/", headers={"X-Cockpit-Token": "s3cret"}).status_code == 200
