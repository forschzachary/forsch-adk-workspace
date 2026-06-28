"""GameplanClient — REST shapes + auth, verified with an injected fake HTTP client
(no network). Mirrors the Frappe document REST API the bot poller uses.
"""
import json

from forsch.adk_bridge.teamrooms.client import GameplanClient


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return {"data": self._data}

    def raise_for_status(self):
        pass


class _FakeHTTP:
    def __init__(self, data=None):
        self.calls = []
        self._data = data if data is not None else []

    def get(self, url, params=None, headers=None):
        self.calls.append(("GET", url, params, headers))
        return _Resp(self._data)

    def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, json, headers))
        return _Resp(json)


def _client(http):
    return GameplanClient(base_url="https://crm.x.com/", api_key="K", api_secret="S", http=http)


def test_auth_header_is_frappe_token():
    http = _FakeHTTP()
    _client(http).list_comments_since("2026-06-22 00:00:00")
    _, _, _, headers = http.calls[0]
    assert headers["Authorization"] == "token K:S"


def test_list_comments_filters_and_parses():
    http = _FakeHTTP(data=[{"name": "c1", "content": "<p>hi</p>", "reference_name": "d1", "owner": "u@x", "creation": "2026-06-22 01:00:00"}])
    out = _client(http).list_comments_since("2026-06-22 00:00:00")
    assert out[0]["name"] == "c1" and out[0]["reference_name"] == "d1"
    _, url, params, _ = http.calls[0]
    assert url == "https://crm.x.com/api/resource/GP Comment"
    flt = json.loads(params["filters"])
    assert ["reference_doctype", "=", "GP Discussion"] in flt
    assert any(f[0] == "creation" and f[1] == ">" for f in flt)
    assert params["order_by"] == "creation asc"


def test_post_comment_payload_shape():
    http = _FakeHTTP()
    _client(http).post_comment("d1", "<p>reply</p>")
    method, url, body, _ = http.calls[0]
    assert method == "POST"
    assert url == "https://crm.x.com/api/resource/GP Comment"
    assert body == {"reference_doctype": "GP Discussion", "reference_name": "d1", "content": "<p>reply</p>"}


def test_get_discussion_uses_name_in_path():
    http = _FakeHTTP(data={"name": "d1", "project": "stability-room", "title": "T"})
    d = _client(http).get_discussion("d1")
    assert d["project"] == "stability-room"
    _, url, _, _ = http.calls[0]
    assert url == "https://crm.x.com/api/resource/GP Discussion/d1"


def test_mention_notifications_inbox():
    http = _FakeHTTP(data=[{"name": "n1", "type": "Mention", "comment": "c1", "discussion": "d1", "project": "p1", "from_user": "u@x"}])
    out = _client(http).list_mention_notifications("bot@x")
    assert out[0]["discussion"] == "d1"
    _, url, params, _ = http.calls[0]
    assert "GP Notification" in url
    flt = json.loads(params["filters"])
    assert ["to_user", "=", "bot@x"] in flt
    assert ["read", "=", 0] in flt
