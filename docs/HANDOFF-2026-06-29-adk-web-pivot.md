# Handoff — 2026-06-29 — ADK Web pivot + surface consolidation

> Box **hubertsp6**, repo `/root/.hermes/workspace/adk` (`forschzachary/forsch-adk-workspace`), `origin/main` gated, box pulls via `deploy.sh`. You author **locally**, PR through the gate, the box deploys. Never hand-edit the box.

## The decision (why this handoff exists)

We were building a custom chat + run-inspection (Chainlit "Hubert cockpit"). Then we found **ADK ships `adk web`** — a built-in dev UI with a robust **trace view** (model calls, tool calls, events, timing, tokens) + eval + session inspection. It's better than anything we'd hand-build for *running + tracing the built agents*. So the architecture pivoted:

| Surface | Role | Status |
|---|---|---|
| **ADK Web** (`adk web`) | dev chat + **trace** of the built agents | **deployed** — `adk-web` systemd svc, tailnet-only `http://100.120.21.13:8002` (no auth → not public) |
| **Live graph** (`packages/live-agent-graph`, `:8888`) | the system map / control surface | keep; **integrate ADK Web into it** |
| **Chainlit** (`chat/`, `adk-chat` svc `:8801`) | repurpose as the **client-facing** product UI | the Hubert/mimo wiring exists; reframe for clients |
| **Gradio bridge** (`bridge/`, `:8800`) | old chat-with-agents surface | **retire** (ADK Web replaces it) |
| **mimo / Claude Code** | the harness Zach vibe-codes *with* (locally) | see `docs/VIBE-CODE-LOCALLY.md` |

Zach is testing agents via ADK Web (`:8002`) right now. Your job is the integration + cleanup below, in parallel.

## Work for you (priority order)

1. **Integrate ADK Web into the live graph.** The graph is the map; clicking an agent/cluster node should open ADK Web's chat+trace for that agent. Investigate ADK Web's URL params (e.g. `?app=<agent>` / app selection) for deep-linking, then either embed it as a tab/iframe in `index.html` (the graph already iframes the bridge at `/chat/*` — same pattern) or link out. Goal: from the map, one click to chat+trace an agent.
2. **Retire the Gradio bridge.** Once ADK Web is the chat surface: remove `bridge/`'s role — the `/chat/*` reverse-proxy in `serve.py`, the `:10000` funnel, the `adk-bridge` container. Do it carefully and verify nothing else depends on it. Land via the gate.
3. **Reframe Chainlit (`chat/`) as the client UI.** Today `cl_app.py` has a `hubert` profile (real mimo harness) + a `claude` profile — that's a *builder* tool. For *clients*, decide the surface: clients chat with the *built* agents (via ADK / LiteLLM), branded, no build-harness access. The theme is already dark precision-instrument (`chat/public/theme.json` + `cockpit.css`); keep/adjust for the client brand. This is its own design pass (see PRODUCT.md, run `/impeccable` if doing it properly).
4. **Local vibe-code enablement.** Confirm `docs/VIBE-CODE-LOCALLY.md` works end-to-end; the one gap is local model access — expose the box's LiteLLM on the tailnet (`tailscale serve` :4000) or document a local LiteLLM, so a fresh clone can `adk web` against a real model.
5. **ADK Web auth (if exposure widens).** It's tailnet-only now because it has no auth. If Zach/clients need it beyond the tailnet, put an auth layer in front (reverse proxy / Cloudflare Access) before any funnel.

## Current state (verified)

- Services: `live-agent-graph` :8888, `adk-api` :8001 (headless agent REST), `adk-chat` :8801 (Chainlit, public funnel), `adk-bridge` :8800 (Gradio), `adk-cockpit` :8780, **`adk-web` :8002 (tailnet-only, new)**. LiteLLM :4000 healthy.
- Agents are env-driven: `LITELLM_BASE_URL`, `LITELLM_HERMES_KEY`, `FORSCH_ADK_MODEL`, `FORSCH_ADK_WORKSPACE` (all `os.environ.get` with defaults). Nothing hardcoded to the box.
- Gate: ruleset `protect-main` (`verify` + `control-plane-approved`, empty bypass). Box authors zero commits.
- Reference library at `docs/reference/` (ADK, Chainlit, Gradio, LiteLLM, MCP, uv, MiMo) — search before guessing.

## How to operate

Author locally → branch → commit → push → `gh pr create` → wait for green (`verify` + `control-plane-approved`, ~20–30s routine) → `gh pr merge --rebase --delete-branch` → `deploy.sh` (or the timer) → **verify with new evidence**. Pushes touching `.github/workflows/` need a token with `workflow` scope (the box PAT lacks it).

## Gotchas

- `deploy.sh` does `git reset --hard origin/main` and removes untracked non-gitignored files (it ate `chat/hubert_soul.md`; gitignored files like `chat.env`, `.serve-env`, `.chainlit/` survive).
- `.chainlit/` is gitignored — `chat/.chainlit/config.toml` was force-tracked to keep the cockpit config in git.
- Chainlit mounts at `/chat` (`mount_chainlit(path="/chat")`), so its `custom_css` + public files live under `/chat/public/...`.
- ADK Web (`adk web`) loads the agents under `agents/`; the `adk-web` unit mirrors `adk-api`'s env. It binds the tailnet IP `100.120.21.13` (not `0.0.0.0`) on purpose — no public exposure.

## Pointers
- `docs/VIBE-CODE-LOCALLY.md` — the local dev loop.
- Memory (Mac): `~/.claude/.../memory/` — `chainlit-hubert-cockpit.md`, `reference-library-and-orchestrator-profile.md`, `monorepo-consolidation-decision.md`.
- Prior handoff: `docs/HANDOFF-2026-06-28-reference-library-and-profile.md`.
