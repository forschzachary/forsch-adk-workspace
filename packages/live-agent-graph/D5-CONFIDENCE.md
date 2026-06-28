# D5: Confidence note — did closing the two trust gaps change live-OS confidence?

**Date:** 2026-06-23  
**Status:** Complete

## Trust Gap 1 — "Live" must mean a real round-trip, not a heartbeat

**Before:** `/pulse` polled ports every 3s. "Live" = "port answered." A node could show green while its agent was broken, its tools were unreachable, or its model was hallucinating.

**After:** L3 for agents is now a synthetic message round-trip (message → tool call → response). The ops agent passes it in ~17s. The check runs inside the adk-bridge container via `docker exec`, using the actual ADK runtime — same code path as a real user message.

**What changed:**
- `reachable` (cheap heartbeat) and `live` (round-trip) are now distinct signals. Two different colors on the graph.
- The roundtrip is cached (`.roundtrip_cache.json`) and refreshed periodically — not run on every graph rebuild or every pulse poll.
- Only agents with CRM tools get the roundtrip check. Others fall back to bridge health for L3.

**Confidence impact: UP.** The green dot now means something. A node showing "live" has actually processed a message end-to-end. The heartbeat is still useful as a fast "is it running?" signal, but it's clearly labeled as `reachable`, not `live`.

**New risk introduced:** The roundtrip is expensive (~17s) and runs inside a Docker container. If the bridge container is down, the check fails — but that's correct behavior. The cache prevents the cost from hitting every graph rebuild. The risk is cache staleness: if the roundtrip succeeds at T=0 and the agent breaks at T=30, the graph shows "live" until the next cache refresh. Mitigation: the pulse endpoint could trigger a refresh when cache is >60s old, but that would block the HTTP response. Better: a cron job that runs `roundtrip_check.py` every 60s and writes the cache.

## Trust Gap 2 — Define what "graduation" actually requires

**Before:** `role: plain -> builder -> orchestrator` was asserted but undefined. No criteria, no enforcement, no operator confirmation.

**After:** Explicit, checkable criteria for each promotion. Operator-confirmed via `/promote` endpoint. Logged to `.promotion_log.jsonl`.

**What changed:**
- `plain → builder`: requires L3 roundtrip + at least one tool + operator confirmation.
- `builder → orchestrator`: requires spawn + wire a child node that reaches `built` + operator confirmation.
- Promotion is never silent self-promotion. The `/promote` endpoint validates the path and criteria before writing.
- Every promotion is logged with timestamp and operator identity.

**Confidence impact: UP.** The role ladder is now real — you can't accidentally promote a node, and you can't promote it to the wrong role. The criteria are checkable, not aspirational.

**New risk introduced:** The criteria are enforced by the promote endpoint, but the graph builder doesn't validate them — it just reads `role` from agents.yaml. A hand-edit to agents.yaml could bypass the promote endpoint. Mitigation: the graph builder could add a `role_valid` field that checks whether the current role is consistent with the agent's gates. A node with `role: builder` but no tools would show `role_valid: false`. This is a future enhancement, not a spike blocker.

## Overall confidence

**UP.** The two gaps were the weakest points in the live-OS premise. Closing them moves the system from "pretty diagram with green dots" to "control surface with verifiable state."

The remaining weakness is the roundtrip cache staleness window (~60s). A cron job to refresh it would close that gap. The promote bypass via hand-editing agents.yaml is a known risk with a clear mitigation path.

**Kill criteria: not triggered.** The roundtrip check is reliable and cheap per slice (17s for ops, cached). Contract-checked wiring doesn't need per-pair custom code — the contract schema is type-derived and the checker is generic.

**Recommendation:** Proceed to the next slice (stability or build). The ops slice is proven end-to-end. The architecture holds.
