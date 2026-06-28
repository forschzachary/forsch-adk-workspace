"""Resolve which agent (if any) should handle a Team Rooms item.

Pure logic, no I/O — kept separate so routing is trivially unit-testable and the
trigger (poller or webhook) stays dumb. Two modes, in priority order:

1. **space map** — a GP Project (space) dedicated to one agent (`config["spaces"]`).
2. **@mention** — a known agent name @-mentioned in the content, in any space,
   when `config["mention_routing"]` is on.
"""
from __future__ import annotations

import re


def resolve_agent(*, project, content, agents, config):
    """Return the agent name to handle this item, or ``None`` if none applies.

    project: GP Project (space) name the item lives in.
    content: the item's text/HTML (for @mention routing).
    agents:  iterable of known agent names (mention targets are validated against it).
    config:  the ``teamrooms`` config block (``spaces`` map, ``mention_routing`` flag).
    """
    spaces = config.get("spaces") or {}
    if project and project in spaces:
        return spaces[project]
    if config.get("mention_routing") and content:
        for name in sorted(agents):  # sorted → deterministic when several match
            if re.search(rf"@{re.escape(name)}\b", content, re.IGNORECASE):
                return name
    return None
