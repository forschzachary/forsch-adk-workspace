"""Typed plan + verdict for the /goal v2 engine (per the v2 spec).

A goal becomes a persisted GoalPlan of GoalSteps, each bound to a factory actuator and a
success check. The independent Judge returns a Verdict per step. Everything goal-specific is
DATA (these models), never code — a new goal never needs new Python.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

Actuator = Literal["build_agent", "add_tool", "promote_edits", "check_agent", "run_eval", "consult", "manual"]
StepStatus = Literal["pending", "running", "passed", "failed", "blocked"]
PlanStatus = Literal["planning", "executing", "blocked", "done", "abandoned"]
VerdictValue = Literal["pass", "fail", "blocked"]


def new_id(prefix: str = "goal") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class GoalStep(BaseModel):
    id: str
    intent: str                                  # human-readable
    actuator: Actuator
    args: dict = Field(default_factory=dict)
    specialist: Optional[str] = None             # which lane advises (plan time)
    success_check: str                           # what evidence proves this done
    status: StepStatus = "pending"
    evidence: list[str] = Field(default_factory=list)  # real outputs the actuator returned
    attempts: int = 0


class GoalPlan(BaseModel):
    id: str
    goal: str
    steps: list[GoalStep] = Field(default_factory=list)
    status: PlanStatus = "planning"
    cost_usd: float = 0.0
    iterations: int = 0

    def next_actionable(self) -> Optional[GoalStep]:
        """The next step to run: first pending, or a failed step still within its attempt budget."""
        for step in self.steps:
            if step.status == "pending":
                return step
            if step.status == "failed" and step.attempts < 3:
                return step
        return None

    def is_settled(self) -> bool:
        """Every step has reached a terminal state (passed or blocked)."""
        return bool(self.steps) and all(s.status in ("passed", "blocked") for s in self.steps)


class Verdict(BaseModel):
    step_id: str = ""
    reasoning: str                               # CoT: enumerate the units, THEN decide
    verdict: VerdictValue
    failed_criteria: list[str] = Field(default_factory=list)
    minimal_change: bool = True                  # was this the smallest change that works?
    next_directive: Optional[str] = None         # if fail: exactly what to fix
