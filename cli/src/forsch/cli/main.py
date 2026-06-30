"""forsch — the Forsch Factory CLI.

One front door over the manifest -> factory -> builder -> bridge: scaffold, build,
promote, check, run the local web builder, test, and operate the bridge — without
remembering which venv, lane, or path each step lives in. The manifest
(agent_specs/agents.yaml) stays the source of truth; forsch is ergonomics on top.
"""
from __future__ import annotations

import os
import subprocess
import sys
from io import StringIO

import click

from forsch.cli.scaffold import new_agent_block
from forsch.cli.workspace import bootstrap_path, find_workspace


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option("0.1.0", prog_name="forsch")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Forsch Factory — build and operate your ADK agent fleet."""
    ws = find_workspace()
    if ws is None:
        raise click.ClickException(
            "not inside a Forsch Factory workspace (no agent_specs/agents.yaml found). "
            "cd into the workspace, or set FORSCH_ADK_WORKSPACE."
        )
    bootstrap_path(ws)
    ctx.obj = ws


# --------------------------------------------------------------------------- manifest

@cli.command()
@click.argument("agent_id")
@click.option("--description", default="", help="one-line description")
@click.option("--no-build", is_flag=True, help="add the manifest block only; skip regenerate")
@click.pass_obj
def new(ws, agent_id: str, description: str, no_build: bool) -> None:
    """Scaffold a new agent in the manifest, then build it."""
    from ruamel.yaml import YAML

    mpath = ws / "agent_specs" / "agents.yaml"
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(mpath.read_text())
    if agent_id in (data.get("agents") or {}):
        raise click.ClickException(f"agent '{agent_id}' already exists in the manifest")
    data["agents"][agent_id] = new_agent_block(agent_id, description)
    buf = StringIO()
    yaml.dump(data, buf)
    mpath.write_text(buf.getvalue())
    click.secho(f"+ added {agent_id} to the manifest", fg="green")
    if not no_build:
        _apply(ws, agent_id)


@cli.command()
@click.argument("agent", required=False)
@click.option("--all", "all_", is_flag=True, help="build every agent in the manifest")
@click.option("--force", is_flag=True, help="bypass the deploy gate (write even if tools are red)")
@click.pass_obj
def build(ws, agent: str | None, all_: bool, force: bool) -> None:
    """Regenerate an agent's artifacts from the manifest (factory apply)."""
    for aid in _agent_ids(ws, agent, all_):
        _apply(ws, aid, force=force)


@cli.command()
@click.argument("agent")
@click.pass_obj
def plan(ws, agent: str) -> None:
    """Dry-run: list what build would write, change nothing."""
    from forsch.adk_factory.cli import plan as factory_plan

    res = factory_plan(ws / "agent_specs" / "agents.yaml", agent)
    click.echo(f"[plan] {agent} would write:")
    for f in res["files"]:
        click.echo(f"    {f['path']}")


@cli.command()
@click.argument("agent", required=False)
@click.pass_obj
def check(ws, agent: str | None) -> None:
    """Validate an agent's tools — the deploy gate. No agent = the whole fleet."""
    from forsch.adk_factory.loader import load_manifest
    from forsch.adk_factory.validation import format_report_text, validate_agent_tools

    manifest = load_manifest(ws / "agent_specs" / "agents.yaml")
    for aid in _agent_ids(ws, agent, agent is None):
        click.secho(f"[{aid}]", bold=True)
        click.echo(format_report_text(validate_agent_tools(manifest.agents[aid])))


@cli.command()
@click.argument("agent")
@click.pass_obj
def promote(ws, agent: str) -> None:
    """Fold builder edits (web_agents/<id>/root_agent.yaml) back into the manifest."""
    from forsch.adk_builder.promote import promote_agent

    res = promote_agent(str(ws), agent)
    folded = ", ".join(res["patch_keys"]) or "nothing (already in sync)"
    click.secho(f"promoted {agent}: folded {folded}", fg="green")
    for w in res["written"]:
        click.echo(f"    {w}")


@cli.command()
@click.option("--family", help="only this family")
@click.pass_obj
def tools(ws, family: str | None) -> None:
    """List the Forsch tool catalog (what the palette shows)."""
    from forsch_palette import build_catalog

    from forsch.cli.ui import console, tool_table

    console.print(tool_table(build_catalog(), family))


# ------------------------------------------------------------------------- run surfaces

@cli.command()
@click.pass_obj
def web(ws) -> None:
    """Launch ADK Web + the Forsch Tool Palette locally (127.0.0.1:8000)."""
    py = _adk_python(ws)
    launcher = ws / "scripts" / "adk-web-local.py"
    os.execv(str(py), [str(py), str(launcher)])


@cli.command()
@click.option("--port", default=8080, show_default=True, help="port to serve on")
@click.pass_obj
def graph(ws, port: int) -> None:
    """Serve the live-agent-graph locally — watch agents appear/update as you build."""
    serve = ws / "packages" / "live-agent-graph" / "serve.py"
    if not serve.exists():
        raise click.ClickException("live-agent-graph is not in this workspace")
    click.secho(f"live graph → http://127.0.0.1:{port}  (build agents to watch them update)", fg="green")
    raise SystemExit(subprocess.call(["python3", str(serve), str(port)], cwd=str(serve.parent)))


@cli.command()
@click.pass_obj
def chat(ws) -> None:
    """Talk to the Forsch Factory operator — an AI that drives the factory and knows ADK docs."""
    from forsch.cli.operator import run_repl

    run_repl(ws)


@cli.command(name="eval")
@click.argument("agent")
@click.option("--new", "scaffold", is_flag=True, help="write a starter eval set and exit")
@click.option("--threshold", type=float, default=0.7, show_default=True, help="pass threshold (0-1)")
@click.pass_obj
def eval_cmd(ws, agent: str, scaffold: bool, threshold: float) -> None:
    """Grade an agent against its eval set with an LLM judge on your gateway (no Vertex)."""
    from forsch.cli.evals import eval_set_path, run_eval, scaffold_eval_set

    set_file = eval_set_path(ws, agent)
    if scaffold or not set_file.exists():
        scaffold_eval_set(set_file, agent)
        click.secho(f"  scaffolded {set_file.relative_to(ws)}", fg="green")
        click.echo(f"  fill in each case's expected response, then: forsch eval {agent}")
        return
    raise SystemExit(0 if run_eval(ws, agent, set_file, threshold=threshold) else 1)


@cli.command(name="goal")
@click.argument("text")
@click.option("--max-iters", default=12, show_default=True, help="hard cap on loop iterations")
@click.pass_obj
def goal_cmd(ws, text: str, max_iters: int) -> None:
    """Pursue a goal autonomously (headless) — plan, execute safe steps, judge, park gated ones."""
    from forsch.cli.goal import run_goal

    run_goal(ws, text, max_iterations=max_iters)


@cli.command()
@click.argument("suite", type=click.Choice(["unit", "agents", "bridge", "chat"]), default="unit")
@click.pass_obj
def test(ws, suite: str) -> None:
    """Run a test suite in its correct venv/lane."""
    if suite == "unit":
        import shutil

        if shutil.which("uv") is None:
            raise click.ClickException("uv not found — the unit gate needs it to resolve pytest. A missing tool is a hard red, never a silent pass.")
        # `uv run` resolves the cli project + its dev group (pytest) reliably; if pytest can't be
        # found the run exits non-zero (no masked exit code), so a missing tool can't pass green.
        raise SystemExit(subprocess.call(
            ["uv", "run", "--project", str(ws / "cli"), "pytest", "-q", "tests"], cwd=str(ws / "cli")))
    raise SystemExit(subprocess.call(["make", f"test-{suite}"], cwd=str(ws)))


@cli.command()
@click.argument("action", type=click.Choice(["up", "restart", "build"]))
@click.pass_obj
def bridge(ws, action: str) -> None:
    """Operate the adk-bridge container (up / restart / build)."""
    if action == "restart":
        raise SystemExit(subprocess.call(["docker", "restart", "adk-bridge"]))
    args = ["docker", "compose", "up", "-d"] if action == "up" else ["docker", "compose", "build"]
    raise SystemExit(subprocess.call(args, cwd=str(ws / "bridge")))


@cli.command()
@click.pass_obj
def doctor(ws) -> None:
    """Check workspace + lane health."""
    from forsch.cli.ui import check, console

    console.print(f"[dim]workspace[/]  {ws}")
    console.print(check("manifest", (ws / "agent_specs" / "agents.yaml").is_file(), "agent_specs/agents.yaml"))
    adk_pkg = "packages/adk-components" if (ws / "packages" / "adk-components").exists() else "components"
    for venv in (f"{adk_pkg}/.venv", "factory/.venv", "builder/.venv"):
        console.print(check(venv, (ws / venv).exists(), "host py3.x lane"))
    console.print(check("LITELLM_BASE_URL", bool(os.environ.get("LITELLM_BASE_URL")),
                        os.environ.get("LITELLM_BASE_URL", "unset (web/run need it)")))
    console.print(check(".adk-local.env", (ws / ".adk-local.env").exists(), "local gateway creds"))
    console.print(check("docker", _silent(["docker", "info"]), "container lane (bridge)"))


# ------------------------------------------------------------------------------ helpers

def _agent_ids(ws, agent: str | None, all_: bool) -> list[str]:
    from forsch.adk_factory.loader import load_manifest

    if all_:
        return list(load_manifest(ws / "agent_specs" / "agents.yaml").agents)
    if not agent:
        raise click.ClickException("give an agent id, or --all")
    return [agent]


def _apply(ws, agent_id: str, force: bool = False) -> None:
    from forsch.adk_factory.cli import apply
    from forsch.adk_factory.loader import load_manifest
    from forsch.adk_factory.validation import DeployGateBlocked, format_report_text

    from forsch.cli.graph import sync_agent_to_graph_registry

    try:
        res = apply(ws / "agent_specs" / "agents.yaml", agent_id, ws, force=force)
        click.secho(f"built {agent_id}: {len(res['written'])} file(s)", fg="green")
        spec = load_manifest(ws / "agent_specs" / "agents.yaml").agents[agent_id]
        if sync_agent_to_graph_registry(ws, agent_id, spec.model_dump()):
            click.secho(f"  ↺ synced {agent_id} into the live graph", fg="cyan")
    except DeployGateBlocked as exc:
        click.secho(f"build BLOCKED for {agent_id} — {exc.report.summary['red']} red tool(s)", fg="red")
        click.echo(format_report_text(exc.report))
        raise SystemExit(1)


def _line(label: str, ok: bool, detail: str = "") -> None:
    mark = click.style("ok", fg="green") if ok else click.style("--", fg="red")
    click.echo(f"  [{mark}] {label:<22} {detail}")


def _adk_python(ws):
    """The python that has ADK installed — components/.venv or packages/adk-components/.venv."""
    for rel in ("packages/adk-components/.venv", "components/.venv"):
        p = ws / rel / "bin" / "python"
        if p.exists():
            return p
    raise click.ClickException(
        "no ADK venv found (packages/adk-components/.venv or components/.venv) — run `uv sync` there first"
    )


def _silent(cmd: list[str]) -> bool:
    try:
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    cli()
