# Reusable Agent Cockpit

This is the copyable contract behind the Live Agent Graph Hubert sidecar. It is intentionally small: a model selector, a chat request, and a run receipt that can render progress, tool usage, diagnostics, and a final assistant response.

## Backend Contract

`GET /models`

```json
{
  "models": ["default", "openai/gpt-5.4"],
  "source": "mimo-cli",
  "default_model": "default",
  "health": {
    "default": {"state": "ready", "note": "MiMo default"}
  }
}
```

`POST /chat`

```json
{
  "message": "[cluster: demo] Build the next step",
  "session_id": "optional-existing-session",
  "model": "default"
}
```

Response:

```json
{
  "ok": true,
  "response": "Assistant text",
  "session_id": "mimo-session-id",
  "model": "default",
  "elapsed_ms": 3200,
  "progress": {
    "state": "complete",
    "label": "assistant response ready",
    "current_event": {"type": "completed", "label": "assistant response ready", "status": "ok"}
  },
  "events": [
    {"type": "queued", "label": "request accepted", "status": "ok", "at_ms": 0},
    {"type": "subprocess", "label": "MiMo CLI started", "status": "running", "at_ms": 0},
    {"type": "completed", "label": "assistant response ready", "status": "ok", "at_ms": 3200}
  ],
  "tools": [
    {"name": "read_file", "status": "finished", "at_ms": 900, "preview": "optional bounded detail"}
  ],
  "diagnostic": null
}
```

Failures use the same shape with `ok: false`, `progress.state: "error"`, and a `diagnostic` object:

```json
{
  "code": "MODEL_UNAVAILABLE",
  "message": "model not available on this box: example/model",
  "status_code": 400,
  "model": "example/model",
  "next_action": "Choose a listed model from the selector and retry."
}
```

## Frontend Hooks

The sidecar needs these replaceable functions:

- `apiUrl(path)`: route local, embedded, or proxied endpoints.
- `graphSecretHeaders()`: return auth headers if the host app uses a shared secret or bearer token.
- `renderChatModelOptions(payload)`: render the model catalog.
- `startPendingHubertRun(model, contextLabel)`: show optimistic request progress while waiting for `/chat`.
- `normalizeRunReceipt(data, fallbackModel, ok)`: convert backend responses into the UI receipt.
- `renderRunPanel(run)`: display stages, tools, elapsed time, and diagnostics.
- `chatFailureText(status, data, err)`: convert HTTP/backend failures into user-facing copy.

## Fork Points

- Prompt chips: project-specific starter prompts.
- Context builder: graph, selected node, file path, project, customer, or task state.
- Model catalog: MiMo, ADK, OpenAI, local Ollama, or a fixed allowlist.
- Tool/event adapter: keep the `events[]` and `tools[]` shape even if the underlying runner is not MiMo.
- Auth: Cloudflare Access, shared graph secret, bearer token, or local-only.

## Design Bar

- Show progress immediately after send.
- Show tool/event receipts after completion when available.
- Never flatten failures to `unknown`; include a stable code, plain message, and next action.
- Keep event/tool previews bounded. The cockpit is a workbench, not a log dump.
- Preserve the same response shape for success, backend failure, auth failure, and rate limit.
