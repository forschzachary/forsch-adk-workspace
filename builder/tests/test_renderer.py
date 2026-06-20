"""Tests for the dashboard renderer (Phase 1 TDD, step 5).

``render_dashboard(workspace)`` turns the collector's ``Workspace`` model into
self-contained HTML (no external network assets). Phase 1 is read-only: the
banner says so and any edit affordances are disabled.
"""

from forsch.adk_builder.models import (
    AgentEntry,
    BridgeRoute,
    DocEntry,
    Metadata,
    ToolEntry,
    Workspace,
)
from forsch.adk_builder.renderer import render_dashboard


def _sample_workspace() -> Workspace:
    return Workspace(
        root="/opt/data/workspace/adk",
        agents=[
            AgentEntry(
                id="stability",
                contract_path="agent_specs/agents.yaml",
                runtime_package="forsch.agent_stability.agent",
                web_wrapper_path="web_agents/stability",
                bridge_channels=["#team-stability"],
                tools=["forsch.adk_components.tools.get_workspace_inventory"],
                metadata=Metadata(display_name="Stability Governor", risk="read_only"),
                warnings=["agent 'stability': missing display_name in agent_specs/agents.yaml"],
            )
        ],
        tools=[
            ToolEntry(
                name="inventory",
                path="components/src/forsch/adk_components/tools/inventory.py",
                metadata=Metadata(
                    display_name="Workspace Inventory",
                    description="Scans the ADK workspace.",
                ),
            )
        ],
        docs=[DocEntry(path="docs/ARCHITECTURE.md", title="Architecture")],
        bridge_routes=[BridgeRoute(agent_id="ops", channels=["#team-ops"], has_contract=False)],
        warnings=["bridge route 'ops' has no agent contract in agent_specs/agents.yaml (drift)"],
    )


def test_render_includes_read_only_banner():
    html = render_dashboard(_sample_workspace())
    assert "READ ONLY" in html


def test_render_includes_each_agent_by_stable_id():
    html = render_dashboard(_sample_workspace())
    assert "stability" in html
    assert 'id="agent-stability"' in html  # stable anchor for left-nav


def test_render_includes_agent_paths():
    html = render_dashboard(_sample_workspace())
    assert "agent_specs/agents.yaml" in html
    assert "forsch.agent_stability.agent" in html
    assert "web_agents/stability" in html
    assert "#team-stability" in html  # bridge route


def test_render_includes_tool_display_name_and_description():
    html = render_dashboard(_sample_workspace())
    assert "Workspace Inventory" in html
    assert "Scans the ADK workspace." in html


def test_render_includes_doc_link():
    html = render_dashboard(_sample_workspace())
    assert "docs/ARCHITECTURE.md" in html


def test_render_shows_warning_badges():
    html = render_dashboard(_sample_workspace())
    assert "missing display_name" in html
    assert "drift" in html


def test_render_disables_edit_actions_in_phase1():
    html = render_dashboard(_sample_workspace())
    assert "disabled" in html.lower()  # edit affordance present but disabled


def test_render_includes_glossary_vocabulary():
    html = render_dashboard(_sample_workspace())
    assert "agent contract" in html.lower()


def test_render_escapes_html_to_avoid_injection():
    ws = _sample_workspace()
    ws.warnings.append("<script>alert('x')</script>")
    html = render_dashboard(ws)
    assert "<script>alert" not in html  # escaped, not raw
