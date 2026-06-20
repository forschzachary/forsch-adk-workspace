"""Pydantic models for the builder (Phase 1, read-only).

Small and read-only: these never write to the workspace. ``Metadata`` /
``ParsedMetadata`` back the metadata parser; the ``*Entry`` / ``Workspace``
models back the collector and renderer.
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
    """Result of parsing one metadata source (warn-not-crash)."""

    metadata: Metadata = Field(default_factory=Metadata)
    warnings: list[str] = Field(default_factory=list)
    path: Optional[str] = None
    present: bool = False


class AgentEntry(BaseModel):
    """An agent joined from the contract + runtime package + web wrapper + bridge route."""

    id: str
    contract_path: Optional[str] = None
    runtime_package: Optional[str] = None
    web_wrapper_path: Optional[str] = None
    bridge_channels: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)
    warnings: list[str] = Field(default_factory=list)


class ToolEntry(BaseModel):
    """A shared component tool file discovered by static scan."""

    name: str
    path: str
    metadata: Metadata = Field(default_factory=Metadata)
    warnings: list[str] = Field(default_factory=list)


class DocEntry(BaseModel):
    """A markdown doc discovered under the workspace."""

    path: str
    title: Optional[str] = None


class BridgeRoute(BaseModel):
    """A Discord→agent route from bridge_config.yaml, with contract-presence flag."""

    agent_id: str
    channels: list[str] = Field(default_factory=list)
    has_contract: bool = False


class Workspace(BaseModel):
    """The whole read-only workspace model the renderer consumes."""

    root: str
    agents: list[AgentEntry] = Field(default_factory=list)
    tools: list[ToolEntry] = Field(default_factory=list)
    docs: list[DocEntry] = Field(default_factory=list)
    bridge_routes: list[BridgeRoute] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
