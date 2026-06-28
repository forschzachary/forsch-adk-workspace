"""Contracts a source adapter implements. Ingress is source-specific (a discord.Client
handler, an HTTP webhook, a Chainlit callback); the shared parts are:

  - produce a CanonicalMessage (see message.py), with `target` pre-resolved from the
    source's own address map when it has one;
  - route it with gateway.router.resolve_agent(msg, agents, config);
  - run it with the bridge's existing _run_agent_text(agent_name, agent, user_id,
    session_id, text, buffer);
  - render the reply via a Renderer (the existing buffer protocol below).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Renderer(Protocol):
    """The buffer protocol StreamBuffer (Discord) and TextBuffer (text) already satisfy."""
    def feed(self, text: str) -> None: ...
    def should_flush(self) -> bool: ...
    async def flush(self) -> None: ...
    async def flush_final(self) -> None: ...
