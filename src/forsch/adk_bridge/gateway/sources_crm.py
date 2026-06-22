"""CRM source adapter: Frappe task-assigned payload -> CanonicalMessage (pure)."""
from __future__ import annotations

from forsch.adk_bridge.bridge import _resolve_crm_agent, _format_crm_task_message
from forsch.adk_bridge.gateway.message import CanonicalMessage


def crm_to_canonical(payload: dict, assignee_map: dict[str, str]) -> CanonicalMessage:
    """Normalize a CRM task-assigned webhook payload. target = assignee->agent (via the
    existing resolver, so routing is identical). Keying mirrors the bridge:
    sender=crm:frappe, session_id=crm:<agent>:<task_id>."""
    target = _resolve_crm_agent(payload, assignee_map)
    task_id = payload.get("task_id") or payload.get("name") or "unknown"
    return CanonicalMessage(
        source="crm",
        sender="crm:frappe",
        text=_format_crm_task_message(payload),
        target=target,
        session_id=f"crm:{target}:{task_id}" if target else None,
        raw=payload,
    )
