"""The /goal command — the Forsch Factory autonomous goal engine (v2).

/goal pursues a goal end to end: a Planner (consulting the lane-specialists) emits a typed
GoalPlan; the engine executes the safe steps deterministically; an independent Judge (minimax-m3,
never the actor) verdicts the evidence; the loop arbitrates and checkpoints to goals/<id>.yaml so
it resumes losslessly. deploy/delete never run — they're parked with the exact command for Zach.

Engine lives in goal_engine/; architecture in docs/handoffs/2026-06-29-forsch-goal-command.md.
goal_preamble() is kept as the v1 quick single-pass path (the operator's plain reasoning).
"""
from __future__ import annotations

from pathlib import Path

GOAL_DIRECTIVE = """\
GOAL MODE — pursue this goal end to end, turbocharged. Do not stop at a plan; act on it.

  GOAL: {goal}

Run this loop:
1. CLARIFY only if genuinely blocked (one line). Otherwise proceed on best judgment.
2. CONSULT the relevant lane-specialists before acting — agent_logic_specialist (agent
   config/model/evals), tools_data_specialist (the tool library), interfaces_specialist
   (channels/bridge), router_specialist (clusters/routing). Pull a skill if one fits.
3. PLAN: lay out a concrete, numbered step list. Each step names the verb/tool/specialist it
   uses and its success check. Show the plan first.
4. EXECUTE the safe steps now with your verbs (build, add_tool, promote, check). You may NOT
   deploy to production or delete anything — those stay manual; tell Zach the exact command.
5. VERIFY each executed step with fresh evidence (a check or build result you actually saw),
   never an assumption.
6. REPORT: what's done (with evidence), what's blocked, and the single next move.

Be surgical and concrete. Cite real file paths and real results.
"""


def goal_preamble(goal: str) -> str:
    """v1 quick path: turn a raw goal into a single-pass directive for the operator's reasoning."""
    return GOAL_DIRECTIVE.format(goal=goal.strip())


# --------------------------------------------------------------------------- engine driver

def _status_color(status: str) -> str:
    return {"passed": "green", "failed": "red", "blocked": "yellow", "running": "cyan"}.get(status, "dim")


def _renderer():
    """A rich on_event callback that draws the goal loop on the cosmic theme."""
    from forsch.cli.ui import COSMIC, console

    def render(kind, payload):
        if kind == "plan":
            n = len(payload.steps)
            console.print(f"\n  [{COSMIC}]✦[/] [bold]plan[/] [dim]·[/] {n} step{'s' if n != 1 else ''}  [dim]goals/{payload.id}.yaml[/]")
            for step in payload.steps:
                console.print(f"    [dim]{step.id}[/]  {step.intent}  [dim]({step.actuator})[/]")
            console.print()
        elif kind == "step_start":
            console.print(f"  [{COSMIC}]▸[/] {payload.intent}  [dim]({payload.actuator} · attempt {payload.attempts})[/]")
        elif kind == "verdict":
            step, verdict = payload
            color = _status_color({"pass": "passed", "fail": "failed", "blocked": "blocked"}.get(verdict.verdict, ""))
            tail = "" if verdict.minimal_change else " [yellow](not minimal)[/]"
            console.print(f"    [{color}]{verdict.verdict}[/]{tail}  [dim]{verdict.reasoning[:90]}[/]")
        elif kind == "stall":
            console.print("  [yellow]stalled — no progress; parking the goal[/]")
        elif kind == "finish":
            passed = sum(s.status == "passed" for s in payload.steps)
            total = len(payload.steps)
            console.print(f"\n  [bold]{passed}/{total}[/] passed · status [bold]{payload.status}[/]")
            blocked = [s for s in payload.steps if s.status == "blocked"]
            if blocked:
                console.print("  [yellow]needs you (gated / blocked):[/]")
                for step in blocked:
                    last = step.evidence[-1] if step.evidence else ""
                    console.print(f"    [dim]{step.id}[/] {step.intent} — {last}")
            console.print(f"  [dim]ledger: goals/{payload.id}.yaml · resume: /goal resume {payload.id}[/]\n")

    return render


async def run_goal_async(ws: Path, goal: str, max_iterations: int = 12):
    from forsch.cli.goal_engine.engine import run_goal as engine_run

    return await engine_run(ws, goal, max_iterations=max_iterations, on_event=_renderer())


async def resume_goal_async(ws: Path, goal_id: str, max_iterations: int = 12):
    from forsch.cli.goal_engine import ledger
    from forsch.cli.goal_engine.engine import run_goal as engine_run

    plan = ledger.load(ws, goal_id)
    return await engine_run(ws, plan.goal, max_iterations=max_iterations, on_event=_renderer(), resume_plan=plan)


def run_goal(ws: Path, goal: str, max_iterations: int = 12):
    """Headless entry (`forsch goal "<text>"`) — drives the engine to completion."""
    import asyncio
    import logging
    import os
    import warnings

    from forsch.cli.operator import _load_env

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    _load_env(ws / ".adk-local.env")
    if not os.environ.get("LITELLM_BASE_URL"):
        raise SystemExit("no gateway configured — add LITELLM_BASE_URL + a key to .adk-local.env.")
    return asyncio.run(run_goal_async(ws, goal, max_iterations))


async def handle_goal_command(ws: Path, arg: str) -> None:
    """Dispatch a /goal REPL command: '<text>' | list | status <id> | resume <id>."""
    from forsch.cli.goal_engine import ledger
    from forsch.cli.ui import COSMIC, console

    sub, _, rest = arg.partition(" ")
    sub, rest = sub.strip(), rest.strip()

    if not arg:
        console.print("  [dim]usage: /goal <text>  ·  /goal list  ·  /goal status <id>  ·  /goal resume <id>[/]\n")
        return
    if sub == "list":
        plans = ledger.list_goals(ws)
        if not plans:
            console.print("  [dim]no goals yet[/]\n")
            return
        for plan in plans:
            console.print(f"  [{COSMIC}]{plan.id}[/] [dim]{plan.status}[/]  {plan.goal[:64]}")
        console.print()
        return
    if sub == "status":
        try:
            plan = ledger.load(ws, rest)
        except Exception:
            console.print(f"  [red]no goal '{rest}'[/]\n")
            return
        console.print(f"\n  [{COSMIC}]{plan.id}[/]  {plan.goal}  [dim]({plan.status})[/]")
        for step in plan.steps:
            console.print(f"    [dim]{step.id}[/] [{_status_color(step.status)}]{step.status:<8}[/] {step.intent}")
        console.print()
        return
    if sub == "resume":
        try:
            await resume_goal_async(ws, rest)
        except Exception:
            console.print(f"  [red]no goal '{rest}'[/]\n")
        return
    await run_goal_async(ws, arg)
