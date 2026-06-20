"""Metadata parser (Phase 1, read-only).

Two sources, one model:
  * ``parse_python_metadata`` — YAML frontmatter inside a Python module
    docstring (uses ``ast.get_docstring``, not regex alone).
  * ``parse_yaml_agent_metadata`` — human fields from an ``agents.yaml`` entry.

Both warn-not-crash on malformed input and tolerate missing metadata.
"""

from __future__ import annotations

import ast
from typing import Any, Optional

import yaml

from forsch.adk_builder.models import Metadata, ParsedMetadata

# Frontmatter keys mapped onto the Metadata model; unknown keys are ignored.
_FRONTMATTER_KEYS = {"display_name", "description", "doc_link", "owner", "risk", "kind"}


def _frontmatter_block(docstring: str) -> Optional[str]:
    """Return the YAML text between the first two ``---`` fences, or None."""
    lines = docstring.splitlines()
    fences = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(fences) < 2:
        return None
    return "\n".join(lines[fences[0] + 1 : fences[1]])


def parse_python_metadata(source: str, *, path: Optional[str] = None) -> ParsedMetadata:
    """Parse YAML frontmatter from a Python module docstring."""
    result = ParsedMetadata(path=path)
    where = path or "<source>"
    try:
        docstring = ast.get_docstring(ast.parse(source))
    except SyntaxError as exc:
        result.warnings.append(f"{where}: could not parse Python source: {exc}")
        return result
    if not docstring:
        return result  # no docstring -> no metadata (tolerated, present=False)
    block = _frontmatter_block(docstring)
    if block is None:
        return result  # docstring but no frontmatter (tolerated)
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        result.warnings.append(f"{where}: malformed metadata frontmatter: {exc}")
        return result
    if not isinstance(data, dict):
        result.warnings.append(f"{where}: metadata frontmatter is not a mapping")
        return result
    result.present = True
    result.metadata = Metadata(**{k: v for k, v in data.items() if k in _FRONTMATTER_KEYS})
    return result


def parse_yaml_agent_metadata(
    spec: Any, *, agent_id: str, path: Optional[str] = None
) -> ParsedMetadata:
    """Parse human-friendly fields from one ``agents.yaml`` entry.

    Maps the real manifest shape too: ``purpose`` -> description fallback,
    ``safety_level`` -> risk. Warns (never raises) on missing display fields.
    """
    result = ParsedMetadata(path=path)
    where = path or "agent spec"
    if not isinstance(spec, dict):
        result.warnings.append(f"agent '{agent_id}': spec is not a mapping in {where}")
        return result

    display_name = spec.get("display_name")
    description = spec.get("description") or spec.get("purpose")
    if isinstance(description, str):
        description = description.strip()
    doc_link = spec.get("doc_link")
    risk = spec.get("risk") or spec.get("safety_level")

    result.metadata = Metadata(
        display_name=display_name,
        description=description,
        doc_link=doc_link,
        risk=risk,
    )
    result.present = any(v is not None for v in (display_name, description, doc_link))

    if not display_name:
        result.warnings.append(f"agent '{agent_id}': missing display_name in {where}")
    if not description:
        result.warnings.append(f"agent '{agent_id}': missing description/purpose in {where}")
    return result
