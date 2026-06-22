# Hubert "still dying" — root cause + the native-fallback fix (2026-06-20)

## TL;DR
Hubert was dying with `API failed after 3 retries — Connection error` and later a Gemini `400`. It was **not one bug** — it was a stack of four, and the fix was to stop fighting it in litellm and configure fallback **the native Hermes way** per the official docs. All four are now fixed; one thing remains *unobserved-but-configured*.

---

## The presenting symptoms
1. `❌ API failed after 3 retries — Connection error` on `model=gpt-5.5` (48× in 6h).
2. `❌ Non-retryable error (HTTP 400): Code Assist HTTP 400: "Please ensure that the number of function response parts is equal to the number of function call parts…"`
3. User's framing: *"Codex has always been reliable and I have plenty of space — but it's still dying."*

## What was actually happening (four distinct failures, untangled)

**1. The "Connection error" was the proxy being down — not Codex.**
litellm logged **zero** chatgpt/codex connection errors; the errors were hermes→`127.0.0.1:4000` (litellm itself) during litellm restarts. A heavy gpt-5.5 call returned **HTTP 200 in 1.44s** — Codex is fast. The restarts came from an **every-minute deploy-runner cron** (`/root/cloud-deploy/hubert-deploy-runner.sh`) that did `docker rm -f litellm` + overwrote live config on each fire (now inert — its script path was orphaned at 15:38), plus session restarts. Compounded by litellm running a **single uvicorn worker** → every restart = a full ~30s blackout.

**2. "Codex is reliable" was false here.** litellm logs, last 6h: **63× HTTP 429 + 54 timeouts** on gpt-5.5. "Plenty of space" (quota/credits) ≠ no **rate limit** — the ChatGPT/Codex OAuth backend throttles per-window. So gpt-5.5 *does* fall back.

**3. …and the entire fallback chain was also broken.** When gpt-5.5 fell back: Claude capped (10× "out of extra usage"), Gemini-pro capped (12× "exhausted your capacity" 429s), **`gemini-2.5-pro` had no fallback entry** → 30× `No fallback model group found` dead-ends, and 15× `MidStreamFallbackError` (litellm can't fall back once a fake-stream is mid-flight).

**4. The Gemini 400 was a real handler bug.** The Code Assist handler emitted each tool result as its own single-part turn, so N **parallel** tool calls were answered by N one-part turns — Gemini requires one N-part turn. Single tool calls worked (1→1), which is why it slipped past the earlier integration test.

## The root insight
Fallback was bolted onto **litellm** (middleware) — where it fails mid-stream and has per-model holes. The official Hermes docs are explicit: **fallback is a Hermes-native concern, not delegated to middleware.** Hermes has a native `fallback_providers` that re-issues the *whole turn* on the next provider (clean, no mid-stream). It was sitting empty (`[]`) on cloud while everything ran through litellm. **That's the "configured wrong originally."**

---

## Fixes applied (all verified)

### A. Gemini parallel-tool-call fix
`~/Dev/cloud/hubert/litellm/gemini_code_assist_handler.py` — `_messages_to_contents` now **buffers a run of `tool` results and flushes them as one turn** (N functionCall parts ↔ N functionResponse parts). TDD: added `test_messages_to_contents_parallel_tool_calls_grouped`; **19/19 pass**. Deployed to box (byte-matched), litellm restarted; the exact failing 2-call payload now returns **HTTP 200** with a correct answer.

### B. Native Hermes fallback (the main fix) — per official docs
- Official schema (no inferred fields): each entry = `{provider, model, base_url?, key_env?}`. Docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers
- **`/root/.hermes/config.yaml`** `fallback_providers` now:
  `gpt-5.5` (primary) → claude-sonnet-4-6 → gemini-2.5-pro → gemini-2.5-flash → nvidia-nemotron-30b — each `provider: litellm, base_url: http://127.0.0.1:4000/v1, key_env: LITELLM_HERMES_KEY`.
- **litellm main-brain fallback removed** (`gpt-5.5:` + `claude-sonnet-4-6:` lines) so the primary's 429 surfaces cleanly to Hermes; litellm keeps only aux smart-routing.
- Triggers (official): 429 / 500-503 / 401/403/404/invalid — **NOT 400**. So the Claude cap-remap (400→429) and the Gemini parallel-fix (no more 400) are load-bearing: they make caps surface as 429s the native chain catches.
- Verified via `docker exec hermes hermes fallback list` (primary + 4-entry chain), gateway restarted + reconnected to Discord, `RestartCount=0`.
- **Correction noted:** an earlier attempt added a non-official `api_mode` field (inferred from the primary block). Removed — official schema only. (Saved as a preference: follow official docs over local/inferred config.)

### C. s6-log lock — Hubert's file-logs were frozen since 22:38
The `adk-bridge` container (built from the hermes image, shares the `/root/.hermes` bind-mount) ran a **duplicate `gateway-default/log` service** squatting the write-lock on `/root/.hermes/logs/gateways/default/lock`. Disabled it; restarted Hubert's logger:
`docker exec adk-bridge /command/s6-svc -d /run/service/gateway-default/log`
`docker exec hermes     /command/s6-svc -r /run/service/gateway-default/log`
Verified: lock-errors **6→0**, `current` unfroze (22:38 → live, growing). **Not restart-proof** — re-run if adk-bridge restarts; durable fix = adk-bridge shouldn't run gateway/dashboard services (compose/image change).

### D. Repo durability — committed so a deploy won't revert it
The deploy seeds both files from the repo, and both would have clobbered the box:
- `config/hubert.config.yaml` had a *third* fallback variant (`ollama-cloud/deepseek`) → replaced with the official chain.
- `litellm/config.yaml` still had the main-brain fallback → removed + comment updated.
Committed + pushed: **`58016c4` on `forschzachary/hubert-cloud` `main`**.

---

## Current state
- **Resolved:** the connection-error storm (root cause was proxy churn + the broken every-minute cron, now inert), the Gemini parallel-400, the dead-end fallback holes, the mid-stream fallback failures, the frozen file-logs, and repo drift.
- **Configured + loaded + parses, but not yet OBSERVED in the wild:** an actual gpt-5.5 throttle re-issuing to Claude. Offer standing: tail the (now-working) gateway logs until the next natural 429 and confirm it fires.
- **Not restart-proof:** the adk-bridge s6-log disable (C).

## Adjacent finding (not acted on)
**LiteLLM Agent Control Plane** (`LiteLLM-Labs/litellm-agent-control-plane`, pushed 2026-06-20) ships a **Hermes runtime template** — Hermes behind the Anthropic Managed Agents API, all provider creds/routing centralized on LAP. Strong candidate as a future control-plane layer (Hubert as one runtime among many). Note: its Hermes bridge currently flattens tool frames; it's day-0 infra. Left as a forward-looking option, not a task. **No nuke/rebuild** — explicitly off the table.

## Key locations / commands
- Box: `ssh -i ~/.ssh/zachfleet_vps root@87.99.149.222` (TS `100.120.21.13`).
- Native fallback: `docker exec hermes hermes fallback list` (manage via `hermes fallback add/remove`).
- Repo: `~/Dev/cloud/hubert` → `config/hubert.config.yaml` (hermes), `litellm/config.yaml` (litellm). Remote `forschzachary/hubert-cloud`.
- Config backups on box: `/root/.hermes/config.yaml.bak-pre-native-fb-*`, `/root/.hermes/litellm/config.yaml.bak-pre-native-fb-*`.
- Memory: [[project_hermes_native_fallback_2026_06_20]], [[feedback_official_docs_over_local_config]], [[project_litellm_canonical_routing_2026_06_20]].
