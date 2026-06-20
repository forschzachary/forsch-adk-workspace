"""Pydantic models for builder metadata (Phase 1).

Kept deliberately small: just what the metadata parser and (later) the
collector/renderer need. Read-only — these models never write to the workspace.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    """Human-friendly metadata for a workspace artifact (tool, spec, doc)."""

    display_name: Optional[str] = None
    description: Optional[str] = None
    doc_link: Optional[str] = None
    owner: Optional[str] = None
    risk: Optional[str] = None
    kind: Optional[str] = None


class ParsedMetadata(BaseModel):
    """Result of parsing one metadata source.

    ``present`` distinguishes "no metadata found" (tolerated, no warning) from
    "metadata found". ``warnings`` carries non-fatal problems (malformed
    frontmatter, missing display fields) instead of raising.
    """

    metadata: Metadata = Field(default_factory=Metadata)
    warnings: list[str] = Field(default_factory=list)
    path: Optional[str] = None
    present: bool = False
