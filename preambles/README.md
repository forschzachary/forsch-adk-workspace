# preambles/ — what every built agent is fed

This directory is **one of the two levers** that control what an ADK agent the
factory builds is told to be. Everything an agent is fed comes from exactly two
places, and both are in this repo, operator-owned and gate-protected:

```
final instruction  =  preambles/<group>.md   +   agent_specs/agents.yaml → agents.<id>.instruction
                       └─ the GROUP preamble       └─ the agent's own job
```

There is **nothing else** — no hidden system prompt, no out-of-repo file. If you
want to change what an agent is, you change one of those two files.

## How it works

`factory/renderer.py:compose_instruction(spec, workspace_root)` builds each
agent's instruction as:

```python
preamble = load_preamble(spec.group)        # reads preambles/<group>.md (empty if no group)
instruction = f"{preamble}\n\n{spec.job}"   # preamble first, then the agent's own job
```

So an agent's `group:` field in `agents.yaml` selects which preamble file is
prepended. An agent with no `group:` gets no preamble — only its own
`instruction:`.

## Current preambles

| File | Used by (agents with `group:` = this) | Purpose |
|---|---|---|
| `hubert-team-lead.md` | `assistant`, `build` | Shared Hubert persona + evidence discipline for the team-lead agents |

(The mapping is by the `group:` field in `agent_specs/agents.yaml` — check there
for the live list; do not hardcode it.)

## Editing rules

- **You are strictly in charge here.** These files are the canonical, reviewable
  surface for what your agents are told. Edit them directly.
- A preamble change affects **every** agent in that group at once — that's the
  point (shared persona/discipline lives in one place).
- After editing a preamble or an agent's `instruction:`, **regenerate** the
  affected agents (`factory/.venv/bin/python -m forsch.adk_factory.cli apply
  --agent <id>`) and land the change through the gate.
- This is **Layer B** (the built agents). The orchestrator's own profile (Layer
  A) is the workspace `CLAUDE.md`, not a preamble — see `CLAUDE.md` §6.
