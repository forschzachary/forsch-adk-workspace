"""Read-only reconcile between the manifest and the Discord bridge routes.

Surfaces drift WITHOUT mutating ``bridge_config.yaml`` (which carries comments
and non-route sections that a ``safe_dump`` rewrite would destroy). A future
careful task can apply changes with round-trip YAML; for now this is the
analysis the review gate / cockpit shows.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from forsch.adk_factory.loader import load_manifest


def analyze_bridge(manifest_path, bridge_config_path) -> dict:
    """Compare manifest agents against bridge routes.

    Returns a report with four lists:
      - ``in_sync``: agent is routed and its channels match the manifest
      - ``channel_mismatch``: agent is routed but channels differ
      - ``missing_route``: agent in manifest has no bridge route
      - ``drift``: bridge route has no manifest contract (the classic drift)
    """
    manifest = load_manifest(manifest_path)
    cfg = yaml.safe_load(Path(bridge_config_path).read_text()) or {}
    routes = cfg.get("agents") or {}

    report = {
        "in_sync": [],
        "channel_mismatch": [],
        "missing_route": [],
        "drift": [],
    }

    for aid, spec in manifest.agents.items():
        route = routes.get(aid)
        if not isinstance(route, dict):
            report["missing_route"].append(aid)
            continue
        if list(route.get("channels") or []) == list(spec.discord_channels):
            report["in_sync"].append(aid)
        else:
            report["channel_mismatch"].append(aid)

    for rid, rspec in routes.items():
        if not isinstance(rspec, dict):
            continue  # scalar entry such as `dm_fallback: assistant`
        if rid not in manifest.agents:
            report["drift"].append(rid)

    return report
