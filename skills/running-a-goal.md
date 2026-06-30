# Running a goal

`/goal` is the autonomous engine: hand it an outcome, it plans, executes the safe steps, grades
its own work with an independent judge, and parks anything gated for you.

## How it works

1. **Plan** — a Planner (consulting the lane-specialists) turns the goal into a typed plan of
   steps, each bound to a safe verb (`check_agent`, `add_tool`, `build_agent`, `promote_edits`,
   `run_eval`) or `manual` (for anything gated).
2. **Execute** — each step runs its verb deterministically (no guessing).
3. **Judge** — an *independent* model (minimax-m3, never the actor) reads the real evidence and
   returns pass / fail / blocked. Deterministic checks (a green `check`, a passing `eval`) skip
   the judge entirely.
4. **Arbitrate + checkpoint** — pass moves on; fail retries (bounded); blocked is parked with the
   exact manual command. The plan is checkpointed to `goals/<id>.yaml` after every step.

## Commands

- `/goal <text>` — pursue a goal (in chat). Or headless: `forsch goal "<text>" --max-iters N`.
- `/goal list` — your goal runs and their status.
- `/goal status <id>` — the step-by-step state of one goal.
- `/goal resume <id>` — continue an unfinished goal from its last checkpoint (lossless).

## Guardrails (it stays lazy and bounded)

- **Never crosses the gate** — `deploy`/`delete` are not wired in; they're `manual` steps with the
  exact command for you to run.
- **Bounded** — a hard `max_iterations` cap, per-step retry limit, and a stall detector that parks
  a goal making no progress.
- **Lazy** — the planner prefers an existing verb over a new tool; the judge fails bloat
  (`minimal_change=false`) even when the work technically succeeds.

## Good goals

Concrete and verb-shaped: "check every agent's tools validate", "add the `get_grocery_log` tool to
shelby and confirm it builds green", "run shelby's evals and report". Vague goals ("make it
better") plan poorly — say what "done" looks like.
