from forsch.adk_components.tools.frappe_client import FrappeClient


def test_frappe_ping_calls_method_endpoint():
    calls = []

    class FakeHTTP:
        def request(self, method, url, params=None, json_data=None):
            calls.append((method, url, params, json_data))
            return {"message": "pong"}

    client = FrappeClient(base_url="https://crm.example.test", http_client=FakeHTTP())

    assert client.ping() == {"message": "pong"}
    assert calls == [("GET", "https://crm.example.test/api/method/ping", None, None)]


def test_frappe_get_count_calls_frappe_client_get_count():
    calls = []

    class FakeHTTP:
        def request(self, method, url, params=None, json_data=None):
            calls.append((method, url, params, json_data))
            return {"message": 73}

    client = FrappeClient(base_url="https://crm.example.test/", http_client=FakeHTTP())

    assert client.get_count("CRM Lead") == 73
    assert calls == [
        (
            "GET",
            "https://crm.example.test/api/method/frappe.client.get_count",
            {"doctype": "CRM Lead"},
            None,
        )
    ]


def test_frappe_get_list_defaults_to_safe_fields_and_limit():
    calls = []

    class FakeHTTP:
        def request(self, method, url, params=None, json_data=None):
            calls.append((method, url, params, json_data))
            return {"message": [{"name": "CRM-LEAD-1"}]}

    client = FrappeClient(base_url="https://crm.example.test", http_client=FakeHTTP())

    assert client.get_list("CRM Lead") == [{"name": "CRM-LEAD-1"}]
    assert calls == [
        (
            "GET",
            "https://crm.example.test/api/method/frappe.client.get_list",
            {"doctype": "CRM Lead", "fields": '["name"]', "limit_page_length": 20},
            None,
        )
    ]
