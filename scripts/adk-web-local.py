#!/usr/bin/env python
"""Local ADK Web launcher — Forsch agents + the built-in builder assistant on your LiteLLM gateway.

Why this exists:
  * `adk web web_agents` unlocks Builder Mode (the pencil): an app is editable purely
    because web_agents/<id>/root_agent.yaml exists. That needs no model.
  * But *running/tracing* an agent, and the in-UI "Assistant" panel, both need a model.
    The Forsch agents read LITELLM_BASE_URL / LITELLM_HERMES_KEY; the built-in assistant
    (__adk_agent_builder_assistant) hard-defaults to gemini-2.5-pro via Google and dies
    with "No API key was provided" on a host with no Google creds.

This launcher loads .adk-local.env (gitignored: gateway URL + key), puts every
agents/<id>/src on sys.path so the YAML model_code/tool refs resolve, repoints the
built-in assistant onto the gateway, then serves `adk web web_agents` on 127.0.0.1:8000.

Run:  components/.venv/bin/python scripts/adk-web-local.py
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env(path: Path) -> None:
    if not path.exists():
        sys.exit(
            f"missing {path}\n"
            "create it (gitignored) with two lines:\n"
            "  LITELLM_BASE_URL=http://<gateway-host>:4000/v1\n"
            "  LITELLM_HERMES_KEY=<your gateway key>"
        )
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.replace("export ", "").strip(), val.strip().strip('"').strip("'"))


def _repoint_builder_assistant() -> None:
    """Route the built-in __adk_agent_builder_assistant onto the Forsch gateway.

    Two global seams, both chosen so they survive the agent_loader re-instantiating the
    assistant from a bare module (a different object than the fully-qualified package):

      1. LLMRegistry.new_llm — LlmAgent.canonical_model resolves *string* models through
         here, so mapping any 'gemini*' string to a gateway LiteLlm covers the assistant
         AND its sub-agents, wherever they're built.
      2. AgentLoader.load_agent — after the assistant loads, drop its google_search /
         url_context AgentTools: Gemini-native grounding that can't run through a proxy.
         The remaining file/config/ADK-search FunctionTools are its real build value.
    """
    from google.adk.cli.utils import agent_loader as al
    from google.adk.models import registry as reg
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.tools.agent_tool import AgentTool

    base = os.environ["LITELLM_BASE_URL"]
    key = os.environ["LITELLM_HERMES_KEY"]

    def _gateway_model():
        return LiteLlm(model="openai/gpt-5.5", api_base=base, api_key=key)

    # (1) model-resolution hook
    _orig_new_llm = reg.LLMRegistry.new_llm

    def _new_llm(model):
        if isinstance(model, str) and model.lower().startswith("gemini"):
            return _gateway_model()
        return _orig_new_llm(model)

    reg.LLMRegistry.new_llm = staticmethod(_new_llm)

    # (2) loader hook: strip grounding AgentTools from the assistant after it loads
    _orig_load = al.AgentLoader.load_agent

    def _load_agent(self, agent_name):
        agent = _orig_load(self, agent_name)
        if "adk_agent_builder_assistant" in agent_name:
            target = getattr(agent, "root_agent", agent)
            tools = getattr(target, "tools", None)
            if tools:
                kept = [t for t in tools if not isinstance(t, AgentTool)]
                try:
                    target.tools = kept
                except Exception:
                    object.__setattr__(target, "tools", kept)
        return agent

    al.AgentLoader.load_agent = _load_agent


def main() -> None:
    _load_env(ROOT / ".adk-local.env")
    os.environ.setdefault("FORSCH_ADK_WORKSPACE", str(ROOT))

    # scripts/ on the path so the launcher can import the palette module.
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    # Every agent package on the path so web_agents/<id>/root_agent.yaml code refs resolve.
    for src in sorted(glob.glob(str(ROOT / "agents" / "*" / "src"))):
        if src not in sys.path:
            sys.path.insert(0, src)

    _repoint_builder_assistant()

    # Build ADK's own FastAPI app so we can mount the Forsch Tool Palette beside the
    # builder, instead of handing off to the opaque `adk web` CLI.
    import uvicorn
    from google.adk.cli.fast_api import get_fast_api_app

    app = get_fast_api_app(
        agents_dir=str(ROOT / "web_agents"),
        web=True,
        host="127.0.0.1",
        port=8000,
        reload_agents=False,
    )

    from forsch_palette import mount_palette

    mount_palette(app, ROOT)

    print("ADK Web + Forsch Tool Palette -> http://127.0.0.1:8000  (palette at /forsch)")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
