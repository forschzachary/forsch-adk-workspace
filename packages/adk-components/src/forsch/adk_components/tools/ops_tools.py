"""SRE/Ops tools for ADK agents."""

from __future__ import annotations

import subprocess
import os
import shutil
from pathlib import Path


def _workspace_root() -> Path | None:
    root = os.environ.get("FORSCH_ADK_WORKSPACE")
    return Path(root).expanduser().resolve() if root else None

def execute_bash_command(command: str) -> dict:
    """Execute an arbitrary shell command on the host and return the output.

    This runs via ``shell=True`` on purpose (pipes, globs, redirects are the point)
    and is intentionally unconfined, so it is only safe on a TRUSTED, local agent
    (stability). Output is capped at 8k/stream and the command is killed after 60s.
    Do NOT bind this tool to any agent exposed to untrusted input.
    """
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[:8000],
            "stderr": proc.stderr[:8000],
        }
    except Exception as exc:
        return {"command": command, "error": str(exc)}

def read_host_file(path: str) -> dict:
    """Read a configuration or log file from the host filesystem, with confinement.

    Reads are restricted to FORSCH_ADK_WORKSPACE (mirrors write_host_file) so a
    prompt-injected agent can't exfiltrate host secrets (~/.ssh, /etc/shadow,
    .env, cli.json). To read a host file outside the workspace, set
    FORSCH_ADK_ALLOW_HOST_READS=1.
    """
    try:
        target = Path(os.path.expanduser(path)).resolve()
        ws = _workspace_root()
        confined = os.environ.get("FORSCH_ADK_ALLOW_HOST_READS") != "1"
        if confined and ws is None:
            # Fail CLOSED: an unset workspace must NOT silently disable the seatbelt.
            return {
                "path": path,
                "error": (
                    "refused: FORSCH_ADK_WORKSPACE is not set, so the read cannot be "
                    "confined; set it, or set FORSCH_ADK_ALLOW_HOST_READS=1 to override"
                ),
            }
        if confined and not target.is_relative_to(ws):
            return {
                "path": path,
                "error": (
                    f"refused: {target} is outside the workspace ({ws}); "
                    "set FORSCH_ADK_ALLOW_HOST_READS=1 to override"
                ),
            }
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content[:15000], "truncated": len(content) > 15000}
    except Exception as exc:
        return {"path": path, "error": str(exc)}

def write_host_file(path: str, content: str) -> dict:
    """Write content to a file on the host filesystem, with seatbelts.

    1. Backup: any existing file is copied to ``<path>.bak`` before being
       overwritten, so a bad write is one ``mv`` away from recovery. The backup
       path is returned in the result.
    2. Confinement: writes are restricted to FORSCH_ADK_WORKSPACE. To edit a
       host config outside the workspace, set FORSCH_ADK_ALLOW_HOST_WRITES=1.
    """
    try:
        target = Path(os.path.expanduser(path)).resolve()
        ws = _workspace_root()
        confined = os.environ.get("FORSCH_ADK_ALLOW_HOST_WRITES") != "1"
        if confined and ws is None:
            # Fail CLOSED: an unset workspace must NOT silently disable the seatbelt
            # (that let writes land anywhere). Matches stability_tools' refuse-to-guess.
            return {
                "path": path,
                "success": False,
                "error": (
                    "refused: FORSCH_ADK_WORKSPACE is not set, so the write cannot be "
                    "confined; set it, or set FORSCH_ADK_ALLOW_HOST_WRITES=1 to override"
                ),
            }
        if confined and not target.is_relative_to(ws):
            return {
                "path": path,
                "success": False,
                "error": (
                    f"refused: {target} is outside the workspace ({ws}); "
                    "set FORSCH_ADK_ALLOW_HOST_WRITES=1 to override"
                ),
            }
        backup = None
        if target.exists():
            backup = str(target) + ".bak"
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "success": True, "backup": backup}
    except Exception as exc:
        return {"path": path, "success": False, "error": str(exc)}
