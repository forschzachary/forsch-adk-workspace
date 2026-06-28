from starlette.testclient import TestClient
from forsch.adk_bridge.http import app

def test_healthz():
    assert TestClient(app).get("/healthz").json() == {"ok": True}
