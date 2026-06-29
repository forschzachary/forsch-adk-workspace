"""The Forsch Factory operator — an ADK agent you talk to in the terminal (`forsch chat`).

Its tools are the *safe* factory verbs (list / build / promote / add-tool / check — no
deploy, no delete, no bridge ops), so it can author and wire agents but can't ship to
prod or destroy anything; the deploy gate still runs on every build. It also carries the
ADK documentation MCP, so it can answer ADK API questions and build in the same breath.

It runs on your LiteLLM gateway (gpt-5.5), reading creds from `.adk-local.env`.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

_INSTRUCTION = """\
You are the Forsch Factory operator — you help Zach build and wire ADK agents in his
self-hosted factory. agent_specs/agents.yaml is the single source of truth; your tools
edit it and regenerate the agent's files.

Tools you have:
- list_agents / list_tools — see what exists.
- add_tool(agent_id, tool_name) — add a Forsch tool to an agent and rebuild it.
- build_agent(agent_id) — regenerate an agent from the manifest (runs the deploy gate).
- promote_edits(agent_id) — fold an agent's web-builder edits back into the manifest.
- check_agent(agent_id) — validate an agent's tools.
- the ADK documentation — consult it for any ADK API question (callbacks, agent types,
  tool patterns) before answering or building.

Rules: say what you're about to change before you change it. You cannot deploy to
production or delete anything — that's gated and manual; tell Zach to run those verbs
himself. Be warm, concise, and concrete.
"""


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.replace("export ", "").strip(), val.strip().strip('"').strip("'"))


def _make_tools(ws: Path) -> list:
    """The safe authoring verbs, as plain callables ADK auto-wraps into FunctionTools."""

    def list_agents() -> list[str]:
        """List the agent ids in the manifest."""
        from forsch.adk_factory.loader import load_manifest

        return list(load_manifest(ws / "agent_specs" / "agents.yaml").agents)

    def list_tools() -> list[dict]:
        """List the Forsch tools available to add to an agent (name, family, description)."""
        from forsch_palette import build_catalog

        return [{"name": t["name"], "family": t["family"], "description": t["desc"]} for t in build_catalog()]

    def add_tool(agent_id: str, tool_name: str) -> dict:
        """Add a Forsch tool (e.g. 'log_groceries') to an agent in the manifest and rebuild it."""
        from forsch.adk_builder.editor import update_agent
        from forsch.adk_factory.loader import load_manifest

        spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[agent_id]
        bare = [t.rsplit(".", 1)[-1] for t in spec.tools]
        leaf = tool_name.rsplit(".", 1)[-1]
        if leaf in bare:
            return {"ok": True, "note": f"{leaf} is already on {agent_id}"}
        update_agent(str(ws), agent_id, {"tools": bare + [leaf]})
        return {"ok": True, "added": leaf, "agent": agent_id}

    def build_agent(agent_id: str) -> dict:
        """Regenerate an agent's files from the manifest (factory apply; runs the deploy gate)."""
        from forsch.adk_factory.cli import apply

        res = apply(ws / "agent_specs" / "agents.yaml", agent_id, ws)
        return {"ok": True, "agent": agent_id, "files_written": len(res["written"])}

    def promote_edits(agent_id: str) -> dict:
        """Fold an agent's web-builder edits (root_agent.yaml) back into the manifest, then rebuild."""
        from forsch.adk_builder.promote import promote_agent

        res = promote_agent(str(ws), agent_id)
        return {"ok": True, "agent": agent_id, "folded": res["patch_keys"]}

    def check_agent(agent_id: str) -> str:
        """Validate an agent's tools (the deploy gate); returns the report text."""
        from forsch.adk_factory.loader import load_manifest
        from forsch.adk_factory.validation import format_report_text, validate_agent_tools

        spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[agent_id]
        return format_report_text(validate_agent_tools(spec))

    return [list_agents, list_tools, add_tool, build_agent, promote_edits, check_agent]


def _adk_docs_toolset():
    """The ADK documentation as an MCP toolset (the same adk-docs server Claude Code uses)."""
    from google.adk.tools.mcp_tool import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="uvx",
                args=["--from", "mcpdoc", "mcpdoc", "--urls",
                      "AgentDevelopmentKit:https://adk.dev/llms.txt", "--transport", "stdio"],
            ),
            timeout=60,
        )
    )


def create_operator(ws: Path, with_docs: bool = True):
    """Build the operator LlmAgent: factory verbs + (optionally) the ADK docs MCP, on the gateway."""
    from google.adk import Agent
    from google.adk.models.lite_llm import LiteLlm

    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    model = LiteLlm(model="openai/gpt-5.5", api_base=base, api_key=key)
    tools = _make_tools(ws)
    if with_docs:
        tools.append(_adk_docs_toolset())
    return Agent(name="forsch_operator", model=model, instruction=_INSTRUCTION, tools=tools)


async def _loop(agent) -> None:
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from rich.markdown import Markdown

    from forsch.cli.ui import ACCENT, banner, console, tool_call_line

    runner = InMemoryRunner(agent=agent, app_name="forsch")
    session = await runner.session_service.create_session(app_name="forsch", user_id="zach")
    banner()
    while True:
        try:
            query = console.input(f"[bold {ACCENT}]forsch[/] [dim]›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not query:
            continue
        if query in ("exit", "quit"):
            break
        content = types.Content(role="user", parts=[types.Part(text=query)])
        chunks: list[str] = []
        with console.status("[dim]thinking…[/]", spinner="dots"):
            async for event in runner.run_async(user_id="zach", session_id=session.id, new_message=content):
                for call in event.get_function_calls() or []:
                    console.print(tool_call_line(call.name, call.args))
                if event.is_final_response() and event.content:
                    for part in event.content.parts or []:
                        if getattr(part, "text", None):
                            chunks.append(part.text)
        if chunks:
            console.print(Markdown("".join(chunks)))
        console.print()


def run_repl(ws: Path) -> None:
    import logging
    import warnings

    warnings.filterwarnings("ignore")
    logging.disable(logging.INFO)
    _load_env(ws / ".adk-local.env")
    if not os.environ.get("LITELLM_BASE_URL"):
        raise SystemExit(
            "no gateway configured — add LITELLM_BASE_URL + a key to .adk-local.env to chat."
        )
    asyncio.run(_loop(create_operator(ws)))
