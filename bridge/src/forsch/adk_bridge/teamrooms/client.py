"""Thin Gameplan (Frappe) REST client for the Team Rooms bridge.

Reads recent comments / mention-notifications and posts agent replies, authenticated
as a bot user via a Frappe ``api_key:api_secret`` token. The HTTP client is injectable
so the logic is unit-testable without a network (tests pass a fake; prod lazily makes
an ``httpx.Client``).

Gameplan shapes (Frappe v16, verified):
  - GP Comment is polymorphic: ``reference_doctype="GP Discussion"`` + ``reference_name=<disc>``.
  - GP Notification rows (``type="Mention"``, ``to_user=<bot>``) are the mention inbox.
"""
from __future__ import annotations

import json

_COMMENT_FIELDS = ["name", "content", "reference_name", "owner", "creation"]
_NOTIF_FIELDS = ["name", "type", "comment", "discussion", "project", "from_user", "creation"]


class GameplanClient:
    def __init__(self, *, base_url, api_key, api_secret, http=None):
        self.base_url = base_url.rstrip("/")
        self._auth = f"token {api_key}:{api_secret}"
        self._http = http

    @property
    def http(self):
        if self._http is None:
            import httpx
            self._http = httpx.Client(timeout=30.0)
        return self._http

    def _headers(self):
        return {"Authorization": self._auth, "Content-Type": "application/json"}

    def _resource(self, doctype):
        return f"{self.base_url}/api/resource/{doctype}"

    def list_comments_since(self, since_iso, *, limit=100):
        """New GP Discussion comments created after ``since_iso`` (asc by creation)."""
        params = {
            "filters": json.dumps([
                ["reference_doctype", "=", "GP Discussion"],
                ["creation", ">", since_iso],
            ]),
            "fields": json.dumps(_COMMENT_FIELDS),
            "order_by": "creation asc",
            "limit_page_length": limit,
        }
        r = self.http.get(self._resource("GP Comment"), params=params, headers=self._headers())
        r.raise_for_status()
        return r.json()["data"]

    def list_mention_notifications(self, bot_email, *, limit=50):
        """Unread mention notifications addressed to the bot (the @mention inbox)."""
        params = {
            "filters": json.dumps([
                ["to_user", "=", bot_email],
                ["read", "=", 0],
                ["type", "=", "Mention"],
            ]),
            "fields": json.dumps(_NOTIF_FIELDS),
            "order_by": "creation asc",
            "limit_page_length": limit,
        }
        r = self.http.get(self._resource("GP Notification"), params=params, headers=self._headers())
        r.raise_for_status()
        return r.json()["data"]

    def get_discussion(self, name):
        """Fetch one GP Discussion (for its ``project`` / ``closed_at`` / ``title``)."""
        r = self.http.get(f"{self._resource('GP Discussion')}/{name}", headers=self._headers())
        r.raise_for_status()
        return r.json()["data"]

    def post_comment(self, discussion, content_html):
        """Post an agent reply into a discussion. ``owner`` is set to the bot by Frappe."""
        body = {"reference_doctype": "GP Discussion", "reference_name": discussion, "content": content_html}
        r = self.http.post(self._resource("GP Comment"), json=body, headers=self._headers())
        r.raise_for_status()
        return r.json()["data"]
