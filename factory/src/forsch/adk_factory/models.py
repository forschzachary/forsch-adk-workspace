"""Pydantic models for the Factory.

``AgentSpec`` is one entry in the canonical manifest (``agent_specs/agents.yaml``),
normalized with ``defaults`` applied. ``Manifest`` is the whole file. These are the
deterministic input to the renderer — no runtime imports, no LLM.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AgentSpec(BaseModel):
    """A single agent's contract, fully resolved (defaults merged in)."""

    id: str
    package: str
    attr: str = "root_agent"
    adk_name: str
    agent_class: str = "LlmAgent"
    description: str = ""
    model_code: str
    instruction: str = ""
    # group → a preamble component (preambles/<group>.md) the factory prepends to
    # the instruction at render time. The manifest keeps only the agent's own job.
    group: Optional[str] = None
    # model → the LiteLLM model name pinned for this agent (routing/fallback owned
    # by LiteLLM). None = the shared FORSCH_ADK_MODEL default.
    model: Optional[str] = None
    web_entrypoint: Optional[str] = None
    discord_channels: list[str] = Field(default_factory=list)
    safety_level: str = "read_only"
    purpose: str = ""
    tools: list[str] = Field(default_factory=list)
    smoke_prompts: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    """The whole ``agents.yaml`` — the single writable source of truth."""

    version: int = 1
    agents: dict[str, AgentSpec] = Field(default_factory=dict)
