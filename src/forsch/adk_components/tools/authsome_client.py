"""Authsome-backed HTTP client for ADK tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


_PYTHON_HTTP_SCRIPT = r'''
import json
import os
import sys
import urllib.parse
import urllib.request

method, url, payload_json = sys.argv[1:4]
payload = json.loads(payload_json)
params = payload.get("params") or {}
if params:
    separator = "&" if "?" in url else "?"
    url = url + separator + urllib.parse.urlencode(params)

headers = {}
token = os.environ.get("FRAPPE_CRM_TOKEN")
if token:
    headers["Authorization"] = f"token {token}"

data = None
if "json" in payload:
    data = json.dumps(payload["json"]).encode()
    headers["Content-Type"] = "application/json"

request = urllib.request.Request(url, data=data, headers=headers, method=method)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        sys.stdout.write(response.read().decode())
except urllib.error.HTTPError as error:
    sys.stderr.write(error.read().decode() or str(error))
    raise SystemExit(22)
'''


class AuthsomeHTTPError(RuntimeError):
    """Raised when an Authsome-backed HTTP request fails."""


class AuthsomeHTTPClient:
    """Small HTTP wrapper that routes requests through Authsome."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:7998",
        authsome_bin: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url
        self._authsome_bin = authsome_bin
        self.timeout = timeout

    @property
    def authsome_bin(self) -> str:
        """Resolve the authsome binary lazily: explicit arg, AUTHSOME_BIN, then PATH."""
        resolved = self._authsome_bin or os.environ.get("AUTHSOME_BIN") or shutil.which("authsome")
        if not resolved:
            raise AuthsomeHTTPError(
                "authsome binary not found; set AUTHSOME_BIN or install authsome on PATH"
            )
        return resolved

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        cmd = [
            self.authsome_bin,
            "run",
            "--",
            "python3",
            "-c",
            _PYTHON_HTTP_SCRIPT,
            method.upper(),
            url,
        ]

        payload: dict[str, Any] = {}
        if params:
            payload["params"] = params
        if json_data is not None:
            payload["json"] = json_data
        cmd.append(json.dumps(payload))

        env = {**os.environ, "AUTHSOME_BASE_URL": self.base_url}
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=self.timeout,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise AuthsomeHTTPError(message)

        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
