"""Frappe CRM client for ADK tools."""

from __future__ import annotations

import json
from typing import Any, Protocol

from .authsome_client import AuthsomeHTTPClient


class HTTPClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any: ...


class FrappeClient:
    """Read-only Frappe REST API client."""

    def __init__(
        self,
        *,
        base_url: str = "https://frappe-web-production-7412.up.railway.app",
        authsome_base_url: str = "http://127.0.0.1:7998",
        http_client: HTTPClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or AuthsomeHTTPClient(
            base_url=authsome_base_url,
        )

    def ping(self) -> dict[str, Any]:
        return self.http_client.request("GET", self._method_url("ping"))

    def get_count(self, doctype: str) -> int:
        response = self.http_client.request(
            "GET",
            self._method_url("frappe.client.get_count"),
            params={"doctype": doctype},
        )
        if not isinstance(response, dict) or response.get("message") is None:
            raise ValueError(f"unexpected Frappe response for get_count({doctype!r}): {response!r}")
        return int(response["message"])

    def get_list(
        self,
        doctype: str,
        *,
        fields: list[str] | None = None,
        limit_page_length: int = 20,
    ) -> list[dict[str, Any]]:
        response = self.http_client.request(
            "GET",
            self._method_url("frappe.client.get_list"),
            params={
                "doctype": doctype,
                "fields": json.dumps(fields or ["name"]),
                "limit_page_length": limit_page_length,
            },
        )
        if not isinstance(response, dict) or response.get("message") is None:
            raise ValueError(f"unexpected Frappe response for get_list({doctype!r}): {response!r}")
        return response["message"]

    def _method_url(self, method: str) -> str:
        return f"{self.base_url}/api/method/{method}"
