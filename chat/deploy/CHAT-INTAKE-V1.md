# ADK Chat Intake V1

## Funnel URL
https://hubert-cloud-sp6.tail818cf8.ts.net/chat

## Authentication
Pass `?chat_token=<CHAT_TOKEN>` (or set `chat_token` cookie). Token is in
`chat/chat.env` (gitignored). The TokenBridge ASGI middleware (in `http.py`)
reads the QS param, injects it as `x-chat-token`, and sets a session cookie so
subsequent WS frames authenticate automatically.

## Environment variables (chat/chat.env — gitignored)
| Var | Purpose |
|-----|---------|
| `IS_SANDBOX=1` | Lets the Claude SDK run as root without --dangerously-skip-permissions error |
| `HOME=/root` | Claude CLI finds its auth at /root/.claude |
| `CHAT_TOKEN` | Bearer secret — QS param or cookie |
| `CHAINLIT_AUTH_SECRET` | Read at import time by mount_chainlit; must be present |
| `LITELLM_BASE` | http://127.0.0.1:4000 — local LiteLLM proxy |
| `LITELLM_HERMES_KEY` | sk-* for the proxy |
| `HUBERT_SOUL_PATH` | Path to hubert_soul.md (copy of container SOUL.md) |
| `CHAT_HOST / CHAT_PORT` | 127.0.0.1:8801 |
| `PYTHONPATH` | /root/.hermes/workspace/adk/chat/src |

## How the two backends dispatch
`cl_app.py` exposes two ChatProfiles:

- **hubert** — sends to LiteLLM at `LITELLM_BASE` on model `gpt-5.5` via
  `stream_hubert()` (in `hubert.py`). System prompt = SOUL.md + chat-voice
  modifier. No tool use.
- **claude** — spawns a persistent `ClaudeSDKClient` per user session
  (`claudewrap.py` + `claude-agent-sdk`), with `cwd=/root/.hermes/workspace/adk`
  and `permission_mode=bypassPermissions`. Full tool use live in the workspace.
  Tool steps render as Chainlit Step elements.

Dispatch key in `cl_app.py on_message`:
```python
who = cl.user_session.get("who")  # "hubert" or "claude"
if who == "hubert": stream via LiteLLM
else: route to ClaudeSDKClient
```

## Adding a new profile
1. Add a `cl.ChatProfile(name="newprofile", ...)` to the `profiles()` list in `cl_app.py`.
2. Add a dispatch branch in `on_message()` for `who == "newprofile"`.
3. Restart: `systemctl restart adk-chat`.

## Service management
```bash
systemctl status adk-chat
systemctl restart adk-chat
journalctl -u adk-chat -n 50 --no-pager
```

## Funnel
Managed by Tailscale: `tailscale funnel --https=443 http://127.0.0.1:8801`
Run `tailscale funnel status` to verify. The :443 funnel is public on the internet
(not just tailnet).

## Verified (2026-06-21)
- **Hubert**: replied "for taco night: tortillas, protein, taco seasoning/spices, onion,
  cilantro, limes, shredded cheese, salsa" — lowercase voice, gpt-5.5 via LiteLLM.
- **Claude**: rendered tool steps `tool: Bash` and `tool: Read` proving real tool-use
  and bypassPermissions in the workspace. Reply streamed successfully.
