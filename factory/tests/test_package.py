"""Functional-equivalence test for the rendered agent package.

We do NOT byte-match agent.py (a hand-written one wraps its instruction string
arbitrarily). Instead we EXECUTE the generated module against stubbed
``google.adk`` / ``forsch.adk_components.tools`` and capture the exact
``Agent(...)`` and ``LiteLlm(...)`` calls — proving the generated code builds
the agent the manifest describes, with no heavy deps in the factory venv.
"""

import sys
import types
from pathlib import Path

from forsch.adk_factory.loader import load_manifest
from forsch.adk_factory.renderer import render_agent_package

WS = Path("/root/.hermes/workspace/adk")


class _Recorder:
    """Stub callable that records the kwargs it was called with."""

    def __init__(self, store: dict, key: str):
        self._store = store
        self._key = key

    def __call__(self, **kwargs):
        self._store[self._key] = kwargs
        return object()


def _exec_generated(source: str, tool_leaves: list[str]) -> dict:
    recorded: dict = {}

    google = types.ModuleType("google")
    google_adk = types.ModuleType("google.adk")
    google_adk.Agent = _Recorder(recorded, "agent")
    google_adk_models = types.ModuleType("google.adk.models")
    lite_llm = types.ModuleType("google.adk.models.lite_llm")
    lite_llm.LiteLlm = _Recorder(recorded, "model")

    components = types.ModuleType("forsch.adk_components")
    tools = types.ModuleType("forsch.adk_components.tools")
    for leaf in tool_leaves:
        sentinel = types.SimpleNamespace()
        sentinel.__name__ = leaf
        setattr(tools, leaf, sentinel)

    stubs = {
        "google": google,
        "google.adk": google_adk,
        "google.adk.models": google_adk_models,
        "google.adk.models.lite_llm": lite_llm,
        "forsch.adk_components": components,
        "forsch.adk_components.tools": tools,
    }
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        ns: dict = {}
        exec(compile(source, "<generated agent.py>", "exec"), ns)
        recorded["namespace"] = ns
        return recorded
    finally:
        for k, prior in saved.items():
            if prior is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = prior


def test_generated_agent_constructs_equivalent_agent():
    m = load_manifest(WS / "agent_specs" / "agents.yaml")
    spec = m.agents["stability"]
    files = render_agent_package(spec)

    rel = next(p for p in files if p.endswith("agent.py"))
    assert rel == "agents/stability/src/forsch/agent_stability/agent.py"

    leaves = [t.rsplit(".", 1)[-1] for t in spec.tools]
    rec = _exec_generated(files[rel], leaves)

    agent_kwargs = rec["agent"]
    assert agent_kwargs["name"] == spec.adk_name
    assert agent_kwargs["description"] == spec.description
    assert agent_kwargs["instruction"] == spec.instruction.rstrip("\n")
    assert [t.__name__ for t in agent_kwargs["tools"]] == leaves

    assert rec["model"]["model"] == "openai/glm-5.2"  # stability is pinned in the manifest
    ns = rec["namespace"]
    assert ns["root_agent"] is ns["agent"]  # `agent = root_agent` alias
