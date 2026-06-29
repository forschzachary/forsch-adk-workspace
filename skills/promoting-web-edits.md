# Promoting web-builder edits

The ADK Web builder (the pencil) lets you edit an agent visually in `web_agents/<id>/root_agent.yaml`.
Those edits are in a generated file — `promote` folds them back into the manifest so they survive.

## Flow

1. **Edit in the web builder** — `forsch web` launches ADK Web + the Forsch Tool Palette. The pencil is
   unlocked because you're serving `web_agents/` (YAML wrappers), not `agents/` (Python). Change the
   model, instruction, description, or tools.
2. **Promote** — `forsch promote <id>` reads `web_agents/<id>/root_agent.yaml` and folds the changed
   fields back into `agent_specs/agents.yaml` (the source of truth), then rebuilds. It reports exactly
   which keys it folded.
3. **Verify** — the manifest now carries your edits; `forsch build <id>` regenerates cleanly and the
   live graph updates.

## Notes

- `web_agents/<id>/root_agent.yaml` is generated and gitignored — never the source of truth. Always
  promote before relying on a web edit.
- Promote preserves tool wildcards and strips the generated group preamble so it round-trips cleanly.
- If `promote` folds "nothing (already in sync)", the manifest already matches the web edit.
