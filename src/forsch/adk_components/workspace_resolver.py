"""Single source of truth for the workspace root.

Import this everywhere instead of hardcoding /opt/data/workspace.
Override with FORSCH_WORKSPACE; else derive from HERMES_HOME.
"""

import os
from pathlib import Path


def workspace_root() -> Path:
    """Return the canonical workspace root.

    FORSCH_WORKSPACE override wins if set.
    Otherwise derives from HERMES_HOME (the durable per-instance home).
    """
    override = os.environ.get("FORSCH_WORKSPACE")
    if override:
        return Path(override)
    return Path(os.environ.get("HERMES_HOME", "/opt/data")) / "workspace"
