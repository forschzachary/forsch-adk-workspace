"""Pydantic models for the Factory.

``AgentSpec`` is one entry in the canonical manifest (``agent_specs/agents.yaml``),
normalized with ``defaults`` applied. ``Manifest`` is the whole file. These are the
deterministic input to the renderer — no runtime imports, no LLM.
"""

from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel, Field


class ToolBundle(BaseModel):
    """A named, reusable group of fully-qualified tool names.

    Lives under the top-level ``tool_bundles:`` block in the manifest. It is a
    refactor of *declaration* only — at generation time the Factory expands each
    agent's bundle references into a flat tool list, so the runnable ``agent.py``
    never knows bundles existed.
    """

    description: str = ""
    tools: list[str] = Field(default_factory=list)


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
    # bundles → references into the top-level ``tool_bundles:`` map. Each entry is
    # either a bare bundle name (str, "all tools") or a mapping
    # ``{bundle: <name>, only|exclude: [...]}``. The dict shape is validated
    # structurally in ``bundles.expand_bundles`` (kept out of pydantic so the model
    # stays dumb). Expanded into ``tools`` at generation time; the runnable
    # ``agent.py`` never sees this field.
    bundles: list[Union[str, dict]] = Field(default_factory=list)
    smoke_prompts: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    """The whole ``agents.yaml`` — the single writable source of truth."""

    version: int = 1
    agents: dict[str, AgentSpec] = Field(default_factory=dict)
    # tool_bundles → named groups of tools, a layer of organization above
    # individual tools. Keyed by bundle name. NOT merged with ``defaults`` (a
    # bundle is not an agent); passed through verbatim by the loader.
    tool_bundles: dict[str, ToolBundle] = Field(default_factory=dict)
