# Graduation Criteria — Live Agent Graph

**Date:** 2026-06-23  
**Status:** Defined and implemented

## Role ladder

```
plain → builder → orchestrator
```

Each promotion is **operator-confirmed** — never silent self-promotion. The graph shows current role + next-gate-needed on every agent node.

## plain → builder

**Criteria (all must be met):**

1. **L3 round-trip cleared.** The agent has passed a synthetic message round-trip (message → tool call → response). For agents without tools, bridge health is the fallback L3.

2. **Exposes a build/spawn capability.** The agent has at least one tool that creates or modifies artifacts in its slice. For the ops slice, this means CRM tools (`get_crm_health_snapshot`, `list_recent_crm_leads`) — the agent can read/write CRM state.

3. **Has write access to its slice's artifacts.** The agent's `safety_level` in agents.yaml is `local_write` or higher (not `read_only`). This gates the agent's ability to modify files/configs in its domain.

4. **Operator confirms.** A human clicks "Promote" in the UI. The action is logged with timestamp and operator identity.

**Next gate after promotion:** builder → orchestrator (spawn + wire a child node that reaches `built`).

## builder → orchestrator

**Criteria (all must be met):**

1. **Currently role=builder.** Must have already graduated from plain.

2. **Can spawn AND wire >=1 child node.** The agent has demonstrated the ability to create a new agent (via spawn_agent.py or equivalent) AND wire it to itself with a contract-checked edge.

3. **Child node reaches `built`.** The spawned child must clear L0-L3 gates (artifact exists, has tools, on bridge PYTHONPATH, round-trip passes).

4. **Operator confirms.** A human clicks "Promote" in the UI. The action is logged.

**Next gate after promotion:** none (orchestrator is the terminal role).

## Implementation

### `/promote` endpoint (serve.py)

POST `/promote` with `agent_id` and `target_role`. Validates criteria, updates agents.yaml, rebuilds graph.

### UI promote button

Shown on agent nodes that meet the criteria for their next role. Disabled (grey) if criteria not met. Clicking it sends the promote request.

### Logging

Each promotion writes to `.promotion_log.jsonl`:
```json
{"agent_id": "ops", "from_role": "plain", "to_role": "builder", "operator": "zach", "timestamp": "2026-06-23T..."}
```

### Node display

Tooltip shows:
```
ops (agent) · state: built · role: builder
next gate: builder→orchestrator (spawn + wire child → built)
```

## Current state (2026-06-23)

| Agent | Role | L3 | Next gate |
|-------|------|-----|-----------|
| ops | builder | ✓ (roundtrip) | builder→orchestrator |
| stability | plain | ✓ (bridge) | plain→builder (needs local_write + operator) |
| assistant | plain | ✓ (bridge) | plain→builder (needs tools + operator) |
| brand | plain | ✓ (bridge) | plain→builder (needs tools + operator) |
| build | plain | ✓ (bridge) | plain→builder (needs tools + operator) |
| social | plain | ✓ (bridge) | plain→builder (needs tools + operator) |
| shelby | plain | ✗ (not on bridge) | plain→builder (needs L2+L3 + operator) |

Ops is the only agent that has graduated to builder. It was promoted by hand-editing agents.yaml (the operator-confirmed path). The UI promote button is the next step.
