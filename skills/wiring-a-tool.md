# Wiring a tool

Add an existing Forsch tool to an agent, or create a new shared tool.

## Add an existing tool to an agent

1. **See what exists** — `forsch tools` (or ask the tools_data_specialist). Tools live in
   `forsch.adk_components.tools.*` and are listed in the palette.
2. **Add it** — in `forsch chat`: "add `<tool_name>` to `<agent_id>`". This edits the agent's
   `tools:` list in the manifest and rebuilds. Or edit `tools:` by hand and `forsch build <id>`.
3. **Verify** — `forsch check <id>`. The deploy gate refuses to build an agent whose tools don't
   resolve, so a green check means every tool is real and importable.

## Create a new shared tool

1. **Write the function** — a plain Python function in `packages/adk-components/src/forsch/adk_components/tools/`.
   The docstring becomes the tool description; type hints become the schema. Keep it focused and
   fail loud on bad input.
2. **Test it** — add a test under `components/tests/` (or `packages/adk-components/tests/`) and run the
   component suite in the host venv: `forsch test agents` or the package's pytest.
3. **Export it** so the palette/introspection finds it (module-level function in the tools package).
4. **Wire it** into an agent as above, then `forsch build <id>`.

## Notes

- Never hardcode workspace paths; tools read `FORSCH_ADK_WORKSPACE` and fail loud if it's missing.
- A tool's safety classification feeds the deploy gate — write tools that declare what they touch.
