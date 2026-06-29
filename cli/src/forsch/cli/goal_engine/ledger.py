"""The goal ledger — persist a GoalPlan to goals/<id>.yaml, atomically, for resume + status.

The filesystem is the source of truth (human-readable, git-diffable). A crash or restart
resumes from the last checkpoint; the engine checkpoints after every step. Goals live in
``<ws>/goals/`` (gitignored — they're run state, not source).
"""
from __future__ import annotations

from pathlib import Path

from forsch.cli.goal_engine.schema import GoalPlan


def goals_dir(ws: Path) -> Path:
    return ws / "goals"


def goal_path(ws: Path, goal_id: str) -> Path:
    return goals_dir(ws) / f"{goal_id}.yaml"


def checkpoint(ws: Path, plan: GoalPlan) -> Path:
    """Atomically write the plan to goals/<id>.yaml. Call after every step."""
    from ruamel.yaml import YAML

    path = goal_path(ws, plan.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    tmp = path.with_suffix(".yaml.tmp")
    with tmp.open("w") as handle:
        yaml.dump(plan.model_dump(), handle)
    tmp.replace(path)
    return path


def load(ws: Path, goal_id: str) -> GoalPlan:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    data = yaml.load(goal_path(ws, goal_id).read_text())
    return GoalPlan.model_validate(data)


def list_goals(ws: Path) -> list[GoalPlan]:
    directory = goals_dir(ws)
    plans: list[GoalPlan] = []
    for path in sorted(directory.glob("*.yaml")) if directory.is_dir() else []:
        try:
            plans.append(load(ws, path.stem))
        except Exception:
            continue
    return plans
