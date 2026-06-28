"""OAuthAPIClient — base OAuth2 client with auto-refresh + persistent token store.

---
keywords: [oauth, gmail, calendar, drive, imap, api, auth, refresh-token, google, microsoft, github, slack]
intention: "Saves you from re-implementing OAuth flows (token fetch, refresh, persistence, scope handling) for every new external service. Subclass it, declare scopes, ship a working integration."
function: "Base OAuth2 client with auto-refresh, persistent token store, Authsome fallback for credential safety."
depends_on: [jsonl_store]
used_by: [crm_tools, email_groceries]
example: "client = GmailClient(scopes=['gmail.readonly']); msgs = client.fetch_recent()"
---

SUB-CLASS THIS. Don't call OAuthAPIClient directly.

    class GmailClient(OAuthAPIClient):
        auth_endpoint = "https://accounts.google.com/o/oauth2/auth"
        token_endpoint = "https://oauth2.googleapis.com/token"
        default_scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

Then call `client.fetch("/gmail/v1/users/me/messages")`.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

from .jsonl_store import JSONLStore


class OAuthError(Exception):
    pass


class OAuthAPIClient:
    """Base OAuth2 client. Subclass and declare auth_endpoint, token_endpoint, default_scopes."""

    auth_endpoint: str = ""
    token_endpoint: str = ""
    default_scopes: list[str] = []
    provider_name: str = "generic"

    def __init__(
        self,
        scopes: Optional[list[str]] = None,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_store: Optional[JSONLStore] = None,
    ):
        self.scopes = scopes or self.default_scopes
        # Credential resolution: env > Authsome (future) > raise
        self.client_id = client_id or self._resolve_credential("client_id")
        self.client_secret = client_secret or self._resolve_credential("client_secret")
        if not self.client_id or not self.client_secret:
            raise OAuthError(
                f"{self.provider_name}: missing OAuth credentials. "
                f"Set FORSCH_OAUTH_{self.provider_name.upper()}_CLIENT_ID + _CLIENT_SECRET, "
                f"or pass client_id= and client_secret= to constructor."
            )
        self.token_store = token_store or JSONLStore(
            f"oauth_{self.provider_name}_tokens.json", basename_dir="oauth"
        )
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _resolve_credential(self, kind: str) -> Optional[str]:
        """Look up credential from env vars. Authsome fallback TBD."""
        env_var = f"FORSCH_OAUTH_{self.provider_name.upper()}_{kind.upper()}"
        return os.environ.get(env_var)

    def _load_token(self) -> Optional[dict[str, Any]]:
        records = self.token_store.read()
        return records[0] if records else None

    def _save_token(self, token: dict[str, Any]) -> None:
        # Token is set-shaped, not append-shaped — use write_atomic
        token["saved_at"] = time.time()
        self.token_store.write_atomic([token])

    def _set_token_state(self, token: dict[str, Any]) -> None:
        self._access_token = token["access_token"]
        self._token_expires_at = time.time() + token.get("expires_in", 3600)

    def _is_token_valid(self) -> bool:
        if not self._access_token:
            return False
        # 60s buffer
        return time.time() < (self._token_expires_at - 60)

    def _ensure_token(self) -> str:
        if self._is_token_valid():
            return self._access_token  # type: ignore[return-value]
        stored = self._load_token()
        refresh_error: OAuthError | None = None
        if stored and stored.get("refresh_token"):
            try:
                return self._refresh(stored["refresh_token"])
            except OAuthError as exc:
                refresh_error = exc
        message = (
            f"{self.provider_name}: no valid token and no refresh_token. "
            f"Run the authorization flow first (call get_authorization_url + exchange_code)."
        )
        if refresh_error:
            message = (
                f"{self.provider_name}: stored refresh_token could not be refreshed. "
                f"{refresh_error} Run the authorization flow again."
            )
        raise OAuthError(message)

    def _refresh(self, refresh_token: str) -> str:
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode()
        req = urllib.request.Request(self.token_endpoint, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token = json.loads(resp.read())
        except Exception as exc:
            raise OAuthError(f"{self.provider_name}: refresh failed: {exc}") from exc
        token["refresh_token"] = token.get("refresh_token", refresh_token)
        self._set_token_state(token)
        try:
            self._save_token(token)
        except Exception as exc:
            raise OAuthError(
                f"{self.provider_name}: refresh succeeded but token persistence failed: {exc}"
            ) from exc
        return self._access_token

    def exchange_code(self, code: str, redirect_uri: str = "http://localhost") -> dict[str, Any]:
        """Exchange an authorization code for tokens. Call after the user grants consent."""
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode()
        req = urllib.request.Request(self.token_endpoint, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                token = json.loads(resp.read())
        except Exception as exc:
            raise OAuthError(f"{self.provider_name}: code exchange failed: {exc}") from exc
        self._set_token_state(token)
        try:
            self._save_token(token)
        except Exception as exc:
            raise OAuthError(
                f"{self.provider_name}: code exchange succeeded but token persistence failed: {exc}"
            ) from exc
        return token

    def get_authorization_url(self, redirect_uri: str = "http://localhost", state: str = "") -> str:
        """Build the URL to redirect a user to for OAuth consent."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
        }
        if state:
            params["state"] = state
        return f"{self.auth_endpoint}?{urllib.parse.urlencode(params)}"

    def fetch(self, path: str, *, method: str = "GET", params: Optional[dict] = None, body: Optional[dict] = None) -> Any:
        """Authenticated API call. Returns parsed JSON."""
        token = self._ensure_token()
        url = path
        if params:
            url = f"{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data=data, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise OAuthError(f"{self.provider_name}: {exc.code} {exc.reason} on {path}") from exc
