# Google Developer Knowledge MCP

## Purpose

Use Google's Developer Knowledge MCP server as an optional live documentation source for ADK, Gemini, Google Cloud, and related Google developer products.

This is for the ADK vibe-coding loop: coding agents can ask live docs for current ADK APIs before editing agent specs, tools, bridge code, or factory templates.

## Hermes Configuration

Configured in `/opt/data/config.yaml`:

```yaml
mcp_servers:
  google-dev-knowledge:
    url: "https://developerknowledge.googleapis.com/mcp"
    timeout: 120
    connect_timeout: 30
    sampling:
      enabled: false
```

A backup was written before editing:

```text
/opt/data/config.yaml.bak-google-dev-mcp-<timestamp>
```

## Verification

Run:

```bash
hermes mcp list
hermes mcp test google-dev-knowledge
```

Expected result:

```text
✓ Connected
✓ Tools discovered: 3
```

Tools discovered on 2026-06-20:

- `search_documents` - search official Google developer documentation.
- `answer_query` - grounded synthesized answer from the same corpus; quota-limited.
- `get_documents` - retrieve full document content by document name.

## Runtime Notes

- Restart Hermes/gateway before expecting the MCP tools inside normal agent sessions.
- Tool names in Hermes should be prefixed as `mcp_google_dev_knowledge_*` after discovery.
- The endpoint allows MCP initialize/tool listing without auth, but actual tool calls returned `401 Unauthorized` in a raw unauthenticated probe. Hermes can connect and discover tools; authenticated calls may still require Google credentials depending on Google's policy.
- Prefer ADC if authentication becomes required. Do not put static Google API keys in workspace docs or committed configs.

## How To Use In Agent Work

Before accepting ADK code from a coding assistant, query the MCP server for the current docs on the exact concept:

- ADK Agent constructor and `instruction` field.
- ADK `Runner` and session services.
- ADK Web entrypoint format.
- ADK workflow/graph APIs.
- ADK custom tool signatures and docstring requirements.
- LiteLLM integration in ADK.

The MCP server is a documentation source, not a source of truth for our architecture. Our source of truth remains:

- `agent_specs/agents.yaml` once created.
- `forsch-adk-components` for shared tools/models.
- generated agent packages.
- `bridge` for Discord I/O.
- ADK docs and verified runtime tests.

## Failure Mode

If MCP calls fail:

1. Use `hermes mcp test google-dev-knowledge`.
2. Check whether Hermes needs restart.
3. Check whether Google now requires ADC/OAuth for tool calls.
4. Fall back to direct ADK docs at `https://google.github.io/adk-docs/`.

Do not block agent factory work on this MCP server. It is an antenna, not a foundation.
