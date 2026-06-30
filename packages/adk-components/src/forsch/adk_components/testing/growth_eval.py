"""Deterministic rubric runner for growth-team evalsets."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


TOOL_MODULE = "forsch.adk_components.tools"


def _get_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def _assertion_passed(result: dict[str, Any], assertion: dict[str, Any]) -> tuple[bool, str]:
    path = assertion.get("path", "")
    value = _get_path(result, path)
    if "equals" in assertion:
        expected = assertion["equals"]
        return value == expected, f"{path} == {expected!r} (got {value!r})"
    if "min" in assertion:
        expected = assertion["min"]
        try:
            return float(value) >= float(expected), f"{path} >= {expected!r} (got {value!r})"
        except (TypeError, ValueError):
            return False, f"{path} >= {expected!r} (got non-numeric {value!r})"
    if "max" in assertion:
        expected = assertion["max"]
        try:
            return float(value) <= float(expected), f"{path} <= {expected!r} (got {value!r})"
        except (TypeError, ValueError):
            return False, f"{path} <= {expected!r} (got non-numeric {value!r})"
    if "contains" in assertion:
        expected = assertion["contains"]
        if isinstance(value, list):
            haystack = "\n".join(str(v) for v in value)
        else:
            haystack = str(value or "")
        return expected in haystack, f"{path} contains {expected!r}"
    return False, f"unknown assertion for {path!r}"


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    call = case.get("tool_call") or {}
    name = call.get("name")
    args = call.get("args") or {}
    if not name:
        return {
            "eval_case_id": case.get("eval_case_id"),
            "passed": False,
            "error": "missing tool_call.name",
        }
    tools = importlib.import_module(TOOL_MODULE)
    func = getattr(tools, name, None)
    if func is None:
        return {
            "eval_case_id": case.get("eval_case_id"),
            "passed": False,
            "error": f"unknown tool {name}",
        }

    try:
        result = func(**args)
    except Exception as exc:  # noqa: BLE001 - eval runner must report failed case, not crash
        return {
            "eval_case_id": case.get("eval_case_id"),
            "passed": False,
            "tool": name,
            "error": str(exc),
        }

    assertion_results = []
    passed = True
    for assertion in case.get("assertions", []):
        ok, message = _assertion_passed(result, assertion)
        assertion_results.append({"passed": ok, "message": message})
        passed = passed and ok

    return {
        "eval_case_id": case.get("eval_case_id"),
        "passed": passed,
        "tool": name,
        "assertions": assertion_results,
        "result_preview": result,
    }


def _run_evalset(path: Path) -> dict[str, Any]:
    started = time.time()
    data = json.loads(path.read_text())
    cases = data.get("eval_cases") or data.get("cases") or []
    case_results = [_run_case(case) for case in cases]
    passed_cases = sum(1 for case in case_results if case.get("passed"))
    total_cases = len(case_results)
    score = (passed_cases / total_cases) if total_cases else 0.0
    ok = total_cases > 0 and passed_cases == total_cases
    return {
        "ok": ok,
        "agent_id": data.get("agent_id") or path.parent.name,
        "evalset_id": path.stem.replace(".evalset", ""),
        "trajectory_pass": ok,
        "final_response_pass": ok,
        "score": round(score, 3),
        "passed_cases": passed_cases,
        "total_cases": total_cases,
        "cases": case_results,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "source": str(path),
    }


def run_evalset(path: Path) -> dict[str, Any]:
    """Run an evalset with isolated local-write storage unless the caller set one."""
    if os.environ.get("FORSCH_PATTERNS_DATA_DIR"):
        return _run_evalset(path)

    with tempfile.TemporaryDirectory(prefix="growth-eval-") as data_dir:
        os.environ["FORSCH_PATTERNS_DATA_DIR"] = data_dir
        try:
            return _run_evalset(path)
        finally:
            os.environ.pop("FORSCH_PATTERNS_DATA_DIR", None)


def find_evalset(root: Path, agent_id: str, evalset_id: str | None) -> Path:
    agent_root = root / agent_id
    if evalset_id:
        candidate = agent_root / f"{evalset_id}.evalset.json"
        if candidate.exists():
            return candidate
    matches = sorted(agent_root.glob("*.evalset.json"))
    if not matches:
        raise FileNotFoundError(f"no evalsets found for {agent_id} under {agent_root}")
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic growth-team evalsets")
    parser.add_argument("--evalsets-root", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--evalset")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    path = find_evalset(Path(args.evalsets_root), args.agent, args.evalset)
    result = run_evalset(path)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "PASS" if result["ok"] else "FAIL"
        print(
            f"{status} {result['agent_id']}::{result['evalset_id']} "
            f"{result['passed_cases']}/{result['total_cases']} score={result['score']}"
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
