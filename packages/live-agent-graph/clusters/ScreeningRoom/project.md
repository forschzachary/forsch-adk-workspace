---
goal: 'Private movie club — invite, provision, request, and SR-1 scheduling via native Discord bots'
status: active
handoff_pct: 0
data_connectors:
  - sr_cli
  - jellyfin
  - jellyseerr
---
# ScreeningRoom

Private movie-club cluster. Served by the NATIVE hand-coded ADK Discord bots
**Huberto** (friend-facing cat, DM) and **screening_ops** (internal infra lead),
defined in `bridge/src/forsch/adk_bridge/` and modeled as persistent nodes in
`capabilities.json`. These are NOT Factory/agents.yaml agents. The retired
`screening` Factory agent (a stub with TMDB tools) was removed on 2026-06-30.
