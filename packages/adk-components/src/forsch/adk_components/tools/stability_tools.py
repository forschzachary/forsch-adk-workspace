"""Read-only stability inspection tools for ADK agents."""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

_IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
# Workspace root comes ONLY from FORSCH_ADK_WORKSPACE (set by compose / the
# cockpit unit). No hardcoded default — a stale path is a silent landmine.
_DEFAULT_SERVICE_ENDPOINTS = {
    "authsome": "http://127.0.0.1:7998/health",
    "litellm": "http://127.0.0.1:4000/health/readiness",
}
_DEFAULT_AGENTS = {
    "stability": {"module": "forsch.agent_stability.agent", "attr": "root_agent"},
    "ops": {"module": "forsch.agent_ops.agent", "attr": "root_agent"},
    "assistant": {"module": "forsch.agent_assistant.agent", "attr": "agent"},
    "brand": {"module": "forsch.agent_brand.agent", "attr": "agent"},
    "build": {"module": "forsch.agent_build.agent", "attr": "agent"},
    "social": {"module": "forsch.agent_social.agent", "attr": "agent"},
}
_DEFAULT_GIT_PATHS = [
    "components",
    "agents/stability",
    "agents/assistant",
    "agents/brand",
    "agents/build",
    "agents/ops",
    "agents/social",
    "bridge",
]


def get_workspace_inventory(root: str | None = None, max_depth: int = 3) -> dict[str, Any]:
    """Return a compact read-only inventory of the configured ADK workspace."""
    workspace_root = _workspace_root(root)
    root_path = _resolve_workspace_path(root or str(workspace_root), workspace_root)
    if root_path is None:
        return {"root": root, "exists": False, "directories": [], "files": [], "error": "path outside workspace"}
    if not root_path.exists():
        return {"root": str(root_path), "exists": False, "directories": [], "files": []}

    directories: list[str] = []
    files: list[str] = []
    for current, dirnames, filenames in os.walk(root_path):
        current_path = Path(current)
        rel_current = current_path.relative_to(root_path)
        dirnames[:] = [name for name in sorted(dirnames) if name not in _IGNORED_DIRS]
        depth = 0 if rel_current == Path(".") else len(rel_current.parts)
        if depth >= max_depth:
            dirnames[:] = []
        for dirname in dirnames:
            rel = current_path.joinpath(dirname).relative_to(root_path)
            directories.append(rel.as_posix())
        if depth < max_depth:
            for filename in sorted(filenames):
                rel = current_path.joinpath(filename).relative_to(root_path)
                files.append(rel.as_posix())

    return {"root": str(root_path), "exists": True, "directories": directories, "files": files}


def get_git_state(paths: list[str] | None = None) -> list[dict[str, Any]]:
    """Return branch and porcelain status for known workspace repository paths."""
    workspace_root = _workspace_root(required=paths is None)
    if paths is None:
        requested_paths = [str(workspace_root / rel_path) for rel_path in _DEFAULT_GIT_PATHS]
    else:
        requested_paths = paths
    states: list[dict[str, Any]] = []
    for requested_path in requested_paths:
        if workspace_root is not None:
            path = _resolve_workspace_path(requested_path, workspace_root)
            if path is None:
                states.append({"path": requested_path, "is_repo": False, "branch": None, "status": [], "error": "path outside workspace"})
                continue
        else:
            path = Path(requested_path).expanduser().resolve()
        states.append(_git_state_for_path(path))
    return states


def validate_agent_imports(agents: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """Import configured agents and report whether the expected attribute exists."""
    specs = agents or [
        {"name": name, "module": config["module"], "attr": config["attr"]}
        for name, config in _DEFAULT_AGENTS.items()
    ]
    results: list[dict[str, Any]] = []
    for spec in specs:
        name = spec.get("name", spec.get("module", "unknown"))
        allowed = _DEFAULT_AGENTS.get(name)
        module_name = spec.get("module")
        attr = spec.get("attr", "root_agent")
        if allowed is None or module_name is None or module_name != allowed["module"] or attr != allowed["attr"]:
            results.append({"name": name, "module": module_name, "attr": attr, "ok": False, "error": "agent import not allowed"})
            continue
        try:
            module = importlib.import_module(module_name)
            agent = getattr(module, attr)
            results.append(
                {
                    "name": name,
                    "module": module_name,
                    "attr": attr,
                    "ok": True,
                    "agent_name": getattr(agent, "name", None),
                }
            )
        except Exception as exc:  # noqa: BLE001 - stability reports should not crash the caller.
            results.append({"name": name, "module": module_name, "attr": attr, "ok": False, "error": str(exc)})
    return results


def check_service_health(endpoints: dict[str, str] | None = None, timeout: float = 2.0) -> list[dict[str, Any]]:
    """Check approved HTTP health endpoints without mutating services."""
    requested = endpoints if endpoints is not None else _DEFAULT_SERVICE_ENDPOINTS
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout) as client:
        for name, url in requested.items():
            if _DEFAULT_SERVICE_ENDPOINTS.get(name) != url:
                results.append({"name": name, "url": url, "ok": False, "error": "service endpoint not allowed"})
                continue
            try:
                response = client.get(url)
                results.append(
                    {
                        "name": name,
                        "url": url,
                        "ok": 200 <= response.status_code < 400,
                        "status_code": response.status_code,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - health probes should return structured failures.
                results.append({"name": name, "url": url, "ok": False, "error": str(exc)})
    return results


def _workspace_root(fallback: str | None = None, *, required: bool = True) -> Path | None:
    root = os.environ.get("FORSCH_ADK_WORKSPACE")
    if root:
        return Path(root).expanduser().resolve()
    if fallback:
        return Path(fallback).expanduser().resolve()
    if required:
        raise RuntimeError(
            "FORSCH_ADK_WORKSPACE is not set; refusing to guess the workspace root"
        )
    return None


def _resolve_workspace_path(path: str, workspace_root: Path) -> Path | None:
    resolved = Path(path).expanduser().resolve()
    if resolved == workspace_root or workspace_root in resolved.parents:
        return resolved
    return None


def _git_state_for_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "is_repo": False, "branch": None, "status": []}

    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        return {"path": str(path), "is_repo": False, "branch": None, "status": []}

    proc = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=path,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    lines = [line for line in proc.stdout.splitlines() if line]
    branch = lines[0].removeprefix("## ") if lines else None
    return {
        "path": str(path),
        "is_repo": True,
        "branch": branch,
        "status": lines[1:],
        "ok": proc.returncode == 0,
    }
