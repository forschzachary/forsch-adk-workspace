"""Tests for the read-only workspace collector (Phase 1 TDD, step 3).

The collector statically walks an ADK workspace and returns one structured
``Workspace`` model: agents (joined from the contract + runtime package + web
wrapper + bridge route + tools + metadata), shared tools, docs, and warnings
(missing display metadata, and drift such as a bridge route with no agent
contract). It must be READ-ONLY and never import runtime agent modules.
"""

import textwrap
from pathlib import Path

from forsch.adk_builder.collector import collect_workspace


def _make_workspace(tmp_path: Path) -> Path:
    (tmp_path / "agent_specs").mkdir()
    (tmp_path / "agent_specs" / "agents.yaml").write_text(
        textwrap.dedent(
            """\
            agents:
              stability:
                package: forsch.agent_stability.agent
                attr: root_agent
                web_entrypoint: web_agents/stability
                safety_level: read_only
                purpose: Audit the workspace without changing source.
                tools:
                  - forsch.adk_components.tools.get_workspace_inventory
            """
        )
    )
    (tmp_path / "agents" / "stability").mkdir(parents=True)
    (tmp_path / "agents" / "stability" / "__init__.py").write_text("")

    (tmp_path / "web_agents" / "stability").mkdir(parents=True)
    (tmp_path / "web_agents" / "stability" / "agent.py").write_text("root_agent = object()\n")

    (tmp_path / "bridge").mkdir()
    (tmp_path / "bridge" / "bridge_config.yaml").write_text(
        textwrap.dedent(
            """\
            agents:
              stability:
                agent_package: forsch.agent_stability.agent
                agent_attr: root_agent
                channels:
                  - "#team-stability"
              ops:
                agent_package: forsch.agent_ops.agent
                agent_attr: agent
                channels:
                  - "#team-ops"
            """
        )
    )

    tools_dir = tmp_path / "components" / "src" / "forsch" / "adk_components" / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "inventory.py").write_text(
        textwrap.dedent(
            '''\
            """
            ---
            display_name: Workspace Inventory
            description: Scans the ADK workspace.
            risk: read_only
            kind: tool_wrapper
            ---
            """


            def get_workspace_inventory():
                return {}
            '''
        )
    )

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text("# Architecture\n")
    return tmp_path


def test_collector_finds_agent_from_contract(tmp_path):
    ws = collect_workspace(_make_workspace(tmp_path))

    stab = next(a for a in ws.agents if a.id == "stability")
    assert stab.contract_path.endswith("agent_specs/agents.yaml")
    assert stab.runtime_package == "forsch.agent_stability.agent"
    assert stab.web_wrapper_path is not None and "web_agents/stability" in stab.web_wrapper_path
    assert stab.metadata.risk == "read_only"
    assert "forsch.adk_components.tools.get_workspace_inventory" in stab.tools


def test_collector_attaches_bridge_channels_to_agent(tmp_path):
    ws = collect_workspace(_make_workspace(tmp_path))
    stab = next(a for a in ws.agents if a.id == "stability")
    assert "#team-stability" in stab.bridge_channels


def test_collector_flags_bridge_route_without_contract(tmp_path):
    # bridge routes 'ops', but agents.yaml has no 'ops' contract -> drift warning.
    ws = collect_workspace(_make_workspace(tmp_path))
    assert any("ops" in w and "contract" in w.lower() for w in ws.warnings)


def test_collector_collects_tools_with_metadata(tmp_path):
    ws = collect_workspace(_make_workspace(tmp_path))
    inv = next(t for t in ws.tools if "inventory" in t.name)
    assert inv.metadata.display_name == "Workspace Inventory"
    assert inv.metadata.risk == "read_only"
    assert inv.path.endswith("inventory.py")


def test_collector_lists_docs(tmp_path):
    ws = collect_workspace(_make_workspace(tmp_path))
    assert any(d.path.endswith("ARCHITECTURE.md") for d in ws.docs)


def test_collector_warns_on_missing_agent_display_name(tmp_path):
    # stability spec has purpose but no display_name -> missing-metadata warning.
    ws = collect_workspace(_make_workspace(tmp_path))
    assert any("stability" in w and "display_name" in w for w in ws.warnings)


def test_collector_is_read_only(tmp_path):
    root = _make_workspace(tmp_path)
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    collect_workspace(root)
    after = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    assert before == after  # collector created/removed nothing


def test_collector_tolerates_non_dict_bridge_entry(tmp_path):
    # Real bridge_config.yaml has `dm_fallback: assistant` under `agents:` — a
    # scalar, not a route spec. The collector must not crash on it.
    root = _make_workspace(tmp_path)
    (root / "bridge" / "bridge_config.yaml").write_text(
        textwrap.dedent(
            """\
            agents:
              stability:
                agent_package: forsch.agent_stability.agent
                channels:
                  - "#team-stability"
              dm_fallback: assistant
            """
        )
    )
    ws = collect_workspace(root)  # must not raise

    route_ids = [r.agent_id for r in ws.bridge_routes]
    assert "stability" in route_ids
    assert "dm_fallback" not in route_ids  # a scalar config value is not a route


def test_collector_ignores_venv_and_caches_when_scanning_tools(tmp_path):
    # Nested package repos carry their own .venv/site-packages and caches — the
    # tool scan must not treat installed third-party .py as workspace components.
    root = _make_workspace(tmp_path)
    venv_pkg = root / "components" / ".venv" / "lib" / "python3.12" / "site-packages" / "thirdparty"
    venv_pkg.mkdir(parents=True)
    (venv_pkg / "junk.py").write_text("x = 1\n")
    cache = root / "components" / "__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "cached.py").write_text("y = 1\n")

    ws = collect_workspace(root)
    names = [t.name for t in ws.tools]

    assert "junk" not in names  # .venv / site-packages excluded
    assert "cached" not in names  # __pycache__ excluded
    assert any("inventory" in n for n in names)  # the real component is still found
