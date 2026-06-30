from __future__ import annotations

import json

from forsch.adk_components.testing.growth_eval import run_evalset
from forsch.adk_components.tools import (
    audit_personal_site_launch,
    create_linkedin_draft,
    create_website_launch_task,
    get_linkedin_brand_brief,
    get_linkedin_metric_dashboard,
    list_linkedin_autonomous_actions,
    record_linkedin_metric_snapshot,
    run_linkedin_observability_cycle,
    score_linkedin_draft,
    stage_linkedin_profile_update,
)


def test_brand_brief_has_manual_linkedin_boundary():
    brief = get_linkedin_brand_brief()
    guardrails = "\n".join(brief["guardrails"])
    assert "No live LinkedIn writes" in guardrails
    assert "Technical Support Leader" in brief["positioning"]["headline"]


def test_linkedin_draft_score_flags_live_action_language():
    result = score_linkedin_draft(
        "Auto-post this tonight and guarantee leads with fully autonomous support.",
        "post",
    )
    assert result["pass"] is False
    assert result["manual_approval_required"] is True
    assert any("live-action" in flag for flag in result["flags"])


def test_create_linkedin_draft_is_staged_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_PATTERNS_DATA_DIR", str(tmp_path))
    result = create_linkedin_draft(
        content_type="post",
        topic="support handoffs",
        draft_text="Support handoffs fail when context, owner, and next move are invisible.",
    )
    assert result["ok"] is True
    assert result["synced"] is False
    assert result["published"] is False
    assert result["manual_approval_required"] is True


def test_stage_profile_update_is_staged_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_PATTERNS_DATA_DIR", str(tmp_path))
    result = stage_linkedin_profile_update(
        "headline",
        "Technical Support Leader | Practical AI for Support Ops | Building The Coordination Layer",
    )
    assert result["ok"] is True
    assert result["record"]["section"] == "headline"
    assert result["record"]["publication_boundary"] == "manual_only"


def test_website_launch_audit_blocks_unproved_300k_claim():
    result = audit_personal_site_launch(
        page_title="Practical AI for Support Ops",
        meta_description="Technical support leadership and practical AI workflows for support operations.",
        hero_copy="Find $300k in hidden support labor with practical AI.",
        primary_cta="Subscribe to The Coordination Layer",
    )
    assert result["pass"] is False
    assert any("300k" in flag for flag in result["flags"])


def test_website_launch_audit_allows_300k_with_proof():
    result = audit_personal_site_launch(
        page_title="Practical AI for Support Ops",
        meta_description="Technical support leadership and practical AI workflows for support operations.",
        hero_copy="A proof-backed case study about finding $300k in hidden support handoff drag.",
        primary_cta="Read the support-ops case study",
        proof_items="Approved case-study page with source notes, calculation method, and Zach review.",
    )
    assert result["pass"] is True
    assert not any("300k claim needs proof" in flag for flag in result["flags"])


def test_create_website_task_is_queued_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_PATTERNS_DATA_DIR", str(tmp_path))
    result = create_website_launch_task(
        area="seo",
        title="Add page metadata",
        notes="Unique title and meta description for the homepage.",
    )
    assert result["ok"] is True
    assert result["synced"] is False
    assert result["record"]["deployment_boundary"] == "manual_or_separate_approved_deploy"


def test_linkedin_metric_dashboard_recommends_safe_local_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_PATTERNS_DATA_DIR", str(tmp_path))
    record_linkedin_metric_snapshot(
        snapshot_date="2026-06-23",
        source="manual",
        followers=500,
        profile_views_7d=20,
        post_impressions_7d=1000,
        post_count_7d=3,
        reactions_7d=35,
        comments_7d=6,
        reposts_7d=2,
        link_clicks_7d=5,
        website_sessions_7d=4,
        newsletter_subscribers=1,
    )
    record_linkedin_metric_snapshot(
        snapshot_date="2026-06-30",
        source="linkedin_export",
        followers=510,
        profile_views_7d=40,
        post_impressions_7d=500,
        post_count_7d=1,
        reactions_7d=4,
        comments_7d=1,
        reposts_7d=0,
        link_clicks_7d=0,
        website_sessions_7d=7,
        newsletter_subscribers=0,
    )

    dashboard = get_linkedin_metric_dashboard(window_days=30)
    assert dashboard["ok"] is True
    assert dashboard["has_baseline"] is True
    assert dashboard["latest"]["engagement_rate_7d"] == 0.01
    assert dashboard["deltas"]["post_impressions_7d"] == -500
    action_types = {action["type"] for action in dashboard["recommended_autonomous_actions"]}
    assert "draft_impressions_recovery_post" in action_types
    assert "stage_profile_cta_review" in action_types
    assert all(action["public_side_effect"] is False for action in dashboard["recommended_autonomous_actions"])


def test_observability_cycle_creates_local_only_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_PATTERNS_DATA_DIR", str(tmp_path))
    record_linkedin_metric_snapshot(
        snapshot_date="2026-06-30",
        source="manual",
        followers=510,
        profile_views_7d=40,
        post_impressions_7d=500,
        post_count_7d=1,
        reactions_7d=4,
        comments_7d=1,
        link_clicks_7d=0,
        website_sessions_7d=7,
        newsletter_subscribers=0,
    )

    cycle = run_linkedin_observability_cycle(max_actions=3)
    assert cycle["ok"] is True
    assert cycle["published"] is False
    assert cycle["record"]["publication_boundary"] == "manual_only"
    assert cycle["record"]["actions"]
    assert all(action["public_side_effect"] is False for action in cycle["record"]["actions"])

    queued = list_linkedin_autonomous_actions()
    assert queued["ok"] is True
    assert queued["count"] == len(cycle["record"]["actions"])


def test_growth_eval_runner_executes_tool_assertions(tmp_path):
    evalset = {
        "agent_id": "social",
        "eval_cases": [
            {
                "eval_case_id": "safe_draft_scores",
                "tool_call": {
                    "name": "score_linkedin_draft",
                    "args": {
                        "draft_text": "Support ops gets easier when escalation context and the next move are visible.",
                        "content_type": "post",
                    },
                },
                "assertions": [
                    {"path": "ok", "equals": True},
                    {"path": "manual_approval_required", "equals": True},
                    {"path": "score", "min": 0.7},
                ],
            }
        ],
    }
    path = tmp_path / "social.evalset.json"
    path.write_text(json.dumps(evalset))
    result = run_evalset(path)
    assert result["ok"] is True
    assert result["passed_cases"] == 1
