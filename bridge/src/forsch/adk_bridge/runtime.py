"""Build-once registry of ADK agents + a shared DatabaseSessionService.

Factored out of bridge.py's main() so the Chainlit surface and the Discord/CRM
surfaces load agents and the session store exactly once, the same way."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from google.adk.sessions import DatabaseSessionService

from forsch.adk_bridge.bridge import _import_agent, _load_config


def _db_url(config: dict) -> str:
    """SQLite (aiosqlite) URL from the bridge config's session.db_path."""
    return f"sqlite+aiosqlite:///{config['session']['db_path']}"


@dataclass
class Runtime:
    agents: dict
    session_service: DatabaseSessionService
    config: dict


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    config = _load_config("bridge_config.yaml")
    session_service = DatabaseSessionService(db_url=_db_url(config))
    agents = {
        name: _import_agent(spec["agent_package"], spec["agent_attr"])
        for name, spec in (config.get("agents") or {}).items()
        if isinstance(spec, dict)
    }
    return Runtime(agents=agents, session_service=session_service, config=config)
