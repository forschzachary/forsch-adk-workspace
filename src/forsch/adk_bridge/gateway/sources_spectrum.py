"""Spectrum iMessage source adapter: webhook payload -> CanonicalMessage (pure).

Receives a normalized payload from the Spectrum TS bridge service (adk-sms-shelby),
which runs the Spectrum SDK and POSTs incoming iMessages here. This adapter is
pure — no network, no I/O. It normalizes the payload into a CanonicalMessage and
lets the gateway router + stream_agent handle the rest.
"""
from __future__ import annotations

from forsch.adk_bridge.gateway.message import CanonicalMessage


def spectrum_to_canonical(payload: dict, routing_map: dict[str, str] | None = None) -> CanonicalMessage:
    """Normalize a Spectrum iMessage webhook payload.

    Payload shape (from adk-sms-shelby/src/index.ts):
        {
            "platform": "iMessage",
            "sender": "+15551234567",      # phone or email
            "text": "add milk to groceries",
            "space_id": "iMessage;-;+15551234567",
            "message_id": "uuid"
        }

    routing_map: optional {sender_id: agent_name} for per-sender routing.
    Falls back to source_defaults["spectrum"] in the router.
    """
    sender = payload.get("sender", "")
    text = payload.get("text", "")
    space_id = payload.get("space_id", "")
    message_id = payload.get("message_id", "")

    # Resolve target agent from routing map if provided
    target = None
    if routing_map and sender in routing_map:
        target = routing_map[sender]

    return CanonicalMessage(
        source="spectrum",
        sender=f"imessage:{sender}",
        text=text,
        target=target,
        session_id=f"imessage:{space_id}" if space_id else f"imessage:{sender}",
        raw=payload,
    )