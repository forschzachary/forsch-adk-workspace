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


async def run_planner(ws: Path, goal: str, specialists: list) -> GoalPlan:
    from google.adk import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from forsch.cli.goal_engine._json import extract_json

    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    model = LiteLlm(model="openai/gpt-5.5", api_base=base, api_key=key)
    agent = Agent(
        name="goal_planner",
        model=model,
        instruction="You plan Forsch Factory work. Consult specialists, then output the plan as JSON only.",
        tools=list(specialists),
    )
    runner = InMemoryRunner(agent=agent, app_name="forsch_goal_planner")
    session = await runner.session_service.create_session(app_name="forsch_goal_planner", user_id="zach")
    content = types.Content(role="user", parts=[types.Part(text=_PLAN_RUBRIC.format(goal=goal))])

    out = ""
    async for event in runner.run_async(user_id="zach", session_id=session.id, new_message=content):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if getattr(part, "text", None):
                    out += part.text

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
    return GoalPlan(id=new_id(), goal=goal, status="executing", steps=steps)
