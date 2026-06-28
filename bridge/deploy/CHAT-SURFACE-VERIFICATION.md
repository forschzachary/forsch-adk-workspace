# Chat Surface — End-to-End Verification (2026-06-21)

Independent end-to-end verification of the Chainlit `/chat` surface + per-agent
LiteLLM keys + regenerated agent packages, run after both landed. Driven with
Playwright (headless chromium) against the **live** site through the public
Tailscale Funnel, using a pure iframe-style URL `…:10000/chat?chat_token=<CHAT_TOKEN>`
— i.e. exactly the path the CRM iframe uses (no header injection).

## 1. Health (container)
- `docker exec adk-bridge printenv | grep ADK_LITELLM_KEY_` → **6 keys, 6 distinct values**
  (STABILITY/OPS/BUILD/ASSISTANT/BRAND/SOCIAL).
- `FORSCH_ADK_MODEL=openai/gpt-5.5`.
- `docker logs --tail 30 adk-bridge` → 0 error/traceback lines.

## 2. Bug found + fixed: double-reply  (commit 5bb2732)
Live `/chat` showed every reply rendered twice (also doubled in a pure-string
brain check, so not a DOM artifact). Diagnostic on the raw ADK event stream:

```
EV[1..6] partial=True  -> "Hel" "lo" ... (the streamed deltas)
EV[7]    partial=False final=True -> "Hello, happy to help!"  (FULL text again)
```

Root cause: `run.tokens_from_events` yielded the streamed deltas **and** the
final aggregated event (which repeats the whole message). Fix: stream only
`partial=True` deltas; emit the final aggregate **only** when nothing was
streamed (non-streaming fallback). Test updated to model the real partial+final
shape (the prior test used an empty final event, which masked the bug).
Verified single reply live after `docker restart adk-bridge`.

## 3. Per-profile surface sweep — 6/6 PASS
For each ChatProfile: switch via the profile selector, confirm the "Create New
Chat" dialog, verify the bound agent (header chip + "Connected to <agent>"
greeting), send "In one short sentence, name your agent role.", capture the
assistant reply, assert no doubling.

| Profile | Header chip | Greeting | Reply (role) | Doubled |
|---|---|---|---|---|
| stability | stability | Connected to stability | read-only stability governor for the Forsch ADK workspace | no |
| ops | ops | Connected to ops | ops team lead for Forsch | no |
| build | build | Connected to build | Product and engineering lead for Forsch | no |
| assistant | assistant | Connected to assistant | Personal assistant lead for Forsch | no |
| brand | brand | Connected to brand | Brand and marketing lead for Forsch | no |
| social | social | Connected to social | social media lead for Forsch | no |

Each agent returns a **distinct, role-correct** reply → the right agent (its own
per-agent key + instruction) answered. SUMMARY: 6/6 passed.

## Automation notes (for repeatability)
- Assistant messages: `.ai-message` elements (user bubbles lack the class). Capture
  the **last** `.ai-message`, polled until stable.
- Profile selector: Radix **`role=combobox`** (the "<agent> v" chip, top-left).
  Options: **`role=option`** with the agent name. Switching mid-chat opens a
  confirm dialog **"Create New Chat … clear your current chat history"** → click
  the **Confirm** button before the input is usable again.
- Bound-agent signal: `on_chat_start` posts "Connected to <agent>." (first
  `.ai-message` of a session).
- Tooling: ephemeral `uv venv` + `playwright install chromium` (installed for the
  run, removed after — NOT a box dependency).

## Latent (not fixed — surgical)
The dormant Discord/CRM buffer path in `bridge.py` (`_run_agent_text`) feeds every
event incl. the final aggregate, so it would double **if re-enabled**. It is
stubbed today (container CMD = the http/Chainlit server). Flagged, untouched.
