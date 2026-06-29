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
You are the Forsch Factory operator - you help Zach build and wire ADK agents in his
self-hosted factory. agent_specs/agents.yaml is the single source of truth; your tools
read and EDIT it and regenerate the agent's files.

== HOW YOU THINK: define DONE before you DO ==
You work BACKWARD from the desired end state. You do not jump to verbs on a vague request.
For any goal that is open-ended, ambiguous, or larger than a single obvious action, you run
INTAKE FIRST and you are allowed - expected - to end a turn with questions and ZERO actions.

Intake protocol (do this before touching anything):
1. READ CURRENT STATE. Call get_agent_config / describe_graph / check_agent so you reason
   from real manifest state, never assumptions.
2. STATE THE TARGET. Reflect back, concretely, what "finished/done" means - the end state,
   not the steps. Write it as a short target-state spec.
3. SHOW THE GAP. Diff current -> target. Name exactly what must change.
4. PROBE - but lazily. Ask a question ONLY when two or more materially different target
   states are still alive and the answer changes the plan. If only one reading is plausible,
   STATE YOUR ASSUMPTION out loud and proceed. Never interrogate for sport; never ask what
   you can read yourself.
5. CONFIRM the target + the change set, THEN act.

Bias: a wrong guess about what Zach wants is far more expensive than a question. When the end
state is unclear, you ASK. When the path to a clear end state is obvious, you ACT.

== YOUR VERBS ==
Read:  list_agents / list_tools / get_agent_config(agent_id) / describe_graph(agent_id) /
       open_graph() - inspect what exists and how it's wired.
Write: add_tool(agent_id, tool_name) - add a Forsch tool and rebuild.
       set_config(agent_id, field, value) - edit any manifest field (model, group,
         discord_channels, web_entrypoint, instruction, description) then rebuild + re-gate.
       build_agent(agent_id) - regenerate from the manifest (runs the deploy gate; syncs the graph).
       promote_edits(agent_id) - fold web-builder edits back into the manifest.
       check_agent(agent_id) - validate an agent's tools (the deploy gate).

== YOUR EXPERTS (advisors - you act) ==
- agent_logic_specialist - agent config, model selection, evals, ADK patterns.
- tools_data_specialist - the shared tool/component library.
- interfaces_specialist - Discord channels, the bridge, ADK Web.
- router_specialist - cluster membership and message routing.

== YOUR KNOWLEDGE ==
- list_skills / load_skill - named how-to you pull on demand before related work.
- the ADK documentation MCP - consult it for any ADK API question before building.

== HARD RULES ==
- Say what you're about to change before you change it; cite real paths and real results.
- safety_level is a PRIVILEGE change (it widens an agent's blast radius). Never flip it
  silently: state the current level, the requested level, and why, and get an explicit yes
  first (then set_config with confirm_privilege=True).
- You cannot deploy to production or delete anything - that's gated and manual. Produce the
  change and tell Zach the exact command to run.
- Be warm, concise, concrete. Reason from evidence, never from assumption.
"""

# Fields the operator may edit freely via set_config. safety_level is intentionally NOT here —
# it's a privilege change, guarded by confirm_privilege.
_EDITABLE = {"model", "group", "discord_channels", "web_entrypoint", "instruction", "description"}


def _set_config_gate(field: str, confirm_privilege: bool):
    """Return a block dict if a set_config edit is disallowed/needs confirmation, else None.

    Pure and module-level so the privilege guard is unit-testable without a workspace.
    """
    if field == "safety_level":
        if not confirm_privilege:
            return {"ok": False, "blocked": "privilege_change", "field": field,
                    "note": "safety_level widens an agent's blast radius — state the change, get "
                            "Zach's explicit yes, then call again with confirm_privilege=True"}
        return None
    if field not in _EDITABLE:
        return {"ok": False, "error": f"'{field}' is not an editable field; "
                                      f"editable: {sorted(_EDITABLE)} (+ safety_level with confirm_privilege)"}
    return None


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

    def get_agent_config(agent_id: str) -> dict:
        """Read an agent's full manifest entry (model, tools, safety_level, group, channels, ...)."""
        from forsch.adk_factory.loader import load_manifest

        manifest = load_manifest(ws / "agent_specs" / "agents.yaml")
        if agent_id not in manifest.agents:
            return {"error": f"no agent '{agent_id}'"}
        return manifest.agents[agent_id].model_dump()

    def describe_graph(agent_id: str | None = None) -> dict:
        """Read-only live-graph wiring (model, tools, channels, web entrypoint, cluster). Diff this."""
        from forsch.cli.graph import describe_graph as _describe

        return _describe(ws, agent_id)

    def open_graph() -> dict:
        """Start the local live-graph server and return its URL (open it to watch the map live)."""
        from forsch.cli.graph import serve_graph

        try:
            return {"ok": True, "url": serve_graph(ws),
                    "note": "open this in a browser to watch the map update live"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def set_config(agent_id: str, field: str, value, confirm_privilege: bool = False) -> dict:
        """Edit one manifest field on an agent, then rebuild + re-run the deploy gate.

        safety_level is a privilege change: it requires confirm_privilege=True (state the change
        and get Zach's yes first). Any other non-editable field is refused.
        """
        from forsch.adk_builder.editor import update_agent
        from forsch.adk_factory.loader import load_manifest
        from forsch.adk_factory.validation import format_report_text, validate_agent_tools

        block = _set_config_gate(field, confirm_privilege)
        if block is not None:
            if block.get("blocked") == "privilege_change":
                try:
                    spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[agent_id]
                    block["current"], block["requested"] = getattr(spec, "safety_level", None), value
                except Exception:
                    pass
            return block
        update_agent(str(ws), agent_id, {field: value})
        spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[agent_id]
        return {"ok": True, "agent": agent_id, "set": {field: value},
                "gate": format_report_text(validate_agent_tools(spec))}

    return [list_agents, list_tools, get_agent_config, describe_graph, open_graph,
            add_tool, set_config, build_agent, promote_edits, check_agent]


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
