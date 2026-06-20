# Open Questions

Use this file for project-level decisions that block durable cleanup or safe continuation. Do not use it as a scratchpad for transient task progress.

## Repository and source layout

- Should `web_agents/*/tmp/*` wrappers remain tracked in `forsch-adk-workspace`, or should the repo keep only the top-level `web_agents/<name>/` wrappers?
- Should future ADK Web wrappers be generated from `agent_specs/agents.yaml`, or hand-maintained until the interface stabilizes?
- Should each existing agent repo (`ops`, `assistant`, `brand`, `build`, `social`) be checked for the same git discipline and pushed state next?

## Runtime and deployment

- Should `adk-bridge` keep sharing the Hermes Discord bot token, or move to a separate ADK bot token once the bridge is stable?
- Should the bridge Docker service definition live in `forsch-adk-bridge`, `forsch-adk-workspace`, or the cloud deploy repo?
- Which model route should be canonical for ADK agents: `FORSCH_ADK_MODEL`, LiteLLM virtual keys, or per-agent config via Authsome?

## Safety boundaries

- What is the threshold for auto-committing docs versus opening a PR for Zach review?
- Should the Stability Governor remain read-only forever, or should a separate repair agent own guarded mutation workflows?

## 2026-06-20 — builder/ commit is local-only (push blocked, needs resolution)

`forsch-adk-workspace` commit **fd39a85** (`feat(builder): metadata parser + package scaffold`) is committed LOCALLY on the box but **NOT pushed** — there is no GitHub credential path on this rebuilt host:
- `GITHUB_TOKEN` unset; no `~/.git-credentials`; `gh` not installed.
- **Authsome CLI not installed on the host** (daemon IS up at `127.0.0.1:7998`, returns 200) — GIT-DISCIPLINE says use `authsome run -- git push`, but the `authsome` binary is absent.

**To unblock push (Zach):** install the Authsome CLI on the host, OR set `GITHUB_TOKEN` for `forschzachary/forsch-adk-workspace`, OR install `gh` with a token. Then: `cd /root/.hermes/workspace/adk && git push origin main`.

Per the handoff rule this note marks the work as intentionally-local-only **only until** a push path exists. Default assumption remains: local-only is unsafe (the box was just reimaged once).
