"""forsch eval — run an agent's eval set locally, graded by an LLM judge on your gateway.

Wraps ADK's local eval (AgentEvaluator -> LocalEvalService, no Vertex). The agent runs
through its own gateway model; the built-in final_response_match_v2 judge resolves
``openai/<model>`` to a LiteLlm that reads OPENAI_API_BASE / OPENAI_API_KEY — which we
point at the Forsch gateway. The manifest stays the source of truth; eval sets live in
``eval_sets/<agent>.evalset.json``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

JUDGE_MODEL = "openai/gpt-5.5"


def eval_set_path(ws: Path, agent_id: str) -> Path:
    return ws / "eval_sets" / f"{agent_id}.evalset.json"


def scaffold_eval_set(path: Path, agent_id: str) -> None:
    """Write a starter EvalSet JSON (one example case) for the agent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    starter = {
        "eval_set_id": f"{agent_id}-evals",
        "name": f"{agent_id} evals",
        "eval_cases": [
            {
                "eval_id": "example-1",
                "conversation": [
                    {
                        "invocation_id": "inv-1",
                        "user_content": {
                            "role": "user",
                            "parts": [{"text": "Introduce yourself in one sentence."}],
                        },
                        "final_response": {
                            "role": "model",
                            "parts": [{"text": "<the kind of answer you want — the judge grades the agent against this>"}],
                        },
                    }
                ],
            }
        ],
    }
    path.write_text(json.dumps(starter, indent=2) + "\n")


def _gateway_env(ws: Path) -> None:
    """Load .adk-local.env and point both the agent and the LLM-judge at the gateway."""
    from forsch.cli.operator import _load_env

    _load_env(ws / ".adk-local.env")
    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY") or ""
    if not base:
        raise SystemExit("no gateway configured — add LITELLM_BASE_URL + a key to .adk-local.env to eval.")
    # the judge resolves "openai/<model>" -> LiteLlm, which reads these:
    os.environ.setdefault("OPENAI_API_BASE", base)
    os.environ.setdefault("OPENAI_API_KEY", key)


def _build_config(threshold: float, judge_model: str):
    from google.adk.evaluation.eval_config import EvalConfig
    from google.adk.evaluation.eval_metrics import JudgeModelOptions, LlmAsAJudgeCriterion

    return EvalConfig(
        criteria={
            "final_response_match_v2": LlmAsAJudgeCriterion(
                threshold=threshold,
                judge_model_options=JudgeModelOptions(judge_model=judge_model, num_samples=1),
            )
        }
    )


def run_eval(ws: Path, agent_id: str, set_file: Path, threshold: float = 0.7,
             judge_model: str = JUDGE_MODEL) -> bool:
    """Run the eval set against the agent with a gateway-backed LLM judge. Returns pass/fail."""
    import asyncio
    import logging
    import warnings

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)  # we render results ourselves; mute ADK's logging noise
    _gateway_env(ws)

    from google.adk.evaluation.agent_evaluator import AgentEvaluator
    from google.adk.evaluation.eval_config import get_eval_metrics_from_config
    from google.adk.evaluation.eval_set import EvalSet
    from google.adk.evaluation.simulation.user_simulator_provider import UserSimulatorProvider

    eval_set = EvalSet.model_validate_json(set_file.read_text())
    config = _build_config(threshold, judge_model)
    module = f"forsch.agent_{agent_id.replace('-', '_')}.agent"

    async def _detailed():
        agent = await AgentEvaluator._get_agent_for_eval(module_name=module, agent_name=None)
        metrics = get_eval_metrics_from_config(config)
        usp = UserSimulatorProvider(user_simulator_config=config.user_simulator_config)
        return await AgentEvaluator._get_eval_results_by_eval_id(
            agent_for_eval=agent, eval_set=eval_set, eval_metrics=metrics,
            num_runs=1, user_simulator_provider=usp,
        )

    try:
        results = asyncio.run(_detailed())
    except (AttributeError, TypeError) as exc:  # ADK internal-API drift -> high-level path
        return _run_fallback(module, eval_set, config, exc)

    rows = [
        (eval_id, mr.metric_name, mr.score, mr.threshold, mr.eval_status)
        for eval_id, case_results in results.items()
        for cr in case_results
        for per_inv in cr.eval_metric_result_per_invocation
        for mr in per_inv.eval_metric_results
    ]
    return _render(agent_id, rows)


def _render(agent_id: str, rows: list) -> bool:
    from google.adk.evaluation.eval_metrics import EvalStatus
    from rich.table import Table

    from forsch.cli.ui import ACCENT, COSMIC, console

    console.print()
    console.print(f"  [{COSMIC}]✦[/] [bold]eval[/] [dim]·[/] [bold #b8a0ff]{agent_id}[/]")
    console.print()
    table = Table(show_header=True, header_style=f"bold {ACCENT}", box=None, pad_edge=False)
    table.add_column("case")
    table.add_column("metric", style="dim")
    table.add_column("score", justify="right")
    table.add_column("threshold", justify="right", style="dim")
    table.add_column("")
    passed = 0
    for eval_id, metric, score, thr, status in rows:
        ok = status == EvalStatus.PASSED
        passed += ok
        sval = f"{score:.2f}" if score is not None else "—"
        tval = f"{thr:.2f}" if thr is not None else "—"
        table.add_row(
            eval_id, metric,
            f"[{'green' if ok else 'red'}]{sval}[/]", tval,
            "[green]✓[/]" if ok else "[red]✗[/]",
        )
    console.print(table)
    console.print()
    total = len(rows)
    allok = total > 0 and passed == total
    style = "green" if allok else "red"
    console.print(f"  [{style}]{'✓' if allok else '✗'}[/] [bold]{passed}/{total}[/] checks passed")
    console.print()
    return allok


def _run_fallback(module: str, eval_set, config, exc: Exception) -> bool:
    import asyncio

    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    from forsch.cli.ui import console

    console.print(f"  [dim](detailed scores unavailable: {type(exc).__name__}; falling back)[/]")
    try:
        asyncio.run(AgentEvaluator.evaluate_eval_set(
            agent_module=module, eval_set=eval_set, eval_config=config,
            num_runs=1, print_detailed_results=True,
        ))
        console.print("  [green]✓[/] eval passed")
        return True
    except AssertionError as err:
        console.print(f"  [red]✗[/] eval failed\n{err}")
        return False
