"""The /goal v2 engine — a persisted, eval-gated, judge-arbitrated execution loop.

A goal becomes a typed GoalPlan; an Operator executes only the safe steps; an independent
Judge (minimax-m3, never the actor) reads the evidence and returns a pass/fail/blocked
verdict; guardrails (cost ceiling, iteration cap, stall detector, the "are you really done?"
nudge, the reuse gate) keep it lazy and bounded; the ledger checkpoints to disk so a crash or
restart loses nothing. Everything goal-specific is DATA (the GoalPlan), never code.

Architecture + rationale: docs/handoffs/2026-06-29-forsch-goal-command.md.
Built bottom-up: schema -> ledger -> actuators -> planner/judge -> guardrails -> engine.
"""
