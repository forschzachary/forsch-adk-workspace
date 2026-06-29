# Handoff — the turbocharged `forsch chat` `/goal` command

> **For Zach's brainstorm.** This captures the dream, what already exists (v1, shipped), the
> building blocks on hand, how Claude-Code-style goal commands work and how to *exceed* them,
> and the open design questions to settle. Bring a robust spec back from this and the
> implementation steps at the end are ready to execute.

## The dream

A `/goal <something I want>` in `forsch chat` that works like the goal/plan commands you'd find
in Claude Code and friends — decompose, plan, execute, track — but **turbocharged**: it leans on
the whole Forsch Factory (the lane-specialists, the safe verbs, the deploy gate, the live graph,
the eval flywheel, persistent sessions) to actually *pursue and finish* a goal, not just draft a
checklist. You say the goal; it plans with the right experts, does the safe work itself, verifies
with real evidence, and tells you the one manual step it can't take.

## What exists today (v1 — shipped, working)

- **The seam:** [`cli/src/forsch/cli/goal.py`](../../cli/src/forsch/cli/goal.py) — `goal_preamble(goal)`
  wraps your goal in a structured *plan → consult specialists → execute safe steps → verify → report*
  directive.
- **The dispatch:** [`cli/src/forsch/cli/operator.py`](../../cli/src/forsch/cli/operator.py) `_loop`
  — typing `/goal <text>` sends that directive into the current session, so the goal is pursued
  inside the same conversation (and persists with it).
- **What it rides (all live):**
  - **Persistent sessions** — SQLite (`.forsch/sessions.db`); a goal's progress survives restarts.
  - **4 lane-specialists** ([`specialists.py`](../../cli/src/forsch/cli/specialists.py)) — agent-logic,
    tools-data, interfaces, router — wrapped as AgentTools the operator consults in the background.
  - **Skills** ([`skills.py`](../../cli/src/forsch/cli/skills.py)) — loadable how-to it can pull mid-task.
  - **Safe verbs** (`build`, `add_tool`, `promote`, `check`) + the **deploy gate** (deploy/delete stay manual).
  - **Live-graph sync** — every build mirrors into the map.
  - **The eval flywheel** (`forsch eval`) — available as a verification step.

**What v1 is NOT (yet):** it's a single-pass, LLM-driven directive. No explicit plan ledger, no
persisted goal state separate from the chat, no enforced execute→verify loop, no parallel
fan-out across specialists, no checkpoints, no resumable `/goal status`. That's the brainstorm's job.

## Building blocks on hand

| Block | Where | Use for `/goal` |
|---|---|---|
| `PlanReActPlanner` | `google/adk/planners/plan_re_act_planner.py` | Emit a structured plan (PLANNING/ACTION/REASONING tags) — attach via `LlmAgent.planner` |
| `BuiltInPlanner` | `google/adk/planners/built_in_planner.py` | Use the model's native thinking for decomposition |
| `SequentialAgent` / `LoopAgent` / `ParallelAgent` | `google/adk/agents/*_agent.py` | Orchestrate steps — **NOTE: flagged deprecated in favor of ADK Workflow; verify in current google-adk and prefer the Workflow/graph API if so** |
| The 4 specialists | `specialists.py` | Per-layer design + (future) per-layer execution |
| The safe verbs | `operator.py:_make_tools` | The actuators a plan step calls |
| Persistent sessions + state | `operator.py:_session_service` | Persist a goal ledger in session state |
| The eval flywheel | `cli/src/forsch/cli/evals.py` | Eval-gated "done" |
| `before/after_agent_callback` | ADK `LlmAgent` | Feed verifier output back to the planner (re-plan) |

## How Claude-Code-style goal commands work — and how to exceed them

**Baseline:** decompose a goal into a todo list, execute step by step, check items off, surface progress.

**Turbocharge directions (pick + combine in the brainstorm):**
- **Dedicated planner agent** (`PlanReActPlanner`) that emits a typed `GoalPlan` (steps, each with the
  verb/specialist it uses and a success check) instead of freeform prose.
- **Persisted goal ledger** — a `goals/<id>.yaml` (or session state) so a goal is resumable:
  `/goal resume <id>`, `/goal status`.
- **Execute → verify loop** — after each step, verify with *real evidence* (a `check`, a `build`, an
  eval); on failure, re-plan from the verifier's feedback (LoopAgent or a custom loop + callback).
- **Parallel specialist fan-out** — independent subgoals run concurrently (ParallelAgent / Workflow).
- **Checkpoints / human gates** — pause before anything irreversible; deploy + delete always manual.
- **Live progress rendering** — a rich plan tree that updates as steps complete (mirror the workflow
  progress UI: step status, evidence log).
- **Eval-gated completion** — a goal isn't "done" until its acceptance evals pass.

## Open design questions (settle these in the brainstorm)

1. **Autonomy** — how far does `/goal` act without confirming? Where are the gates?
2. **Plan representation** — freeform vs a typed `GoalPlan`/`GoalStep` schema? Persisted where?
3. **Execution engine** — one planner-agent loop, or multi-agent orchestration (Sequential/Loop/Parallel/Workflow)?
4. **Verification** — what counts as "done": a check, a build, an eval, your sign-off?
5. **Resumability** — should a goal survive restart with `/goal resume`/`/goal status`?
6. **Specialist role** — advisors only, or can a specialist *execute* within its layer?
7. **Failure handling** — auto-replan, or stop-and-ask?
8. **Observability** — how should progress render (plan tree, step status, evidence)?

## Concrete next steps (once the design is set)

1. Define `GoalPlan` + `GoalStep` (id, intent, verb/specialist, args, success_check, status, evidence).
2. Build a **planner agent** (`PlanReActPlanner`) that turns a goal into a `GoalPlan`.
3. Build the **execution loop**: actuate each step with the verbs, consult specialists, verify, re-plan on fail.
4. **Persist the ledger** (session state or `goals/<id>.yaml`) for resume/status.
5. **Render progress** as a rich plan tree (reuse the `ui.py` cosmic theme).
6. Wire `/goal new`, `/goal resume <id>`, `/goal status`; keep `/goal <text>` as the quick path.

## Pointers

- Seam: [`cli/src/forsch/cli/goal.py`](../../cli/src/forsch/cli/goal.py)
- Dispatch + REPL: [`cli/src/forsch/cli/operator.py`](../../cli/src/forsch/cli/operator.py)
- Specialists: [`cli/src/forsch/cli/specialists.py`](../../cli/src/forsch/cli/specialists.py)
- Skills: [`cli/src/forsch/cli/skills.py`](../../cli/src/forsch/cli/skills.py)
- Verify-by-eval: [`cli/src/forsch/cli/evals.py`](../../cli/src/forsch/cli/evals.py)
- ADK planners: `google/adk/planners/`; orchestration: `google/adk/agents/{sequential,loop,parallel}_agent.py`
- Original specialist design (Hubert factory-bot): `packages/live-agent-graph/docs/compose/specs/2026-06-27-hubert-factory-bot-design.md`

---

## v2 build status + v2.1 backlog (post-review)

**v2 is built, tested, and reviewed** — PR #33: `66258c6` (foundation), `a75dae0` (engine), `ed5c57b`
(minimax-m3 judge), `726a09c` (review fixes). Zach reviewed `goal_engine/` as judge; all findings
fixed. Skeleton, persistence, independent judge, and gate-by-absence are solid and shippable.

**v2.1 — corrective agency (the #1 next thing).** Today a failed step parks immediately
(`MAX_ATTEMPTS=1`) with the judge's `next_directive` surfaced — honest, but the execute phase
can't yet *act on* the directive. That's the gap between "run all night" and "fail once, then
stop." The fix (pick one):
- **Re-plan on fail** — route `next_directive` back to the Planner to emit a delta (amend the
  step's args, or insert a fix step before it), then continue. Cleanest; keeps execution
  deterministic.
- **Operator actuator** — a step type that hands the directive to an LLM operator with the verbs,
  so it can adjust and retry. Same muscle as the deferred PlanReAct planner + the reuse-gate.

**Also deferred (seams in place):**
- **$-cost ceiling** — a `before_model_callback` tracking cumulative cost, ending the run cleanly
  at a budget. `cost_usd` is the (inert) field for it. `max_iterations` is the bound until then.
- **`LongRunningFunctionTool`** — true overnight pause-at-approval / resume-on-signal, vs today's
  park-and-report.
- **Reuse gate** — the X-line `before_tool_callback` that promotes oversized inline glue into a
  shared tool (relevant once an Operator actuator can write code).
