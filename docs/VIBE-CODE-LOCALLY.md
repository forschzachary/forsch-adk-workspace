# Vibe-code agents locally

The dev loop for building/iterating ADK agents on your own machine, then shipping
to the box through the gate. This is the *author* half of the GitOps setup (the
box only ever **pulls**; you never edit it by hand).

## The loop

```
clone  →  uv sync  →  vibe-code (harness)  →  adk web (test + trace)  →  push  →  gate (CI)  →  box deploys
                          ^___________________________________|
                                   iterate fast, locally
```

1. **Clone** the monorepo: `git clone https://github.com/forschzachary/forsch-adk-workspace`
2. **Sync** the workspace env: `uv sync --all-packages --all-extras` (one lockfile, every member).
3. **Vibe-code** the agent in your harness (mimocode / Claude Code): edit
   `agent_specs/agents.yaml` (the spine) and/or the agent code, then regenerate:
   `factory/.venv/bin/python -m forsch.adk_factory.cli apply --agent <id>`
   (or `uv run python -m forsch.adk_factory.cli apply --agent <id>`).
4. **Test + trace** with the built-in ADK Web UI: `adk web agents` (opens a local
   dev UI — pick the agent, chat, inspect the full trace: model calls, tool calls,
   timing, tokens). This is the run inspection; you don't build it.
5. **Iterate** 3–4. ADK Web hot-reloads agent changes.
6. **Ship**: `git checkout -b <branch>`, commit, push, open a PR. The gate
   (`verify` + `control-plane-approved`) runs; on green, merge; the box pulls and
   deploys. You never touch the box.

You vibe-code in your **harness/editor**, not inside ADK Web. ADK Web is the
test+trace pane next to it.

## Environment (the only setup)

Everything is env-driven (no hardcoded box paths). Set these locally (a `.env` or
your shell), then `adk web` / the agents just work:

| Var | What | Local value |
|---|---|---|
| `FORSCH_ADK_WORKSPACE` | repo root | the absolute path to your clone |
| `LITELLM_BASE_URL` | model gateway (OpenAI-compatible) | see Model access below |
| `LITELLM_HERMES_KEY` | gateway key | matches your gateway |
| `FORSCH_ADK_MODEL` | default model id | e.g. a litellm-proxy model |

### Model access (the one real choice)

The agents call `LiteLlm(api_base=$LITELLM_BASE_URL)`. Point it at a gateway:

- **Reuse the box's LiteLLM over Tailscale** (least setup): expose it on the
  tailnet (`tailscale serve` port 4000 on the box, or bind LiteLLM to the tailnet
  IP), then `LITELLM_BASE_URL=http://100.120.21.13:4000/v1` + the key. Same models
  as production.
- **Run a local LiteLLM** (docker) with your provider keys → `http://localhost:4000/v1`.
- **Point at a provider directly** if it's OpenAI-compatible.

## What lives where (so you don't confuse surfaces)

| Surface | Role | Where |
|---|---|---|
| **ADK Web** (`adk web`) | your dev chat + **trace** of agents | local (and box `adk-web` svc on tailnet `:8002`) |
| **Live graph** | the system map / control surface | box `:8888` |
| **Chainlit cockpit** | the **client-facing** product UI | box `adk-chat` `:8801` |
| **mimo / Claude Code** | the harness you vibe-code *with* | local |

## Don'ts

- Don't edit the box by hand (it resets to `origin/main` on deploy; `git clean`
  removes untracked non-gitignored files).
- Don't hand-edit generated `agents/<id>/` or `web_agents/<id>/` — regenerate.
- Don't commit secrets (`.env`, keys). They stay local / in gitignored env files.
