# Chainlit CRM chat surface — Phase 1 (LIVE)

The native adk-bridge container now runs the Chainlit chat server (was the
Discord listener). Discord is a stub per the chat-surface design.

- Server: `python -m forsch.adk_bridge.http` (uvicorn on 127.0.0.1:8800).
  FastAPI `/healthz` + Chainlit mounted at `/chat`.
- Funnel: `tailscale funnel --bg --https=10000 http://127.0.0.1:8800`.
  NOTE: the plan said 8444, but Tailscale Funnel only allows ports
  443 / 8443 / 10000. 8443 is the Builder cockpit, so the chat uses 10000.
- Auth: Chainlit `header_auth_callback` checks `X-Chat-Token` == $CHAT_TOKEN
  (bridge.env). A token-bridge ASGI middleware in http.py lets a plain iframe
  `/chat?chat_token=TOKEN` authenticate (query/cookie -> injected header).
- Model: bridge.env FORSCH_ADK_MODEL must carry an `openai/` provider prefix
  (`openai/nvidia-deepseek-v4-flash`) — the rebuilt image's newer litellm
  requires it when api_base points at the litellm proxy.
- CRM page: Frappe Web Page route `/agent-chat` (site crm.forschfrontiers.com),
  iframes the funnel `/chat?chat_token=…`. Recreate via
  deploy/make_agent_chat_page.py (replace __CHAT_TOKEN__) through bench console.

Revert to the Discord bridge: set Dockerfile CMD back to
`["python","-m","forsch.adk_bridge.bridge"]` + rebuild.

## Operational gotcha — bridge.env changes require RECREATE, not restart
`env_file` (bridge.env) is read at container CREATE, not on `docker restart`.
So editing bridge.env (e.g. adding per-agent `ADK_LITELLM_KEY_*` keys) and then
`docker restart adk-bridge` does **NOT** load the new vars — agents silently fall
back to the shared `LITELLM_HERMES_KEY` (looks fine, but the per-agent keys are
never used). To apply bridge.env changes:

    cd /root/.hermes/workspace/adk/bridge && docker compose up -d

Then verify the new env is actually in the container:

    docker exec adk-bridge printenv ADK_LITELLM_KEY_STABILITY

(Agents build their `LiteLlm` at import time, so the env must be present at
container create. Per-agent model strings need the same `openai/` provider
prefix as `FORSCH_ADK_MODEL`, see the Model note above.)
