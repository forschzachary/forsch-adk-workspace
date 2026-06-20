"""Read-only workspace collector (Phase 1).

Statically walks an ADK workspace and returns one ``Workspace`` model joining
the agent contract, runtime packages, web wrappers, bridge routes, shared tools,
and docs — surfacing drift and missing-metadata as warnings.

READ-ONLY: only reads files (no writes), and never imports runtime agent
modules (static YAML/AST inspection only), per Phase 1 rules.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from forsch.adk_builder.metadata import parse_python_metadata, parse_yaml_agent_metadata
from forsch.adk_builder.models import (
    AgentEntry,
    BridgeRoute,
    DocEntry,
    ToolEntry,
    Workspace,
)


def _safe_yaml(path: Path, warnings: list[str]) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        warnings.append(f"{path.name}: could not read/parse YAML: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def collect_workspace(root) -> Workspace:
    root = Path(root)
    ws = Workspace(root=str(root))

    contract_path = root / "agent_specs" / "agents.yaml"
    contract = _safe_yaml(contract_path, ws.warnings) if contract_path.exists() else {}
    contract_agents = contract.get("agents") or {}

    bridge_path = root / "bridge" / "bridge_config.yaml"
    bridge = _safe_yaml(bridge_path, ws.warnings) if bridge_path.exists() else {}
    bridge_agents = bridge.get("agents") or {}

    # Bridge routes + drift (a route with no agent contract).
    channels_by_agent: dict[str, list[str]] = {}
    for bid, bspec in bridge_agents.items():
        channels = list((bspec or {}).get("channels") or [])
        channels_by_agent[bid] = channels
        has_contract = bid in contract_agents
        ws.bridge_routes.append(
            BridgeRoute(agent_id=bid, channels=channels, has_contract=has_contract)
        )
        if not has_contract:
            ws.warnings.append(
                f"bridge route '{bid}' has no agent contract in agent_specs/agents.yaml (drift)"
            )

    # Agents from the contract.
    for aid, spec in contract_agents.items():
        spec = spec or {}
        parsed = parse_yaml_agent_metadata(spec, agent_id=aid, path="agent_specs/agents.yaml")
        ws.warnings.extend(parsed.warnings)

        web_entry = spec.get("web_entrypoint")
        web_wrapper_path = None
        if web_entry:
            if (root / web_entry).exists():
                web_wrapper_path = web_entry
            else:
                ws.warnings.append(f"agent '{aid}': web_entrypoint '{web_entry}' is missing")

        # Agent with no bridge route is mild drift worth noting.
        if aid not in channels_by_agent:
            ws.warnings.append(f"agent '{aid}' has an agent contract but no bridge route")

        ws.agents.append(
            AgentEntry(
                id=aid,
                contract_path="agent_specs/agents.yaml" if contract_path.exists() else None,
                runtime_package=spec.get("package"),
                web_wrapper_path=web_wrapper_path,
                bridge_channels=channels_by_agent.get(aid, []),
                tools=list(spec.get("tools") or []),
                metadata=parsed.metadata,
                warnings=list(parsed.warnings),
            )
        )

    # Shared component tools (static scan; no imports).
    components = root / "components"
    if components.exists():
        for py in sorted(components.rglob("*.py")):
            rel = str(py.relative_to(root))
            if py.name == "__init__.py" or py.name.startswith("test_") or "/tests/" in rel:
                continue
            try:
                source = py.read_text()
            except OSError as exc:
                ws.warnings.append(f"{rel}: could not read: {exc}")
                continue
            parsed = parse_python_metadata(source, path=rel)
            ws.warnings.extend(parsed.warnings)
            if not parsed.present and not parsed.warnings:
                ws.warnings.append(f"tool '{py.stem}' ({rel}): no display metadata")
            ws.tools.append(
                ToolEntry(
                    name=py.stem,
                    path=rel,
                    metadata=parsed.metadata,
                    warnings=list(parsed.warnings),
                )
            )

    # Docs (markdown discovery).
    docs_dir = root / "docs"
    if docs_dir.exists():
        for md in sorted(docs_dir.rglob("*.md")):
            rel = str(md.relative_to(root))
            title = None
            try:
                for line in md.read_text().splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
            except OSError:
                pass
            ws.docs.append(DocEntry(path=rel, title=title))

    return ws
