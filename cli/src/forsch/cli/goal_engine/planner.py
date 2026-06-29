"""The Planner — turns a goal into a typed GoalPlan, consulting the lane-specialists.

A single LlmAgent (the actor model) carrying the four specialist AgentTools. It investigates
the factory, consults the right specialists, and emits a JSON plan: an ordered list of steps,
each bound to a SAFE actuator + args + a success check. Laziness lives in the rubric — prefer
an existing verb over a new tool, smallest change that works, don't invent steps the goal
doesn't need.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from forsch.cli.goal_engine.schema import GoalPlan, GoalStep, new_id

_PLAN_RUBRIC = """You are the Planner for the Forsch Factory goal engine. Turn the GOAL into a
concrete, MINIMAL, ordered plan of steps the engine executes deterministically.

GOAL: {goal}

Consult the lane-specialists (agent_logic_specialist, tools_data_specialist,
interfaces_specialist, router_specialist) as needed to design the plan — investigate first.

Each step uses exactly ONE actuator:
- check_agent     args {{"agent_id":"<id>"}}                    done when: 0 red tools
- add_tool        args {{"agent_id":"<id>","tool_name":"<t>"}}  done when: tool added, check green
- build_agent     args {{"agent_id":"<id>"}}                    done when: build succeeds, gate green
- promote_edits   args {{"agent_id":"<id>"}}                    done when: web edits folded in
- run_eval        args {{"agent_id":"<id>"}}                    done when: eval passes
- manual          args {{"command":"<exact command>"}}         for ANYTHING gated (deploy/delete) — Zach runs it

LAZINESS (enforced): prefer an existing verb over a new tool; prefer zero new files; smallest
change that works. Do not invent steps the goal doesn't need. Never use a deploy or delete
step — those are 'manual' with the exact command for Zach.

Output ONLY a JSON object, no prose, exactly this shape:
{{"steps":[{{"id":"s1","intent":"<short>","actuator":"check_agent","args":{{"agent_id":"shelby"}},"specialist":null,"success_check":"<evidence that proves done>"}}]}}
"""

_REPLAN_RUBRIC = """A step in the plan FAILED. Propose the SMALLEST corrective change, then stop.

GOAL: {goal}
FAILED STEP: {step}
EVIDENCE (what actually happened): {evidence}
JUDGE'S DIRECTIVE: {directive}

You may (prefer the smallest that works):
- AMEND the failed step's args - e.g. a wrong agent_id or tool_name - so it can succeed; and/or
- INSERT one or more FIX steps that must run BEFORE the failed step retries. Each fix step uses a
  SAFE actuator: check_agent / add_tool / build_agent / promote_edits / run_eval / manual.
If the failure needs deploy/delete or a human (not the safe verbs), return an empty delta and, if
useful, a single 'manual' fix step with the exact command.

Output ONLY JSON, no prose:
{{"amended_args": null, "fix_steps": [{{"id":"f1","intent":"<short>","actuator":"add_tool","args":{{"agent_id":"x","tool_name":"y"}},"specialist":null,"success_check":"<proof>"}}]}}
"""


async def _ask_planner(ws: Path, prompt: str, tools=None) -> str:
    """Run the planner LlmAgent (gpt-5.5, optional specialist tools) on a prompt; return its text."""
    from google.adk import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    agent = Agent(
        name="goal_planner",
        model=LiteLlm(model="openai/gpt-5.5", api_base=base, api_key=key),
        instruction="You plan Forsch Factory work. Output JSON only, no prose.",
        tools=list(tools or []),
    )
    runner = InMemoryRunner(agent=agent, app_name="forsch_goal_planner")
    session = await runner.session_service.create_session(app_name="forsch_goal_planner", user_id="zach")
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    out = ""
    async for event in runner.run_async(user_id="zach", session_id=session.id, new_message=content):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if getattr(part, "text", None):
                    out += part.text
    return out


async def run_planner(ws: Path, goal: str, specialists: list) -> GoalPlan:
    from forsch.cli.goal_engine._json import extract_json

    out = await _ask_planner(ws, _PLAN_RUBRIC.format(goal=goal), specialists)
    raw = extract_json(out)
    raw_steps: list = []
    if raw:
        try:
            raw_steps = json.loads(raw).get("steps", [])
        except (json.JSONDecodeError, AttributeError):
            raw_steps = []
    steps: list = []
    for item in raw_steps:
        try:
            steps.append(GoalStep.model_validate(item))
        except Exception:
            continue
    # Empty steps from a real goal almost always means the planner output didn't parse — mark it
    # 'plan_failed' so it's distinguishable from a goal that genuinely needed no work.
    status = "executing" if steps else "plan_failed"
    return GoalPlan(id=new_id(), goal=goal, status=status, steps=steps)


async def replan(ws: Path, plan: GoalPlan, failed_step: GoalStep, directive: str) -> dict:
    """Ask the planner for a corrective delta to a failed step.

    Returns ``{"amended_args": dict|None, "fix_steps": list[GoalStep]}`` — amend the failed step's
    args and/or insert fix steps before it. Empty delta means no safe fix (the engine parks it).
    """
    from forsch.cli.goal_engine._json import extract_json

    prompt = _REPLAN_RUBRIC.format(
        goal=plan.goal,
        step=failed_step.model_dump_json(),
        evidence="\n".join(failed_step.evidence) or "(none)",
        directive=directive or "(none)",
    )
    out = await _ask_planner(ws, prompt)  # no specialists — a focused corrective tweak
    delta: dict = {"amended_args": None, "fix_steps": []}
    raw = extract_json(out)
    if raw:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, AttributeError):
            return delta
        amended = data.get("amended_args")
        if isinstance(amended, dict) and amended:
            delta["amended_args"] = amended
        for item in data.get("fix_steps") or []:
            try:
                delta["fix_steps"].append(GoalStep.model_validate(item))
            except Exception:
                continue
    return delta
