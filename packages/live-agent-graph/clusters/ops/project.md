---
goal: "Build the ops agent cluster — infrastructure monitoring, deployment state"
status: building
handoff_pct: 65
data_connectors:
  - github
  - authsome
---
# Ops Cluster

First cluster migrated from the ADK workspace. Currently 7 agents: stability, assistant, brand, build, social, ops, shelby.

## What's working
- ops agent: L3 round-trip proven, role=builder
- stability agent: L3 bridge health, local_write authority, role=builder
- All 7 agents on bridge PYTHONPATH, reachable via Chainlit chat

## What's next
- Graduate ops to orchestrator (spawn + wire a child → built)
- Give the ops agent real ops tools (currently persona-only after the CRM prune)
- Add data connectors for Railway, Cloudflare health checks
