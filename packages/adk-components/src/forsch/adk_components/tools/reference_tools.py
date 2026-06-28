"""Read-only reference-library tools for ADK agents.

Search and read the local documentation wikis under ``docs/reference/`` (ADK,
MCP, LiteLLM, Gradio, uv, MiMo) — produced by ``scripts/refresh_reference.sh``.
Lets an agent consult framework docs at runtime, offline, with bounded output.

The library location is resolved from the workspace root (``FORSCH_ADK_WORKSPACE``)
via :func:`forsch.adk_components.workspace_resolver.workspace_root` — never a
hardcoded path.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from ..patterns.tool_decorator import tool
from ..workspace_resolver import workspace_root

_SOURCES = ("adk", "mcp", "litellm", "gradio", "uv", "mimo")
_MAX_HITS = 25
_MAX_SNIPPET = 400          # chars per snippet
_MAX_TOTAL_BYTES = 24_000   # cap on total search payload
_MAX_READ_BYTES = 40_000    # cap on read_reference body
_PER_FILE_CAP = 5           # max hits per file


def _reference_dir() -> Path:
    """Locate docs/reference/ at the ADK repo root.

    The repo root is ``FORSCH_ADK_WORKSPACE`` (compose: /workspace; cockpit unit:
    /root/.hermes/workspace/adk) — the same contract stability_tools uses. The
    older ``workspace_root()`` resolver returns the workspace *parent*, so the
    repo is ``<parent>/adk``; we use that only as a fallback.
    """
    root = os.environ.get("FORSCH_ADK_WORKSPACE")
    if root:
        return Path(root) / "docs" / "reference"
    return workspace_root() / "adk" / "docs" / "reference"


def _safe_path(rel: str) -> Path | None:
    """Resolve ``rel`` under docs/reference/, rejecting traversal/absolute paths."""
    base = _reference_dir().resolve()
    rel = (rel or "").strip().lstrip("/")
    for prefix in ("docs/reference/", "reference/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    if not rel:
        return None
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _heading_level(line: str) -> int:
    s = line.lstrip()
    return len(s) - len(s.lstrip("#"))


def _nearest_heading(lines: list[str], idx: int) -> str:
    for i in range(min(idx, len(lines) - 1), -1, -1):
        if lines[i].lstrip().startswith("#"):
            return lines[i].strip().lstrip("#").strip()
    return ""


@tool(
    family="reference",
    safety="read_only",
    keywords=["reference", "docs", "documentation", "search", "adk", "gradio",
              "litellm", "mcp", "uv", "mimo", "wiki", "how-to"],
)
def search_reference(query: str, source: str | None = None) -> dict:
    """Search the local reference wikis (docs/reference/) for ``query``.

    Args:
        query: case-insensitive text to find (literal substring, not regex).
        source: optional — restrict to one of adk|mcp|litellm|gradio|uv|mimo.

    Returns:
        ``{query, source, hits, count, truncated, note}`` where each hit is
        ``{source, file, line, heading, snippet}``. Output is bounded in both
        hit count and total bytes so a query cannot flood the agent's context.
    """
    query = (query or "").strip()
    if not query:
        return {"query": query, "source": source, "hits": [], "count": 0,
                "truncated": False, "error": "empty query"}
    base = _reference_dir()
    if not base.exists():
        return {"query": query, "source": source, "hits": [], "count": 0,
                "truncated": False,
                "error": "reference library not found; run scripts/refresh_reference.sh"}
    search_root = base
    if source:
        if source not in _SOURCES:
            return {"query": query, "source": source, "hits": [], "count": 0,
                    "truncated": False,
                    "error": f"unknown source '{source}'; valid: {', '.join(_SOURCES)}"}
        search_root = base / source

    matches = _rg_search(query, search_root)
    if matches is None:
        matches = _py_search(query, search_root)

    hits: list[dict] = []
    total = 0
    for m in matches:
        if len(hits) >= _MAX_HITS or total >= _MAX_TOTAL_BYTES:
            break
        rel = m["file"].relative_to(base)
        snippet = m["snippet"][:_MAX_SNIPPET]
        hits.append({
            "source": rel.parts[0] if rel.parts else "",
            "file": str(rel),
            "line": m["line"],
            "heading": m["heading"],
            "snippet": snippet,
        })
        total += len(snippet) + len(str(rel))
    truncated = len(matches) > len(hits)
    return {"query": query, "source": source, "hits": hits, "count": len(hits),
            "truncated": truncated,
            "note": "more hits — narrow the query or pass source=" if truncated else ""}


@tool(
    family="reference",
    safety="read_only",
    keywords=["reference", "read", "docs", "documentation", "page", "section"],
)
def read_reference(path: str, section: str | None = None) -> dict:
    """Read a reference file under docs/reference/.

    Args:
        path: path relative to docs/reference/ (e.g. ``adk/adk-llms-full.md``).
              A leading ``docs/reference/`` is tolerated. Traversal is rejected.
        section: optional markdown heading; returns only that section's body.

    Returns:
        ``{path, section, content, truncated}`` with content bounded in size.
    """
    p = _safe_path(path)
    if p is None:
        return {"path": path, "section": section, "content": "",
                "error": "path outside docs/reference/"}
    if not p.is_file():
        return {"path": path, "section": section, "content": "", "error": "not found"}
    text = p.read_text(errors="replace")
    if section:
        extracted = _extract_section(text, section)
        if extracted is None:
            return {"path": path, "section": section, "content": "",
                    "error": f"section '{section}' not found"}
        text = extracted
    truncated = len(text) > _MAX_READ_BYTES
    return {"path": path, "section": section, "content": text[:_MAX_READ_BYTES],
            "truncated": truncated}


def _rg_search(query: str, root: Path) -> list[dict] | None:
    """ripgrep-backed literal search. Returns None if rg is unavailable."""
    try:
        out = subprocess.run(
            ["rg", "--no-config", "-F", "-i", "-n", "--max-count", str(_PER_FILE_CAP),
             "-e", query, str(root)],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if out.returncode not in (0, 1):  # 1 = no matches (not an error)
        return None
    results: list[dict] = []
    cache: dict[Path, list[str]] = {}
    for line in out.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        fp, lineno, content = parts
        p = Path(fp)
        if not p.is_file() or not lineno.isdigit():
            continue
        if p not in cache:
            cache[p] = p.read_text(errors="replace").splitlines()
        li = int(lineno) - 1
        results.append({"file": p, "line": int(lineno),
                        "heading": _nearest_heading(cache[p], li),
                        "snippet": content.strip()})
    return results


def _py_search(query: str, root: Path) -> list[dict]:
    """Pure-Python fallback literal search."""
    pat = re.compile(re.escape(query), re.IGNORECASE)
    results: list[dict] = []
    for p in sorted(root.rglob("*.md")):
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError:
            continue
        per_file = 0
        for i, line in enumerate(lines):
            if pat.search(line):
                results.append({"file": p, "line": i + 1,
                                "heading": _nearest_heading(lines, i),
                                "snippet": line.strip()})
                per_file += 1
                if per_file >= _PER_FILE_CAP:
                    break
    return results


def _extract_section(text: str, section: str) -> str | None:
    lines = text.splitlines()
    target = section.strip().lower()
    start = None
    level = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            if line.strip().lstrip("#").strip().lower() == target:
                start = i
                level = _heading_level(line)
                break
    if start is None:
        return None
    out = [lines[start]]
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith("#") and _heading_level(lines[j]) <= level:
            break
        out.append(lines[j])
    return "\n".join(out)
