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
