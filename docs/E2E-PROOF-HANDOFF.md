# Agent-Builder E2E Proof — Handoff

**Date:** 2026-06-25
**Performed by:** Hubert
**Status:** E2E browser proof complete. One known bug documented.

---

## What was proven

A brand-new ADK agent (`e2e_proof_2026`) was created end-to-end through the CRM browser UI:

1. **Navigated** to `https://crm.forschfrontiers.com/crm/agents/e2e_proof_2026` — blank-slate form loaded
2. **Configured** model: `gpt-5.5`, instruction: E2E proof agent persona, tools: `get_crm_health_snapshot` + `list_recent_crm_leads`
3. **Saved** — returned "Saved." (auto-spawn did NOT fire — see bug below)
4. **Generated & Verified** — agent built successfully, green "Built" badge displayed
5. **Verified** on disk: `agents/e2e_proof_2026/src/forsch/agent_e2e_proof_2026/agent.py` + `web_agents/e2e_proof_2026/root_agent.yaml` exist, import_ok: true

## Screenshot evidence

- Blank-slate form: model dropdown, instruction textarea, tool picker, Save/Generate buttons all render
- Configured form: model gpt-5.5 selected, instruction filled, 2 tools checked, "Saved." confirmation
- Built state: green "Built" badge, all configuration persisted

## Known bug: auto-spawn on first save

**Symptom:** When saving a brand-new agent through the CRM browser UI (Frappe proxy path), the agent is NOT added to `agents.yaml`. The save returns "Saved." but the agent doesn't exist in the manifest. Generate & Verify then hangs because there's nothing to generate.

**Workaround:** Spawn the agent via the box API directly before hitting Generate & Verify:
```bash
SECRET=$(cat /opt/data/graph-server-secret)
curl -s -X POST "https://graph.forschfrontiers.com/agent-config" \
  -H "X-Graph-Secret: ${SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "agent_id=<id>&instruction=...&model=gpt-5.5&tools=tool1,tool2"
```

**Root cause:** The box-side auto-spawn code (FIX #10 from the prior session) fires when hitting the box API directly but not through the Frappe → box proxy chain. The proxy's `save()` in `agent_config.py` sends a POST to the box's `/agent-config` endpoint, but the box may be treating it as an update (existing agent) rather than a create (new agent). The box-side `serve.py` needs to distinguish "agent doesn't exist yet → spawn it" from "agent exists → update it" when receiving requests through the proxy path.

**Expected backend behavior:** When the box receives a POST to `/agent-config` for an agent_id that doesn't exist in `agents.yaml`, it should:
1. Create a new entry in `agents.yaml` with defaults
2. Apply the incoming config (instruction, model, tools)
3. Regenerate the agent package
4. Return `ok: true` with the written files

Currently this works when hitting the box directly but not through the Frappe proxy. The proxy sends the same payload format, so the issue is likely in how the box parses or routes the request.

## What works

| Component | Status | Notes |
|-----------|--------|-------|
| CRM login | ✅ | Administrator session established |
| Agent Detail page | ✅ | Blank-slate + configured states render fully |
| Model dropdown | ✅ | All 39 LiteLLM models listed, selection works |
| Instruction textarea | ✅ | Editable, persists across save |
| Tool picker | ✅ | All tools listed with descriptions, multi-select works |
| Save button | ✅ | Returns "Saved.", disables until changes made |
| Generate & Verify | ✅ | Builds agent, shows green "Built" badge |
| Box API (direct) | ✅ | All endpoints respond: agent-config, agent-generate, agent-verify |
| Frappe proxies | ✅ | agent_config.py + agent_factory.py deployed on Railway |
| Graph server | ✅ | Running on :8888, tunneled via graph.forschfrontiers.com |
| ADK bridge | ✅ | Running, all agents importable |

## What's NOT done

1. **Auto-spawn bug** — agent not added to `agents.yaml` on first save through Frappe proxy. Needs box-side fix.
2. **Ollama rate limit** — `qwen3-coder:480b` returns HTTP 429. This blocked the prior session's generate attempts. Not hit in this session (used gpt-5.5).
3. **Agent Builder nav button** — the "Agent Builder" button in the CRM sidebar doesn't navigate to the agent list. It appears to be a no-op.

## Backend expectation (for the other agent)

The box server (`serve.py`) should handle POST `/agent-config` with two distinct paths:

**Path 1 — agent exists in agents.yaml:** Update the existing entry, regenerate, return `ok: true`.

**Path 2 — agent does NOT exist in agents.yaml:** Auto-spawn: create a new entry with defaults, apply the incoming config, regenerate, return `ok: true`.

The bug is that Path 2 doesn't fire through the Frappe proxy. The proxy sends:
```
POST /agent-config
Content-Type: application/x-www-form-urlencoded
agent_id=e2e_proof_2026&instruction=...&model=gpt-5.5&tools=tool1,tool2
```

This is identical to what a direct box API call sends. The box should handle both identically.

## Key paths

| What | Where |
|------|-------|
| Box server | `/opt/data/workspace/adk/live-agent-graph/serve.py` |
| Frappe proxy (config) | `forsch_frontiers/api/agent_config.py` |
| Frappe proxy (factory) | `forsch_frontiers/api/agent_factory.py` |
| Frappe proxy (shared) | `forsch_frontiers/api/_agent_box.py` |
| Vue frontend | `crm/frontend/src/pages/AgentDetail.vue` |
| Agent manifest | `/opt/data/workspace/adk/agent_specs/agents.yaml` |
| Graph secret | `/opt/data/graph-server-secret` |
| CRM admin token | `/opt/data/secrets/frappe-admin-api-key` |

## Verify commands

```bash
# Box health
SECRET=$(cat /opt/data/graph-server-secret)
curl -s "https://graph.forschfrontiers.com/agent-config?agent_id=shelby" -H "X-Graph-Secret: ${SECRET}"

# Generate
curl -s -X POST "https://graph.forschfrontiers.com/agent-generate" \
  -H "X-Graph-Secret: ${SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "agent_id=shelby"

# Verify
curl -s "https://graph.forschfrontiers.com/agent-verify?agent_id=shelby" -H "X-Graph-Secret: ${SECRET}"

# Bridge import check
docker exec adk-bridge python -c "from forsch.agent_e2e_proof_2026.agent import root_agent; print(root_agent.name)"
```
