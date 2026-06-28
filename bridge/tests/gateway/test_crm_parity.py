from forsch.adk_bridge.bridge import _resolve_crm_agent
from forsch.adk_bridge.gateway.sources_crm import crm_to_canonical
from forsch.adk_bridge.gateway.router import resolve_agent

ASSIGNEE_MAP = {"ops": "ops", "build": "build", "assistant": "assistant"}
AGENTS = {"ops", "build", "assistant"}
CONFIG = {"mention_routing": False, "source_defaults": {}}


def test_crm_assignee_routes_like_old_logic():
    payload = {"assigned_to": "build", "task_id": "T-1", "subject": "ship it"}
    canonical = crm_to_canonical(payload, ASSIGNEE_MAP)
    old = _resolve_crm_agent(payload, ASSIGNEE_MAP)
    assert resolve_agent(canonical, AGENTS, CONFIG) == old == "build"


def test_crm_unmapped_assignee_is_none_like_old_logic():
    payload = {"assigned_to": "nobody", "task_id": "T-2"}
    canonical = crm_to_canonical(payload, ASSIGNEE_MAP)
    assert _resolve_crm_agent(payload, ASSIGNEE_MAP) is None
    assert resolve_agent(canonical, AGENTS, CONFIG) is None


def test_crm_session_and_sender_keying():
    payload = {"assigned_to": "ops", "task_id": "T-9"}
    canonical = crm_to_canonical(payload, ASSIGNEE_MAP)
    assert canonical.sender == "crm:frappe"
    assert canonical.target == "ops"
    assert canonical.session_id == "crm:ops:T-9"
