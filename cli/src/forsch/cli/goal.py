"""The /goal command — turbocharged goal pursuit for the forsch operator.

v1 (this file): wraps the user's goal in a structured plan-then-execute directive that drives
the operator to consult its lane-specialists, decompose the goal into concrete factory steps,
execute the safe ones with its verbs, verify with fresh evidence, and report. It rides the
machinery already in the chat (specialists + verbs + the persistent session), so a goal is
pursued inside the same conversation.

The full turbocharged design — a dedicated planner agent, an execute/verify loop with
checkpoints, and a persisted goal ledger — is specced in the handoff
(workspace/handoffs/2026-06-29-forsch-goal-command.md). This module is the seam it grows from.
"""
from __future__ import annotations

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
    """Turn a raw goal into the turbocharged directive sent to the operator."""
    return GOAL_DIRECTIVE.format(goal=goal.strip())
