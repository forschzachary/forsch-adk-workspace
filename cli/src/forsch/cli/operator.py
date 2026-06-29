"""The Forsch Factory operator — an ADK agent you talk to in the terminal (`forsch chat`).

It drives the factory through safe verbs (list / build / promote / add-tool / check — no
deploy, no delete), carries the ADK documentation MCP, and now also:
  - PERSISTENT SESSIONS — conversations survive restarts (SQLite); /sessions, /new, /resume.
  - LANE-SPECIALISTS — four background expert sub-agents (agent-logic, tools-data, interfaces,
    router) it consults under the hood, so it's one seamless chat with experts behind it.
  - SKILLS — named know-how files it can list + load on demand (/skills).
  - /goal — turbocharged goal pursuit: plan -> consult specialists -> execute -> verify.

It runs on your LiteLLM gateway (gpt-5.5), reading creds from `.adk-local.env`.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

APP = "forsch"
USER = "zach"

_INSTRUCTION = """\
You are the Forsch Factory operator — you help Zach build and wire ADK agents in his
self-hosted factory. agent_specs/agents.yaml is the single source of truth; your tools
edit it and regenerate the agent's files.

Your verbs:
- list_agents / list_tools — see what exists.
- add_tool(agent_id, tool_name) — add a Forsch tool to an agent and rebuild it.
- build_agent(agent_id) — regenerate an agent from the manifest (runs the deploy gate; also
  syncs the agent into the live graph).
- promote_edits(agent_id) — fold an agent's web-builder edits back into the manifest.
- check_agent(agent_id) — validate an agent's tools.

Your experts (consult them for layer-specific work — they're advisors, you act):
- agent_logic_specialist — agent config, model selection, evals, ADK patterns.
- tools_data_specialist — the shared tool/component library.
- interfaces_specialist — Discord channels, the bridge, ADK Web.
- router_specialist — cluster membership and message routing.

Your knowledge:
- list_skills / load_skill — named how-to you can pull on demand before related work.
- the ADK documentation MCP — consult it for any ADK API question before answering or building.

Rules: say what you're about to change before you change it. Consult the right specialist or
skill before non-trivial work. You cannot deploy to production or delete anything — that's
gated and manual; tell Zach the exact command to run. Be warm, concise, concrete; cite real
paths and real results, never assumptions.
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
        from forsch.adk_factory.loader import load_manifest

        from forsch.cli.graph import sync_agent_to_graph_registry

        res = apply(ws / "agent_specs" / "agents.yaml", agent_id, ws)
        spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[agent_id]
        synced = sync_agent_to_graph_registry(ws, agent_id, spec.model_dump())
        return {"ok": True, "agent": agent_id, "files_written": len(res["written"]), "graph_synced": synced}

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
    """Build the operator: factory verbs + skills + lane-specialists + (optionally) ADK docs."""
    from google.adk import Agent
    from google.adk.models.lite_llm import LiteLlm

    from forsch.cli.skills import make_skills_tools
    from forsch.cli.specialists import make_specialist_agenttools

    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    model = LiteLlm(model="openai/gpt-5.5", api_base=base, api_key=key)

    tools = _make_tools(ws)
    tools += make_skills_tools(ws)
    tools += make_specialist_agenttools(ws, model)
    if with_docs:
        tools.append(_adk_docs_toolset())
    return Agent(name="forsch_operator", model=model, instruction=_INSTRUCTION, tools=tools)


# --------------------------------------------------------------------------- sessions

def _session_service(ws: Path):
    """A persistent (SQLite) session service, or in-memory if ADK lacks it. (service, persistent)."""
    try:
        from google.adk.sessions.sqlite_session_service import SqliteSessionService
    except ImportError:
        from google.adk.sessions import InMemorySessionService

        return InMemorySessionService(), False
    db = ws / ".forsch" / "sessions.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSessionService(db_path=str(db)), True


async def _ordered_sessions(svc) -> list:
    resp = await svc.list_sessions(app_name=APP, user_id=USER)
    return sorted(resp.sessions, key=lambda s: getattr(s, "last_update_time", 0) or 0)


# ------------------------------------------------------------------------------- repl

def _print_help(console) -> None:
    console.print(
        "\n  [bold]commands[/]\n"
        "  [#b8a0ff]/goal <text>[/]   pursue a goal end-to-end — plan, execute safe steps, judge, checkpoint\n"
        "  [#b8a0ff]/goal[/] [dim]list · status <id> · resume <id>[/]   manage goal runs\n"
        "  [#b8a0ff]/skills[/]        list the skills the operator can load\n"
        "  [#b8a0ff]/sessions[/]      list your saved sessions\n"
        "  [#b8a0ff]/new[/]           start a fresh session\n"
        "  [#b8a0ff]/resume <id>[/]   switch to a saved session (id prefix)\n"
        "  [#b8a0ff]/help[/]          show this\n"
        "  [#b8a0ff]exit[/]           quit\n"
    )


async def _loop(ws: Path, agent) -> None:
    from google.adk.runners import Runner
    from google.genai import types
    from rich.markdown import Markdown

    from forsch.cli.goal import handle_goal_command
    from forsch.cli.skills import list_skill_names
    from forsch.cli.ui import COSMIC, banner, console, tool_call_line

    svc, persistent = _session_service(ws)
    runner = Runner(agent=agent, app_name=APP, session_service=svc, auto_create_session=True)

    prior = await _ordered_sessions(svc)
    if prior:
        session_id = prior[-1].id
        opened = f"resumed [{COSMIC}]{session_id[:8]}[/] [dim]· {len(prior)} on file · /new for fresh · /sessions to list[/]"
    else:
        session_id = (await svc.create_session(app_name=APP, user_id=USER)).id
        opened = f"new session [{COSMIC}]{session_id[:8]}[/]"

    banner()
    note = "" if persistent else " [dim](in-memory — ADK has no sqlite sessions here)[/]"
    console.print(f"  [dim]{opened}[/]{note}\n")

    async def run_turn(text: str) -> None:
        content = types.Content(role="user", parts=[types.Part(text=text)])
        chunks: list[str] = []
        with console.status(f"[{COSMIC}]✦ thinking…[/]", spinner="star2", spinner_style=COSMIC):
            async for event in runner.run_async(user_id=USER, session_id=session_id, new_message=content):
                for call in event.get_function_calls() or []:
                    console.print(tool_call_line(call.name, call.args))
                if event.is_final_response() and event.content:
                    for part in event.content.parts or []:
                        if getattr(part, "text", None):
                            chunks.append(part.text)
        if chunks:
            console.print(Markdown("".join(chunks)))
        console.print()

    while True:
        try:
            query = console.input(f"[bold #b8a0ff]forsch[/] [{COSMIC}]✦[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not query:
            continue
        if query in ("exit", "quit"):
            break

        if query.startswith("/"):
            cmd, _, arg = query[1:].partition(" ")
            cmd, arg = cmd.lower(), arg.strip()
            if cmd in ("help", "?"):
                _print_help(console)
            elif cmd == "skills":
                names = list_skill_names(ws)
                console.print(f"  [bold]skills[/]: {', '.join(names) if names else 'none'}\n")
            elif cmd == "sessions":
                for s in await _ordered_sessions(svc):
                    mark = "›" if s.id == session_id else " "
                    console.print(f"  {mark} [{COSMIC}]{s.id[:8]}[/]")
                console.print()
            elif cmd == "new":
                session_id = (await svc.create_session(app_name=APP, user_id=USER)).id
                console.print(f"  [dim]new session [/][{COSMIC}]{session_id[:8]}[/]\n")
            elif cmd == "resume":
                match = next((s for s in await _ordered_sessions(svc) if s.id.startswith(arg)), None) if arg else None
                if match:
                    session_id = match.id
                    console.print(f"  [dim]resumed [/][{COSMIC}]{session_id[:8]}[/]\n")
                else:
                    console.print(f"  [red]no session matching '{arg}'[/]\n")
            elif cmd == "goal":
                await handle_goal_command(ws, arg)
            else:
                console.print(f"  [dim]unknown command /{cmd} — try /help[/]\n")
            continue

        await run_turn(query)


def run_repl(ws: Path) -> None:
    import logging
    import warnings

    from forsch.cli.ui import black_terminal

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    _load_env(ws / ".adk-local.env")
    if not os.environ.get("LITELLM_BASE_URL"):
        raise SystemExit(
            "no gateway configured — add LITELLM_BASE_URL + a key to .adk-local.env to chat."
        )
    with black_terminal():
        asyncio.run(_loop(ws, create_operator(ws)))
