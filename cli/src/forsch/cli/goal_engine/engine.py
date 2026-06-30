"""The goal engine — an explicit, checkpointed plan->execute->verify->arbitrate loop.

Plain Python around the Runner (NOT an ADK LoopAgent — deprecated in the installed ADK), so the
guardrails are first-class: a max_iterations cap, per-step bounded retries, a stall detector, and
a checkpoint after EVERY step (a crash/restart resumes losslessly from the ledger). The Planner
emits a typed GoalPlan; each step actuates a SAFE verb deterministically; the independent Judge
verdicts the evidence; the loop arbitrates (pass -> done, fail -> retry to a bound, blocked ->
park) and checkpoints. Inject plan_fn/judge_fn/actuate_fn to unit-test the loop without a gateway.
"""
from __future__ import annotations

import os
from pathlib import Path

from forsch.cli.goal_engine.schema import GoalPlan, GoalStep, Verdict

# On failure the engine RE-PLANS — routes the judge's next_directive back to the Planner to amend
# the step's args or insert a fix step — so each retry is a DIFFERENT, corrective attempt, not a
# byte-identical re-run. MAX_ATTEMPTS bounds corrective retries per step; max_iterations bounds the
# whole run; the stall detector parks a goal making no net progress.
MAX_ATTEMPTS = 3
STALL_LIMIT = 4


async def _default_plan(ws: Path, goal: str) -> GoalPlan:
    from google.adk.models.lite_llm import LiteLlm

    from forsch.cli.goal_engine.planner import run_planner
    from forsch.cli.specialists import make_specialist_agenttools

    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    model = LiteLlm(model="openai/gpt-5.5", api_base=base, api_key=key)
    return await run_planner(ws, goal, make_specialist_agenttools(ws, model))


async def _default_judge(ws: Path, step: GoalStep, evidence: list[str]) -> Verdict:
    from forsch.cli.goal_engine.judge import run_judge

    return await run_judge(ws, step, evidence)


def _default_actuate(ws: Path, actuator: str, args: dict) -> str:
    from forsch.cli.goal_engine.actuators import actuate

    return actuate(ws, actuator, args)


async def _default_replan(ws: Path, plan: GoalPlan, failed_step: GoalStep, directive: str) -> dict:
    from forsch.cli.goal_engine.planner import replan

    return await replan(ws, plan, failed_step, directive)


def _apply_delta(plan: GoalPlan, failed_step: GoalStep, delta: dict) -> bool:
    """Apply a corrective delta: insert fix steps before the failed step, amend its args.

    Returns True if anything was applied (-> retry the step), False if the delta was empty (-> park).
    """
    applied = False
    fix_steps = delta.get("fix_steps") or []
    if fix_steps:
        idx = plan.steps.index(failed_step)
        plan.steps[idx:idx] = fix_steps  # fixes run before the failed step retries
        applied = True
    amended = delta.get("amended_args")
    if isinstance(amended, dict) and amended:
        failed_step.args = {**failed_step.args, **amended}
        applied = True
    return applied


def _delta_summary(delta: dict) -> str:
    parts = []
    if delta.get("amended_args"):
        parts.append(f"amended args {delta['amended_args']}")
    fixes = len(delta.get("fix_steps") or [])
    if fixes:
        parts.append(f"inserted {fixes} fix step(s)")
    return "; ".join(parts) or "no change"


async def run_goal(ws: Path, goal: str, *, max_iterations: int = 12, on_event=None,
                   plan_fn=None, judge_fn=None, actuate_fn=None, replan_fn=None,
                   resume_plan: GoalPlan = None) -> GoalPlan:
    """Plan the goal, then loop execute->verify->arbitrate until settled or a guardrail trips.

    Pass resume_plan to continue an existing ledger plan (skips planning; next_actionable() picks
    up exactly where it left off, since passed steps are skipped).
    """
    from forsch.cli.goal_engine import ledger

    plan_fn = plan_fn or _default_plan
    judge_fn = judge_fn or _default_judge
    actuate_fn = actuate_fn or _default_actuate
    replan_fn = replan_fn or _default_replan

    def emit(kind, payload):
        if on_event:
            on_event(kind, payload)

    plan = resume_plan if resume_plan is not None else await plan_fn(ws, goal)
    ledger.checkpoint(ws, plan)
    emit("plan", plan)

    stall = 0
    while plan.iterations < max_iterations:
        step = plan.next_actionable()
        if step is None:
            break
        plan.iterations += 1
        step.status = "running"
        step.attempts += 1
        emit("step_start", step)

        if step.actuator == "consult":
            step.status = "passed"
            step.evidence.append("(consult step — advisory only; nothing actuated)")
            stall = 0
            ledger.checkpoint(ws, plan)
            emit("step_done", step)
            continue

        try:
            evidence = actuate_fn(ws, step.actuator, step.args)
        except Exception as exc:  # actuation must never crash the loop
            evidence = f"[ACTUATION-ERROR] {type(exc).__name__}: {exc}"
        step.evidence.append(evidence)

        verdict = await judge_fn(ws, step, step.evidence)
        emit("verdict", (step, verdict))

        if verdict.verdict == "pass":
            step.status = "passed"
            stall = 0
        elif verdict.verdict == "blocked":
            step.status = "blocked"
            if verdict.next_directive:
                step.evidence.append(f"blocked: {verdict.next_directive}")
            stall = 0
        else:  # fail -> re-plan a corrective delta, else park
            if step.attempts >= MAX_ATTEMPTS:
                step.status = "blocked"
                step.evidence.append(f"gave up after {step.attempts} corrective attempts: {verdict.next_directive or ''}")
                stall += 1
            else:
                delta = await replan_fn(ws, plan, step, verdict.next_directive or "")
                if _apply_delta(plan, step, delta):
                    step.status = "pending"  # retry after the corrective delta (fixes run first)
                    step.evidence.append(f"re-planned: {_delta_summary(delta)}")
                    emit("replan", (step, delta))
                    stall = 0  # a corrective change is progress
                else:
                    step.status = "blocked"
                    step.evidence.append(f"no fix found: {verdict.next_directive or ''}")
                    stall += 1

        ledger.checkpoint(ws, plan)
        emit("step_done", step)

        if stall >= STALL_LIMIT:
            emit("stall", plan)
            break

    if plan.status != "plan_failed":  # preserve a planner parse-failure; don't relabel it
        if not plan.steps:
            plan.status = "abandoned"
        elif plan.is_settled() and all(s.status == "passed" for s in plan.steps):
            plan.status = "done"
        elif any(s.status == "blocked" for s in plan.steps):
            plan.status = "blocked"
        else:
            plan.status = "executing"
    ledger.checkpoint(ws, plan)
    emit("finish", plan)
    return plan
