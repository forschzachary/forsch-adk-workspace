"""One normalized message every source adapter produces and the router consumes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CanonicalMessage:
    source: str                       # "discord" | "crm" | "teamrooms" | "chat" | "sms"
    sender: str                       # stable id of who sent it (becomes ADK user_id)
    text: str                         # message body, HTML stripped to text
    target: Optional[str] = None      # adapter-resolved agent name (explicit address), if any
    session_id: Optional[str] = None  # adapter-chosen ADK session id (continuity key)
    attachments: list[Any] = field(default_factory=list)
    raw: Optional[Any] = None         # source-native handle the renderer needs to reply
