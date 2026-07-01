"""Tests for tool-bundle expansion (factory/src/forsch/adk_factory/bundles.py).

Two tiers of coverage:
  1. Unit: expand_bundles happy paths (bare, only, exclude, multi-bundle order +
     de-dupe, explicit-tools append) and every BundleError path.
  2. Golden safety contract: for the REAL manifest, every agent's bundle
     expansion reproduces the exact ordered tool list it shipped with before the
     bundles refactor. Bundles are a refactor of declaration, not behavior.
"""

from pathlib import Path

import pytest

from forsch.adk_factory.bundles import (
    BundleError,
    expand_bundles,
    validate_bundles,
)
from forsch.adk_factory.loader import load_manifest

P = "forsch.adk_components.tools."

DEFS = {
    "core": {"tools": [P + "a", P + "b", P + "c"]},
    "auth": {"tools": [P + "x", P + "y", P + "z"]},
    "empty": {"tools": []},
}


# --------------------------------------------------------------------------- #
# happy paths
# --------------------------------------------------------------------------- #
def test_bare_string_takes_whole_bundle_in_order():
    assert expand_bundles([], ["core"], DEFS) == [P + "a", P + "b", P + "c"]


def test_only_keeps_intersection_in_bundle_order():
    # 'only' names listed out of bundle order — result still follows bundle order.
    ref = {"bundle": "core", "only": [P + "c", P + "a"]}
    assert expand_bundles([], [ref], DEFS) == [P + "a", P + "c"]


def test_exclude_drops_named_tools():
    ref = {"bundle": "core", "exclude": [P + "b"]}
    assert expand_bundles([], [ref], DEFS) == [P + "a", P + "c"]


def test_multi_bundle_declaration_order_then_explicit_append():
    out = expand_bundles([P + "extra"], ["auth", "core"], DEFS)
    assert out == [P + "x", P + "y", P + "z", P + "a", P + "b", P + "c", P + "extra"]


def test_dedupe_preserves_first_occurrence_across_bundles_and_explicit():
    # 'a' appears via core, again via an only-ref, and again in explicit tools.
    refs = ["core", {"bundle": "core", "only": [P + "a"]}]
    out = expand_bundles([P + "a", P + "new"], refs, DEFS)
    assert out == [P + "a", P + "b", P + "c", P + "new"]


def test_empty_inputs_return_empty():
    assert expand_bundles(None, None, DEFS) == []
    assert expand_bundles([], [], DEFS) == []


def test_explicit_only_no_bundles():
    assert expand_bundles([P + "a", P + "a", P + "b"], [], DEFS) == [P + "a", P + "b"]


def test_bare_dict_with_no_filter_equals_whole_bundle():
    assert expand_bundles([], [{"bundle": "core"}], DEFS) == expand_bundles([], ["core"], DEFS)


def test_accepts_toolbundle_model_defs(tmp_path: Path):
    # expand_bundles must work against the typed ToolBundle objects the loader
    # produces, not only raw dicts.
    p = tmp_path / "agents.yaml"
    p.write_text(
        "version: 1\n"
        "tool_bundles:\n"
        "  core:\n"
        "    description: d\n"
        "    tools: [a.b.c, a.b.d]\n"
        "agents: {}\n"
    )
    m = load_manifest(p)
    assert expand_bundles([], ["core"], m.tool_bundles) == ["a.b.c", "a.b.d"]


# --------------------------------------------------------------------------- #
# BundleError paths (fail loud)
# --------------------------------------------------------------------------- #
def test_unknown_bundle_raises():
    with pytest.raises(BundleError, match="unknown bundle 'nope'"):
        expand_bundles([], ["nope"], DEFS)


def test_only_and_exclude_together_raises():
    ref = {"bundle": "core", "only": [P + "a"], "exclude": [P + "b"]}
    with pytest.raises(BundleError, match="mutually exclusive"):
        expand_bundles([], [ref], DEFS)


def test_only_names_non_member_raises():
    ref = {"bundle": "core", "only": [P + "zzz"]}
    with pytest.raises(BundleError, match="not in the bundle"):
        expand_bundles([], [ref], DEFS)


def test_exclude_names_non_member_raises():
    ref = {"bundle": "core", "exclude": [P + "zzz"]}
    with pytest.raises(BundleError, match="not in the bundle"):
        expand_bundles([], [ref], DEFS)


def test_mapping_without_bundle_key_raises():
    with pytest.raises(BundleError, match="must be a name or a mapping"):
        expand_bundles([], [{"only": [P + "a"]}], DEFS)


# --------------------------------------------------------------------------- #
# validate_bundles surfaces the offending agent
# --------------------------------------------------------------------------- #
def test_validate_bundles_names_the_agent(tmp_path: Path):
    p = tmp_path / "agents.yaml"
    p.write_text(
        "version: 1\n"
        "tool_bundles:\n"
        "  core:\n"
        "    tools: [a.b.c]\n"
        "agents:\n"
        "  demo:\n"
        "    package: forsch.agent_demo.agent\n"
        "    adk_name: demo_agent\n"
        "    model_code: forsch.agent_demo.agent.demo_model\n"
        "    bundles: [does_not_exist]\n"
    )
    m = load_manifest(p)
    with pytest.raises(BundleError, match="agent 'demo'.*unknown bundle"):
        validate_bundles(m)


def test_validate_bundles_passes_on_clean_real_manifest():
    m = load_manifest(_real_manifest_path())
    validate_bundles(m)  # must not raise


# --------------------------------------------------------------------------- #
# Golden safety contract — real manifest reproduces today's tool sets exactly.
# --------------------------------------------------------------------------- #
def _real_manifest_path() -> Path:
    # factory/tests/test_bundles.py -> parents[2] == workspace root
    return Path(__file__).resolve().parents[2] / "agent_specs" / "agents.yaml"


# The ordered tool lists each agent shipped with BEFORE the bundles refactor
# (captured from the committed agents.yaml at 2026-06-30). Expansion must equal
# these byte-for-byte (Tier 2: same set AND same order).
EXPECTED_TOOLS = {
    "stability": [
        P + "get_workspace_inventory", P + "get_git_state",
        P + "validate_agent_imports", P + "check_service_health",
        P + "execute_bash_command", P + "read_host_file", P + "write_host_file",
    ],
    "assistant": [],
    "brand": [
        P + "get_linkedin_brand_brief", P + "score_linkedin_draft",
        P + "stage_linkedin_profile_update", P + "get_personal_site_launch_brief",
        P + "audit_personal_site_launch", P + "get_linkedin_metric_dashboard",
        P + "list_linkedin_autonomous_actions",
    ],
    "build": [],
    "social": [
        P + "get_linkedin_brand_brief", P + "create_linkedin_draft",
        P + "list_linkedin_drafts", P + "score_linkedin_draft",
        P + "create_linkedin_go_live_plan", P + "record_linkedin_metric_snapshot",
        P + "get_linkedin_metric_dashboard", P + "run_linkedin_observability_cycle",
        P + "list_linkedin_autonomous_actions",
    ],
    "website": [
        P + "get_personal_site_launch_brief", P + "audit_personal_site_launch",
        P + "create_website_launch_task", P + "get_linkedin_brand_brief",
        P + "get_linkedin_metric_dashboard", P + "list_linkedin_autonomous_actions",
    ],
    "ops": [],
    "shelby": [P + "log_groceries", P + "get_grocery_log", P + "add_reminder"],
    "wow-guild": [
        P + "search_items", P + "get_item_details", P + "search_quests",
        P + "get_dungeon_bosses", P + "get_boss_loot", P + "search_npcs",
        P + "register_player", P + "get_player",
    ],
    # native agents — explicit tools, no bundles (must pass through untouched)
    "hubert": [
        "forsch.agent_hubert.tools.get_graph_overview",
        "forsch.agent_hubert.tools.manage_cluster",
        "forsch.agent_hubert.tools.get_factory_status",
        "forsch.agent_hubert.tools.route_to_agent_logic_specialist",
    ],
    "agent_logic_specialist": [
        "forsch.agent_agent_logic_specialist.tools.list_agents",
        "forsch.agent_agent_logic_specialist.tools.get_agent_config",
        "forsch.agent_agent_logic_specialist.tools.update_agent_config",
        "forsch.agent_agent_logic_specialist.tools.get_model_info",
        "forsch.agent_agent_logic_specialist.tools.get_adk_reference",
    ],
}


@pytest.mark.parametrize("agent_id", sorted(EXPECTED_TOOLS))
def test_real_manifest_expansion_is_byte_exact(agent_id):
    m = load_manifest(_real_manifest_path())
    spec = m.agents[agent_id]
    expanded = expand_bundles(spec.tools, spec.bundles, m.tool_bundles)
    assert expanded == EXPECTED_TOOLS[agent_id], (
        f"{agent_id}: expansion does not reproduce the pre-bundles ordered tool list"
    )


def test_real_manifest_covers_every_agent():
    # Guard against a new agent being added without a golden entry here.
    m = load_manifest(_real_manifest_path())
    assert set(m.agents) == set(EXPECTED_TOOLS)
