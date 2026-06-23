"""ADK tool functions for read-only CRM operations."""

from __future__ import annotations

from typing import Any

from .frappe_client import FrappeClient


def get_crm_health_snapshot() -> dict[str, Any]:
    """Return a read-only snapshot of Frappe CRM health and key counts.

    Each probe is isolated: a single failing call reports its error rather than
    crashing the whole snapshot (this is a health check — partial data is useful)."""
    client = FrappeClient()

    def _probe(fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - health probes report failures, don't raise
            return {"error": str(exc)}

    return {
        "ping": _probe(client.ping),
        "crm_lead_count": _probe(lambda: client.get_count("CRM Lead")),
        "newsletter_subscription_count": _probe(lambda: client.get_count("FF Newsletter Subscription")),
    }


def list_recent_crm_leads(limit: int = 10) -> list[dict[str, Any]]:
    """Return recent CRM leads with safe display fields only."""
    client = FrappeClient()
    return client.get_list(
        "CRM Lead",
        fields=["name", "lead_name", "organization", "status", "creation"],
        limit_page_length=limit,
    )
