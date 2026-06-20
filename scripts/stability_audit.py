"""Run a read-only stability audit for the ADK workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from forsch.adk_components.tools.stability_tools import (
    check_service_health,
    get_git_state,
    get_workspace_inventory,
    validate_agent_imports,
)

_DEFAULT_AGENTS = [
    {"name": "stability", "module": "forsch.agent_stability.agent", "attr": "root_agent"},
    {"name": "ops", "module": "forsch.agent_ops.agent", "attr": "root_agent"},
    {"name": "assistant", "module": "forsch.agent_assistant.agent", "attr": "agent"},
    {"name": "brand", "module": "forsch.agent_brand.agent", "attr": "agent"},
    {"name": "build", "module": "forsch.agent_build.agent", "attr": "agent"},
    {"name": "social", "module": "forsch.agent_social.agent", "attr": "agent"},
]
_DEFAULT_WORKSPACE = Path("/opt/data/workspace/adk").resolve()


def get_agent_source_paths(root: Path) -> list[Path]:
    """Return local agent source paths needed for workspace import validation."""
    return [root / "agents" / agent["name"] / "src" for agent in _DEFAULT_AGENTS]


def add_agent_source_paths(root: Path) -> None:
    """Make sibling agent packages importable for local workspace audits."""
    for source_path in reversed(get_agent_source_paths(root)):
        if source_path.exists():
            sys.path.insert(0, str(source_path))


def build_report(workspace: str, include_services: bool = True) -> dict[str, Any]:
    """Build a structured read-only audit report."""
    root = Path(workspace).expanduser().resolve()
    if root != _DEFAULT_WORKSPACE:
        workspace_report = get_workspace_inventory(str(root), max_depth=2)
        git_report = get_git_state([])
        agent_report = [
            {
                "name": agent["name"],
                "module": agent["module"],
                "attr": agent["attr"],
                "ok": False,
                "error": "workspace path not allowed",
            }
            for agent in _DEFAULT_AGENTS
        ]
        service_report = check_service_health(timeout=0.5) if include_services else []
        return {
            "workspace": workspace_report,
            "git": git_report,
            "agents": agent_report,
            "services": service_report,
            "summary": _summarize(workspace_report, git_report, agent_report, service_report),
        }

    add_agent_source_paths(root)
    git_paths = [
        root / "components",
        root / "agents" / "stability",
        root / "agents" / "ops",
        root / "agents" / "assistant",
        root / "agents" / "brand",
        root / "agents" / "build",
        root / "agents" / "social",
        root / "bridge",
    ]
    workspace_report = get_workspace_inventory(str(root), max_depth=2)
    git_report = get_git_state([str(path) for path in git_paths])
    if workspace_report.get("exists"):
        agent_report = validate_agent_imports(_DEFAULT_AGENTS)
    else:
        agent_report = [
            {
                "name": agent["name"],
                "module": agent["module"],
                "attr": agent["attr"],
                "ok": False,
                "error": "workspace does not exist",
            }
            for agent in _DEFAULT_AGENTS
        ]
    service_report = check_service_health(timeout=0.5) if include_services else []

    return {
        "workspace": workspace_report,
        "git": git_report,
        "agents": agent_report,
        "services": service_report,
        "summary": _summarize(workspace_report, git_report, agent_report, service_report),
    }


def _summarize(
    workspace: dict[str, Any],
    git: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> dict[str, Any]:
    dirty_repos = [repo["path"] for repo in git if repo.get("status")]
    failed_agents = [agent["name"] for agent in agents if not agent.get("ok")]
    failed_services = [service["name"] for service in services if not service.get("ok")]
    return {
        "workspace_exists": workspace.get("exists", False),
        "dirty_repo_count": len(dirty_repos),
        "dirty_repos": dirty_repos,
        "failed_agent_imports": failed_agents,
        "failed_services": failed_services,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a read-only ADK stability audit.")
    parser.add_argument("--workspace", default="/opt/data/workspace/adk")
    parser.add_argument("--skip-services", action="store_true")
    args = parser.parse_args()

    report = build_report(args.workspace, include_services=not args.skip_services)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
