"""Mirror built agents into the live-agent-graph registry, so the map updates as you build.

The graph (packages/live-agent-graph) renders from its own registry —
``packages/live-agent-graph/registry/agents/agents.yaml`` — a SUBSET of the manifest
(description, discord_channels, safety_level, purpose, tools as BARE names, model, role,
group). The factory's source of truth is agent_specs/agents.yaml. This keeps the two in
sync on every ``forsch build``, with a graceful skip when the graph package isn't present.
"""
from __future__ import annotations

from pathlib import Path

_GRAPH_REGISTRY = ("packages", "live-agent-graph", "registry", "agents", "agents.yaml")
_SUBSET = ("description", "discord_channels", "safety_level", "purpose", "tools", "model", "role", "group")


def graph_registry_path(ws: Path) -> Path:
    return ws.joinpath(*_GRAPH_REGISTRY)


def _bare(tool: str) -> str:
    """The graph registry lists bare tool names; the manifest uses fully-qualified paths."""
    return tool.rsplit(".", 1)[-1]


def sync_agent_to_graph_registry(ws: Path, agent_id: str, spec: dict) -> bool:
    """Mirror one agent's graph-subset into the live-agent-graph registry.

    Returns True if synced, False (a graceful no-op) when the graph package/registry
    isn't present in this workspace. Atomic write; preserves the registry's other entries
    and its ``version`` key.
    """
    path = graph_registry_path(ws)
    if not path.exists():
        return False

    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(path.read_text()) or {}
    data.setdefault("version", 1)
    agents = data.setdefault("agents", {})

    entry: dict = {}
    for key in _SUBSET:
        val = spec.get(key)
        if val in (None, "", [], {}):
            continue
        entry[key] = [_bare(t) for t in val] if key == "tools" else val
    agents[agent_id] = entry

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        yaml.dump(data, f)
    tmp.replace(path)
    return True


def describe_graph(ws: Path, agent_id: str | None = None) -> dict:
    """Read-only structured wiring of the fleet, from the manifest (the source of truth).

    Per agent: model, bare tool names, discord_channels, web_entrypoint, safety_level, group,
    and whether it's mirrored into the live-graph registry. Scope to one with ``agent_id``.
    This is the current-state read the operator diffs against a target state.
    """
    from forsch.adk_factory.loader import load_manifest

    manifest = load_manifest(ws / "agent_specs" / "agents.yaml")
    ids = [agent_id] if agent_id else list(manifest.agents)

    in_registry: set = set()
    reg = graph_registry_path(ws)
    if reg.exists():
        from ruamel.yaml import YAML

        data = YAML(typ="safe").load(reg.read_text()) or {}
        in_registry = set((data.get("agents") or {}).keys())

    out: dict = {}
    for aid in ids:
        if aid not in manifest.agents:
            out[aid] = {"error": "no such agent"}
            continue
        spec = manifest.agents[aid].model_dump()
        out[aid] = {
            "model": spec.get("model") or "",
            "tools": [_bare(t) for t in spec.get("tools", [])],
            "discord_channels": spec.get("discord_channels", []),
            "web_entrypoint": spec.get("web_entrypoint") or "",
            "safety_level": spec.get("safety_level") or "",
            "group": spec.get("group") or "",
            "in_graph_registry": aid in in_registry,
        }
    return out


def serve_graph(ws: Path, port: int = 8080) -> str:
    """Start the local live-graph server in the background (idempotent) and return its URL."""
    import socket
    import subprocess

    serve = ws / "packages" / "live-agent-graph" / "serve.py"
    if not serve.exists():
        raise FileNotFoundError("live-agent-graph is not in this workspace")
    url = f"http://127.0.0.1:{port}"
    with socket.socket() as probe:
        probe.settimeout(0.3)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return url  # already serving — don't spawn a duplicate
    subprocess.Popen(
        ["python3", str(serve), str(port)], cwd=str(serve.parent),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return url
