# Building an agent

Scaffold and build a new ADK agent through the Forsch Factory. The manifest
(`agent_specs/agents.yaml`) is the single source of truth; the factory generates everything else.

## Steps

1. **Scaffold the manifest block** — `forsch new <id> --description "what it does"`. This adds a
   block to `agent_specs/agents.yaml` (package, adk_name, model_code, web_entrypoint, safety_level
   `read_only`, empty tools) and immediately builds it.
2. **Pick a model** — set `model:` in the block (e.g. `gpt-5.5`, `glm-5.2`). It resolves through the
   LiteLLM gateway; there are no fallbacks, so name a model that's actually served.
3. **Write the instruction** — set `instruction:` to the agent's system prompt. Be concrete about its
   job, its tone, and what it must not do.
4. **Add tools** — `forsch chat` → "add <tool> to <id>", or edit `tools:` in the manifest, then
   `forsch build <id>`. Only tools that pass the deploy gate will build.
5. **Build** — `forsch build <id>` regenerates `agents/<id>/...` and `web_agents/<id>/root_agent.yaml`,
   runs the deploy gate, and syncs the agent into the live graph.
6. **Check** — `forsch check <id>` validates the toolset (the deploy gate) without writing.

## Notes

- Generated files (`agents/<id>/`, `web_agents/<id>/`) are derived — never hand-edit, regenerate.
- `safety_level` gates what the agent may do; start `read_only` and widen deliberately.
- To make it runnable in chat, it must be on the bridge PYTHONPATH (a separate, manual step).
