"""The independent Judge — a separate LLM (minimax-m3, NOT the actor) that grades step evidence.

Deterministic checks run FIRST: if a step's success is provable by a check/eval result or an
actuation error in the evidence, return that verdict with no LLM call. Only fuzzy steps reach
the LLM judge, which reads the evidence (never the actor's self-summary), reasons, then returns
a typed Verdict — including minimal_change, which fails bloat even when the work technically
succeeds.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from forsch.cli.goal_engine.schema import GoalStep, Verdict

JUDGE_MODEL = "openai/minimax-m3"

_RUBRIC = """You are an INDEPENDENT Judge for the Forsch Factory goal engine. You did NOT do this
work — you only grade it. Read the step and its EVIDENCE (real tool output) and decide.

Step intent: {intent}
Success check (the criterion): {success_check}
Evidence (what the actuator actually returned):
{evidence}

Decide:
1. Enumerate every piece of evidence the success check requires.
2. If any required evidence is absent, assumed, or contradicted -> verdict "fail".
3. If the work is blocked on a gated/manual action (deploy, delete) -> verdict "blocked".
4. Otherwise -> verdict "pass".
5. minimal_change: false if the change was larger than necessary to meet the check.

Output ONLY a JSON object, no prose, exactly:
{{"reasoning":"<enumerate then decide>","verdict":"pass","failed_criteria":[],"minimal_change":true,"next_directive":null}}
If verdict is "fail", next_directive must state exactly what to fix."""


def deterministic_verdict(step: GoalStep, evidence: list[str]) -> Optional[Verdict]:
    """Grade the cases provable without an LLM; else None (-> the LLM judge).

    Order matters: the unambiguous actuation-crash marker is checked first (it fails ANY actuator),
    then actuator-specific branches. There is no prose-substring catch-all — the check verdict reads
    the structured ``gate-red-count`` the actuator emits, not the spelling of the report.
    """
    text = "\n".join(evidence)
    low = text.lower()

    if "[ACTUATION-ERROR]" in text:
        return Verdict(step_id=step.id, reasoning="the actuator raised an error", verdict="fail",
                       failed_criteria=["actuation error"], minimal_change=True,
                       next_directive="resolve the error shown in the evidence")
    if step.actuator == "manual":
        return Verdict(step_id=step.id, reasoning="manual/gated step — Zach runs it", verdict="blocked",
                       minimal_change=True, next_directive=step.args.get("command", "run the manual step"))
    if step.actuator == "check_agent":
        match = re.search(r"gate-red-count=(\d+)", text)
        if match is None:
            return None  # no machine-readable count -> let the LLM judge read the report
        red = int(match.group(1))
        return Verdict(step_id=step.id, reasoning=f"deploy gate reports {red} red tool(s)",
                       verdict="pass" if red == 0 else "fail",
                       failed_criteria=[] if red == 0 else [f"{red} red tool(s)"], minimal_change=True,
                       next_directive=None if red == 0 else "fix or remove the red tool(s)")
    if step.actuator == "run_eval":
        if "fail" in low:
            return Verdict(step_id=step.id, reasoning="eval scorecard failed", verdict="fail",
                           failed_criteria=["eval below threshold"], minimal_change=True,
                           next_directive="improve the agent or adjust the eval expectation")
        if "pass" in low:
            return Verdict(step_id=step.id, reasoning="eval scorecard passed", verdict="pass", minimal_change=True)
    return None


async def _ask_judge(ws: Path, step: GoalStep, evidence: list[str]) -> str:
    from google.adk import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    judge = Agent(
        name="goal_judge",
        model=LiteLlm(model=JUDGE_MODEL, api_base=base, api_key=key),
        instruction="You are a skeptical, independent judge. Output a JSON verdict only, no prose.",
    )
    runner = InMemoryRunner(agent=judge, app_name="forsch_goal_judge")
    session = await runner.session_service.create_session(app_name="forsch_goal_judge", user_id="zach")
    prompt = _RUBRIC.format(intent=step.intent, success_check=step.success_check,
                            evidence="\n".join(evidence) or "(none)")
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    out = ""
    async for event in runner.run_async(user_id="zach", session_id=session.id, new_message=content):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if getattr(part, "text", None):
                    out += part.text
    return out


async def run_judge(ws: Path, step: GoalStep, evidence: list[str]) -> Verdict:
    det = deterministic_verdict(step, evidence)
    if det is not None:
        return det

    from forsch.cli.goal_engine._json import extract_json

    last = ""
    for _ in range(2):  # one reparse/retry before parking — survives a transient JSON hiccup
        last = await _ask_judge(ws, step, evidence)
        raw = extract_json(last)
        if raw:
            try:
                data = json.loads(raw)
                data["step_id"] = step.id
                return Verdict.model_validate(data)
            except Exception:
                continue
    return Verdict(step_id=step.id, reasoning=f"judge output unparseable after retry: {last[:160]}",
                   verdict="blocked", minimal_change=True, next_directive="re-run the judge")
