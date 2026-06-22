"""Deterministic agent routing — no LLM, no I/O. Pure function, trivially testable.

Policy order:
  1. explicit target  — the adapter already resolved an agent (channel/assignee/persona map)
  2. @mention         — a known agent @-mentioned in the text (if mention_routing on)
  3. source default    — config["source_defaults"][msg.source]
Returns the agent name, or None if nothing applies.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from forsch.adk_bridge.gateway.message import CanonicalMessage


def resolve_agent(msg: CanonicalMessage, agents: Iterable[str], config: dict) -> Optional[str]:
    known = set(agents)

    if msg.target and msg.target in known:
        return msg.target

    if config.get("mention_routing") and msg.text:
        for name in sorted(known):  # sorted → deterministic when several match
            if re.search(rf"@{re.escape(name)}\b", msg.text, re.IGNORECASE):
                return name

    return (config.get("source_defaults") or {}).get(msg.source)


def build_source_defaults(config: dict) -> dict[str, str]:
    """Derive {source: default_agent}. Seeds discord from agents.dm_fallback, then
    merges any explicit config['source_defaults'] on top (explicit wins)."""
    defaults: dict[str, str] = {}
    dm = (config.get("agents") or {}).get("dm_fallback")
    if dm:
        defaults["discord"] = dm
    defaults.update(config.get("source_defaults") or {})
    return defaults
