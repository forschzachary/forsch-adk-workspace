"""Non-destructive LinkedIn, brand, and personal-site growth tools."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..patterns.jsonl_store import JSONLStore
from ..patterns.tool_decorator import tool


_VOICE_SIGNALS = (
    "support",
    "support ops",
    "technical support",
    "context",
    "handoff",
    "visibility",
    "coordination layer",
    "skill floor",
    "next move",
    "queue",
    "escalation",
    "qa",
    "product",
    "engineering",
    "hidden labor",
)

_HYPE_TERMS = (
    "10x",
    "revolutionary",
    "disrupt",
    "game-changing",
    "game changing",
    "autonomous everything",
    "replace your team",
    "replace agents",
    "fully autonomous support",
    "guaranteed",
    "secret hack",
)

_LIVE_ACTION_TERMS = (
    "auto-post",
    "autopost",
    "publish this tonight",
    "post this tonight",
    "send this dm",
    "send dm",
    "auto-accept",
    "accept connection",
    "like every",
    "scrape",
    "bot engagement",
)

_RISK_TERMS = (
    "$300k",
    "300k",
    "total expert",
    "hospitable",
    "investcloud",
    "customer name",
    "pricing",
    "salary",
    "contract",
    "confidential",
    "guarantee",
)

_METRIC_FIELDS = (
    "followers",
    "connections",
    "profile_views_7d",
    "search_appearances_7d",
    "post_impressions_7d",
    "post_reach_7d",
    "post_count_7d",
    "reactions_7d",
    "comments_7d",
    "reposts_7d",
    "saves_7d",
    "sends_7d",
    "link_clicks_7d",
    "followers_gained_7d",
    "website_sessions_7d",
    "newsletter_subscribers",
)

_METRIC_SOURCES = {
    "manual",
    "combined_manual",
    "linkedin_export",
    "approved_linkedin_api",
    "website_analytics",
    "newsletter_analytics",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "draft"


def _store(name: str) -> JSONLStore:
    return JSONLStore(name, basename_dir="growth")


def _contains_any(text: str, needles: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [needle for needle in needles if needle in lowered]


def _coerce_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_metric_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _metric_date_key(record: dict[str, Any]) -> str:
    return str(record.get("snapshot_date") or record.get("recorded_at") or "")


def _engagement_rate(record: dict[str, Any]) -> float:
    impressions = _coerce_int(record.get("post_impressions_7d"))
    engagements = (
        _coerce_int(record.get("reactions_7d"))
        + _coerce_int(record.get("comments_7d"))
        + _coerce_int(record.get("reposts_7d"))
        + _coerce_int(record.get("saves_7d"))
        + _coerce_int(record.get("sends_7d"))
    )
    if impressions <= 0:
        return 0.0
    return round(engagements / impressions, 4)


def _pct_delta(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous, 4)


def _dashboard_actions(
    latest: dict[str, Any] | None,
    previous: dict[str, Any] | None,
    *,
    max_actions: int,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    def add(action_type: str, owner: str, reason: str, tool_suggestion: str) -> None:
        if len(actions) >= max_actions:
            return
        actions.append(
            {
                "type": action_type,
                "owner": owner,
                "reason": reason,
                "tool_suggestion": tool_suggestion,
                "allowed_autonomy": "local_only",
                "public_side_effect": False,
                "manual_approval_required_before_public_action": True,
            }
        )

    if not latest:
        add(
            "request_metric_baseline",
            "social",
            "No LinkedIn metric snapshot has been recorded yet.",
            "record_linkedin_metric_snapshot",
        )
        return actions

    snapshot_date = _parse_metric_date(str(latest.get("snapshot_date") or ""))
    if snapshot_date:
        stale_days = (datetime.now(timezone.utc).date() - snapshot_date).days
        if stale_days > 7:
            add(
                "request_fresh_metrics",
                "social",
                f"Latest metric snapshot is {stale_days} days old.",
                "record_linkedin_metric_snapshot",
            )

    if _coerce_int(latest.get("post_count_7d")) == 0:
        add(
            "draft_weekly_content_batch",
            "social",
            "No posts were logged in the latest 7-day snapshot.",
            "create_linkedin_draft",
        )

    current_impressions = _coerce_int(latest.get("post_impressions_7d"))
    previous_impressions = _coerce_int(previous.get("post_impressions_7d")) if previous else 0
    impressions_pct = _pct_delta(current_impressions, previous_impressions)
    if impressions_pct is not None and impressions_pct <= -0.2:
        add(
            "draft_impressions_recovery_post",
            "social",
            "7-day post impressions are down at least 20% from the prior snapshot.",
            "create_linkedin_draft",
        )

    engagement_rate = _engagement_rate(latest)
    if current_impressions >= 100 and engagement_rate < 0.02:
        add(
            "draft_conversation_prompt",
            "social",
            "7-day engagement rate is under 2% on a measurable impression base.",
            "create_linkedin_draft",
        )

    if _coerce_int(latest.get("profile_views_7d")) > 0 and _coerce_int(latest.get("link_clicks_7d")) == 0:
        add(
            "stage_profile_cta_review",
            "brand",
            "Profile views are present but no link clicks were logged.",
            "stage_linkedin_profile_update",
        )

    if _coerce_int(latest.get("website_sessions_7d")) > 0 and _coerce_int(latest.get("newsletter_subscribers")) == 0:
        add(
            "create_website_cta_task",
            "website",
            "Website sessions are present but no newsletter subscribers were logged.",
            "create_website_launch_task",
        )

    if not actions:
        add(
            "schedule_weekly_growth_review",
            "social",
            "Metrics are healthy enough for a weekly review rather than an urgent fix.",
            "get_linkedin_metric_dashboard",
        )
    return actions


def _execute_safe_growth_action(action: dict[str, Any]) -> dict[str, Any] | None:
    action_type = action.get("type")
    if action_type == "draft_weekly_content_batch":
        return create_linkedin_draft(
            content_type="post",
            topic="weekly support-ops field note",
            draft_text=(
                "Support ops gets easier when the queue has visible context, a clear owner, "
                "and an obvious next move. This week I am looking for the handoff moments "
                "where the work slows down quietly instead of getting escalated cleanly. "
                "What is one signal your support team wishes it saw sooner?"
            ),
            goal="restart a useful weekly LinkedIn cadence",
            source_notes="Autonomous local draft from LinkedIn metric observability; Zach must approve and publish manually.",
        )
    if action_type == "draft_impressions_recovery_post":
        return create_linkedin_draft(
            content_type="post",
            topic="impressions recovery support-ops question",
            draft_text=(
                "When a support post falls flat, I try to make the next one more specific: "
                "one queue symptom, one handoff failure, one practical next move. "
                "For support leaders, where does escalation context most often disappear?"
            ),
            goal="recover reach with a more specific support-ops prompt",
            source_notes="Autonomous local draft from LinkedIn metric observability; Zach must approve and publish manually.",
        )
    if action_type == "draft_conversation_prompt":
        return create_linkedin_draft(
            content_type="post",
            topic="low-engagement conversation prompt",
            draft_text=(
                "A useful support-ops question: if you could add one field to every escalation, "
                "would it be customer context, product area, owner, severity, or next move? "
                "I keep coming back to next move because it turns visibility into action."
            ),
            goal="increase replies with a focused support-ops question",
            source_notes="Autonomous local draft from LinkedIn metric observability; Zach must approve and publish manually.",
        )
    if action_type == "stage_profile_cta_review":
        return stage_linkedin_profile_update(
            section="featured",
            proposed_copy="The Coordination Layer: support-ops field notes on handoffs, escalation context, QA visibility, and practical AI workflows.",
            rationale="Profile views are not turning into link clicks; review the Featured CTA language.",
        )
    if action_type == "create_website_cta_task":
        return create_website_launch_task(
            area="conversion",
            title="Review newsletter CTA from LinkedIn traffic",
            notes="Website sessions are present but subscribers are flat. Check CTA copy, placement, analytics event wiring, and form success state.",
            owner="website",
        )
    return None


def _receipt(*, ok: bool, action: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "synced": False,
        "published": False,
        "manual_approval_required": True,
        "claim": "staged locally for Zach review; not posted, sent, scraped, or published",
        "record": record,
        "receipt": {
            "saved_at": _now(),
            "storage": "FORSCH_PATTERNS_DATA_DIR/growth or FORSCH_ADK_WORKSPACE/data/growth",
        },
    }


@tool(
    family="growth",
    safety="read_only",
    keywords=["linkedin", "brand", "positioning", "profile", "voice", "brief"],
)
def get_linkedin_brand_brief() -> dict[str, Any]:
    """Return Zach's LinkedIn positioning brief, voice rules, and safety boundaries."""
    return {
        "positioning": {
            "headline": "Technical Support Leader | Practical AI for Support Ops | Building The Coordination Layer",
            "one_liner": "Technical support leadership plus practical AI for the messy work around the queue.",
            "owned_surfaces": [
                "The Coordination Layer newsletter",
                "Forsch Frontiers",
                "personal website / support-ops workflow audit page",
            ],
            "voice": [
                "plain, lived-experience, support-floor specific",
                "signal over noise, skill floor up, next move clear",
                "practical AI as visibility and handoff support, not AI hype",
            ],
        },
        "content_pillars": [
            "support operations visibility",
            "escalation context and handoff quality",
            "QA, coaching, and manager follow-through",
            "practical AI workflows with human approval",
            "support signal flowing to Product and Engineering",
            "personal builder story: support lead by day, AI systems builder by night",
        ],
        "guardrails": [
            "No live LinkedIn writes from agents: no posts, comments, DMs, connection actions, profile edits, or scraping.",
            "All drafts and profile edits are staged locally and need Zach's final signature.",
            "Do not lead with the $300k claim until a proof page or case study exists.",
            "Do not disclose employer, customer, private family, pricing, hiring, or confidential details.",
            "AI should be framed as judgment support and context visibility, not replacement of support people.",
        ],
        "go_live_priorities": [
            "Approve headline.",
            "Approve About copy in Zach voice.",
            "Stage Featured link copy for newsletter and website.",
            "Prepare first 3 LinkedIn posts and 5 comment/reply drafts.",
            "Record a baseline LinkedIn metric snapshot before the first autonomous growth review.",
            "Launch personal site with newsletter CTA, workflow-audit CTA, metadata, analytics, and accessibility checks.",
        ],
        "source_notes": [
            "Hubert LinkedIn go-live notes from 2026-05-28 and 2026-06-05.",
            "LinkedIn policy research: User Agreement, Professional Community Policies, Articles and Newsletters guidance, and Microsoft Learn LinkedIn Marketing API metric fields.",
            "Website launch research: Google Search Central SEO starter guide and W3C WCAG quick reference.",
        ],
    }


@tool(
    family="growth",
    safety="read_only",
    keywords=["linkedin", "score", "draft", "rubric", "brand safety"],
)
def score_linkedin_draft(draft_text: str, content_type: str = "post") -> dict[str, Any]:
    """Score a LinkedIn/profile draft against voice, proof, safety, and approval rules."""
    text = (draft_text or "").strip()
    lowered = text.lower()
    flags: list[str] = []
    positives: list[str] = []
    score = 1.0

    if not text:
        return {
            "ok": False,
            "pass": False,
            "score": 0.0,
            "flags": ["empty draft"],
            "positives": [],
            "manual_approval_required": True,
            "content_type": content_type,
        }

    voice_hits = _contains_any(text, _VOICE_SIGNALS)
    if len(voice_hits) >= 3:
        positives.append("has support-ops voice signals")
    elif len(voice_hits) >= 1:
        score -= 0.08
        flags.append("could use more Zach-specific support-ops language")
    else:
        score -= 0.18
        flags.append("missing Zach-specific support-ops language")

    hype_hits = _contains_any(text, _HYPE_TERMS)
    if hype_hits:
        score -= min(0.25, 0.06 * len(hype_hits))
        flags.append("contains AI or marketing hype: " + ", ".join(hype_hits))

    live_hits = _contains_any(text, _LIVE_ACTION_TERMS)
    if live_hits:
        score -= 0.35
        flags.append("contains live-action or automation language: " + ", ".join(live_hits))

    risk_hits = _contains_any(text, _RISK_TERMS)
    if risk_hits:
        score -= min(0.22, 0.05 * len(risk_hits))
        flags.append("needs proof or red-gate review: " + ", ".join(risk_hits))

    if "$300k" in lowered or "300k" in lowered:
        flags.append("do not lead with the $300k claim until proof page exists")

    word_count = len(re.findall(r"\b\w+\b", text))
    if content_type in {"post", "comment_reply"}:
        if word_count < 20:
            score -= 0.08
            flags.append("too thin to carry a clear point")
        elif word_count <= 180:
            positives.append("compact enough for feed scanning")
        elif word_count > 320:
            score -= 0.08
            flags.append("long post; check that every paragraph earns its keep")

    if "?" in text:
        positives.append("invites conversation")

    pass_threshold = 0.72
    final_score = max(0.0, round(score, 2))
    hard_fail = bool(live_hits) or "$300k" in lowered or "300k" in lowered or "guarantee" in lowered
    return {
        "ok": True,
        "pass": final_score >= pass_threshold and not hard_fail,
        "score": final_score,
        "threshold": pass_threshold,
        "flags": flags,
        "positives": positives,
        "manual_approval_required": True,
        "content_type": content_type,
        "word_count": word_count,
        "policy": "staged-only; Zach must publish manually",
    }


@tool(
    family="growth",
    safety="local_write",
    keywords=["linkedin", "draft", "queue", "post", "comment", "reply"],
)
def create_linkedin_draft(
    content_type: str,
    topic: str,
    draft_text: str,
    audience: str = "",
    goal: str = "",
    source_notes: str = "",
    due_date: str = "",
) -> dict[str, Any]:
    """Stage a LinkedIn draft locally. This never posts, sends, scrapes, or edits LinkedIn."""
    score = score_linkedin_draft(draft_text, content_type)
    record = {
        "id": f"{_now()}-{_slug(topic)}",
        "created_at": _now(),
        "status": "needs_zach_approval",
        "content_type": content_type,
        "topic": topic,
        "audience": audience,
        "goal": goal,
        "source_notes": source_notes,
        "due_date": due_date,
        "draft_text": draft_text,
        "score": score,
        "publication_boundary": "manual_only",
    }
    _store("linkedin_drafts.jsonl").append([record])
    return _receipt(ok=True, action="stage_linkedin_draft", record=record)


@tool(
    family="growth",
    safety="read_only",
    keywords=["linkedin", "drafts", "queue", "review"],
)
def list_linkedin_drafts(status: str = "", limit: int = 10) -> dict[str, Any]:
    """List locally staged LinkedIn drafts. No LinkedIn access is performed."""
    records = _store("linkedin_drafts.jsonl").read()
    if status:
        records = [r for r in records if r.get("status") == status]
    # Clamp to [0, 50]. n==0 must return [] — records[-0:] would slice to ALL, and
    # the old max(1, ...) floored limit=0 up to 1 (returned the last draft).
    n = min(_coerce_int(limit), 50)
    return {
        "ok": True,
        "count": len(records),
        "drafts": records[-n:] if n else [],
        "publication_boundary": "manual_only",
    }


@tool(
    family="growth",
    safety="local_write",
    keywords=["linkedin", "profile", "headline", "about", "featured", "stage"],
)
def stage_linkedin_profile_update(
    section: str,
    proposed_copy: str,
    rationale: str = "",
) -> dict[str, Any]:
    """Stage a LinkedIn profile update locally for Zach approval. This never edits LinkedIn."""
    score = score_linkedin_draft(proposed_copy, f"profile_{section}")
    record = {
        "id": f"{_now()}-{_slug(section)}",
        "created_at": _now(),
        "status": "needs_zach_approval",
        "section": section,
        "proposed_copy": proposed_copy,
        "rationale": rationale,
        "score": score,
        "publication_boundary": "manual_only",
    }
    _store("linkedin_profile_updates.jsonl").append([record])
    return _receipt(ok=True, action="stage_linkedin_profile_update", record=record)


@tool(
    family="growth",
    safety="read_only",
    keywords=["linkedin", "go-live", "checklist", "morning", "launch"],
)
def create_linkedin_go_live_plan() -> dict[str, Any]:
    """Return a morning go-live plan with non-destructive LinkedIn actions only."""
    return {
        "ok": True,
        "mode": "manual_go_live",
        "stop_rules": [
            "Stop before any LinkedIn publish, profile save, DM, comment, connection action, or scrape.",
            "Stop if a draft makes an employer/customer claim without source proof.",
            "Stop if the website CTA, newsletter URL, or booking route is not live.",
        ],
        "morning_sequence": [
            "Review staged headline and About copy.",
            "Open LinkedIn manually and apply approved profile edits.",
            "Add Featured items only after the website/newsletter URLs resolve.",
            "Pick 1 launch post, 2 supporting posts, and 5 comment drafts from the local queue.",
            "Publish manually from Zach's browser after final read.",
            "Log what went live and queue the next weekly review.",
        ],
        "first_week_cadence": [
            "1 profile launch post",
            "2 support-ops field-note posts",
            "5 thoughtful comments on relevant support/CX/AI posts, all Zach-approved",
            "1 newsletter or website CTA reminder only after value has been delivered",
        ],
        "manual_actions_for_zach": [
            "Approve final headline.",
            "Approve About section.",
            "Confirm website/newsletter CTA URLs.",
            "Manually publish or edit in LinkedIn.",
        ],
        "observability_setup": [
            "Record a manual or approved-export metric baseline with record_linkedin_metric_snapshot.",
            "Run get_linkedin_metric_dashboard before picking the next post batch.",
            "Run run_linkedin_observability_cycle only for local drafts, profile-review records, and website tasks.",
        ],
    }


@tool(
    family="growth",
    safety="local_write",
    keywords=["linkedin", "metrics", "observability", "snapshot", "analytics", "baseline"],
)
def record_linkedin_metric_snapshot(
    snapshot_date: str = "",
    source: str = "manual",
    followers: int = 0,
    connections: int = 0,
    profile_views_7d: int = 0,
    search_appearances_7d: int = 0,
    post_impressions_7d: int = 0,
    post_reach_7d: int = 0,
    post_count_7d: int = 0,
    reactions_7d: int = 0,
    comments_7d: int = 0,
    reposts_7d: int = 0,
    saves_7d: int = 0,
    sends_7d: int = 0,
    link_clicks_7d: int = 0,
    followers_gained_7d: int = 0,
    website_sessions_7d: int = 0,
    newsletter_subscribers: int = 0,
    notes: str = "",
) -> dict[str, Any]:
    """Record a manual or approved-export LinkedIn metric snapshot locally."""
    normalized_source = (source or "manual").strip().lower().replace(" ", "_")
    quality_flags: list[str] = []
    if normalized_source not in _METRIC_SOURCES:
        quality_flags.append(f"unknown source {source!r}; treated as manual")
        normalized_source = "manual"

    parsed_date = _parse_metric_date(snapshot_date)
    record = {
        "id": f"{_now()}-{_slug(snapshot_date or _today())}",
        "recorded_at": _now(),
        "snapshot_date": parsed_date.isoformat() if parsed_date else _today(),
        "source": normalized_source,
        "quality_flags": quality_flags,
        "collection_boundary": "manual_or_approved_export_only; no scraping, browser automation, or live LinkedIn writes",
        "notes": notes,
    }
    for field in _METRIC_FIELDS:
        record[field] = _coerce_int(locals().get(field))
    record["engagements_7d"] = (
        record["reactions_7d"]
        + record["comments_7d"]
        + record["reposts_7d"]
        + record["saves_7d"]
        + record["sends_7d"]
    )
    record["engagement_rate_7d"] = _engagement_rate(record)
    _store("linkedin_metric_snapshots.jsonl").append([record])
    return _receipt(ok=True, action="record_linkedin_metric_snapshot", record=record)


@tool(
    family="growth",
    safety="read_only",
    keywords=["linkedin", "metrics", "dashboard", "observability", "analytics", "trend"],
)
def get_linkedin_metric_dashboard(window_days: int = 30) -> dict[str, Any]:
    """Summarize locally recorded LinkedIn metrics and recommend safe local actions."""
    records = sorted(_store("linkedin_metric_snapshots.jsonl").read(), key=_metric_date_key)
    if not records:
        return {
            "ok": True,
            "has_baseline": False,
            "status": "needs_metric_baseline",
            "window_days": max(1, min(_coerce_int(window_days), 365)),
            "latest": None,
            "deltas": {},
            "insights": ["No metric snapshot has been recorded yet."],
            "recommended_autonomous_actions": _dashboard_actions(None, None, max_actions=5),
            "autonomy_boundary": "local queue actions only; no LinkedIn scrape, publish, DM, comment, connection action, or profile edit",
        }

    days = max(1, min(_coerce_int(window_days) or 30, 365))
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    windowed = [
        record for record in records
        if (_parse_metric_date(str(record.get("snapshot_date") or "")) or cutoff) >= cutoff
    ]
    if not windowed:
        windowed = records[-1:]

    latest = windowed[-1]
    previous = windowed[-2] if len(windowed) > 1 else (records[-2] if len(records) > 1 else None)
    deltas = {}
    if previous:
        for field in _METRIC_FIELDS + ("engagements_7d",):
            deltas[field] = _coerce_int(latest.get(field)) - _coerce_int(previous.get(field))
        deltas["engagement_rate_7d"] = round(_engagement_rate(latest) - _engagement_rate(previous), 4)
        deltas["post_impressions_7d_pct"] = _pct_delta(
            _coerce_int(latest.get("post_impressions_7d")),
            _coerce_int(previous.get("post_impressions_7d")),
        )

    insights: list[str] = []
    if _coerce_int(latest.get("post_count_7d")) == 0:
        insights.append("No posts were logged in the latest 7-day snapshot.")
    if deltas.get("post_impressions_7d_pct") is not None and deltas["post_impressions_7d_pct"] <= -0.2:
        insights.append("Post impressions are down at least 20% from the prior snapshot.")
    if _coerce_int(latest.get("profile_views_7d")) > 0 and _coerce_int(latest.get("link_clicks_7d")) == 0:
        insights.append("Profile views are not turning into logged link clicks.")
    if _coerce_int(latest.get("post_impressions_7d")) >= 100 and _engagement_rate(latest) < 0.02:
        insights.append("Engagement rate is below 2% on a measurable impression base.")
    if not insights:
        insights.append("No urgent growth risk detected from the latest local metrics.")

    latest_preview = {field: latest.get(field) for field in _METRIC_FIELDS}
    latest_preview.update(
        {
            "snapshot_date": latest.get("snapshot_date"),
            "source": latest.get("source"),
            "engagements_7d": latest.get("engagements_7d", 0),
            "engagement_rate_7d": _engagement_rate(latest),
        }
    )
    return {
        "ok": True,
        "has_baseline": True,
        "status": "ready",
        "window_days": days,
        "snapshot_count": len(windowed),
        "latest": latest_preview,
        "deltas": deltas,
        "insights": insights,
        "recommended_autonomous_actions": _dashboard_actions(latest, previous, max_actions=5),
        "metric_sources_supported": sorted(_METRIC_SOURCES),
        "autonomy_boundary": "local queue actions only; no LinkedIn scrape, publish, DM, comment, connection action, or profile edit",
    }


@tool(
    family="growth",
    safety="local_write",
    keywords=["linkedin", "metrics", "observability", "autonomous", "actions", "queue"],
)
def run_linkedin_observability_cycle(
    window_days: int = 30,
    max_actions: int = 5,
    create_artifacts: bool = True,
) -> dict[str, Any]:
    """Queue safe local growth actions from recorded metrics. This never touches LinkedIn."""
    dashboard = get_linkedin_metric_dashboard(window_days)
    recommended = dashboard.get("recommended_autonomous_actions", [])[: max(1, min(_coerce_int(max_actions) or 5, 10))]
    existing = _store("linkedin_autonomous_actions.jsonl").read()
    recent_keys = {
        (item.get("type"), item.get("reason"))
        for item in existing[-50:]
        if item.get("status") in {"queued", "artifact_created"}
    }
    action_records: list[dict[str, Any]] = []
    for action in recommended:
        key = (action.get("type"), action.get("reason"))
        if key in recent_keys:
            continue
        record = {
            "id": f"{_now()}-{_slug(str(action.get('type') or 'action'))}",
            "created_at": _now(),
            "status": "queued",
            "execution_boundary": "local_only",
            "public_side_effect": False,
            "manual_approval_required_before_public_action": True,
            **action,
        }
        if create_artifacts:
            artifact = _execute_safe_growth_action(action)
            if artifact:
                record["status"] = "artifact_created"
                record["artifact_receipt"] = artifact
        action_records.append(record)

    if action_records:
        _store("linkedin_autonomous_actions.jsonl").append(action_records)

    cycle_record = {
        "id": f"{_now()}-observability-cycle",
        "created_at": _now(),
        "status": "queued_actions" if action_records else "no_new_actions",
        "dashboard_status": dashboard.get("status"),
        "dashboard_insights": dashboard.get("insights", []),
        "actions": action_records,
        "publication_boundary": "manual_only",
        "autonomy_boundary": "agents may draft, score, queue, and create local tasks; Zach publishes or edits public surfaces manually",
    }
    return _receipt(ok=True, action="run_linkedin_observability_cycle", record=cycle_record)


@tool(
    family="growth",
    safety="read_only",
    keywords=["linkedin", "metrics", "observability", "autonomous", "actions", "queue"],
)
def list_linkedin_autonomous_actions(status: str = "", limit: int = 20) -> dict[str, Any]:
    """List locally queued autonomous growth actions. No LinkedIn access is performed."""
    records = _store("linkedin_autonomous_actions.jsonl").read()
    if status:
        records = [record for record in records if record.get("status") == status]
    return {
        "ok": True,
        "count": len(records),
        "actions": records[-max(1, min(_coerce_int(limit) or 20, 100)):],
        "autonomy_boundary": "local queue actions only; no LinkedIn scrape, publish, DM, comment, connection action, or profile edit",
    }


@tool(
    family="growth",
    safety="read_only",
    keywords=["website", "launch", "personal site", "seo", "accessibility", "brief"],
)
def get_personal_site_launch_brief() -> dict[str, Any]:
    """Return the personal branded website launch brief and source-backed checklist."""
    return {
        "ok": True,
        "positioning": "Personal site should convert LinkedIn curiosity into a clear next step: newsletter subscribe, workflow-audit interest, or compare-notes contact.",
        "pages": [
            "Home: Technical support leadership plus practical AI for support ops.",
            "The Coordination Layer: newsletter archive and subscribe CTA.",
            "Workflow audit: low-pressure explanation of what Zach can help inspect.",
            "Proof/case studies: hold the $300k claim until proof is written.",
            "About: Zach voice, support-floor story, builder credibility.",
        ],
        "launch_checklist": [
            "One primary CTA per page.",
            "Unique title and meta description on each page.",
            "Open Graph image and copy aligned with LinkedIn headline.",
            "Newsletter CTA works.",
            "Contact or booking route works.",
            "Accessible headings, link labels, form labels, and image alt text.",
            "Search Console ready after domain is final.",
            "Analytics installed without blocking page load.",
            "No unsupported employer/customer claims.",
        ],
        "source_notes": [
            "Google Search Central: metadata, Search Console, helpful unique content, and promotion.",
            "W3C WCAG 2.2 quick reference: text alternatives, semantic structure, meaningful sequence.",
            "LinkedIn source research: profile truthfulness and manual review before sharing AI-generated content.",
        ],
    }


@tool(
    family="growth",
    safety="read_only",
    keywords=["website", "audit", "seo", "cta", "accessibility", "launch"],
)
def audit_personal_site_launch(
    page_title: str,
    meta_description: str,
    hero_copy: str,
    primary_cta: str,
    newsletter_cta: str = "",
    proof_items: str = "",
) -> dict[str, Any]:
    """Score a personal website page for launch readiness."""
    flags: list[str] = []
    positives: list[str] = []
    score = 1.0

    if not page_title.strip():
        score -= 0.18
        flags.append("missing page title")
    elif len(page_title) > 70:
        score -= 0.06
        flags.append("page title may be too long for scanning")
    else:
        positives.append("page title present")

    md = meta_description.strip()
    if not md:
        score -= 0.18
        flags.append("missing meta description")
    elif 50 <= len(md) <= 180:
        positives.append("meta description is concise")
    else:
        score -= 0.06
        flags.append("meta description should be a concise one- or two-sentence summary")

    combined = "\n".join([page_title, meta_description, hero_copy, primary_cta, newsletter_cta, proof_items])
    if not _contains_any(combined, _VOICE_SIGNALS):
        score -= 0.14
        flags.append("missing support-ops positioning language")
    else:
        positives.append("support-ops positioning present")

    if not primary_cta.strip():
        score -= 0.16
        flags.append("missing primary CTA")
    else:
        positives.append("primary CTA present")

    if "300k" in combined.lower() and not proof_items.strip():
        score -= 0.2
        flags.append("300k claim needs proof before launch")

    hype_hits = _contains_any(combined, _HYPE_TERMS)
    if hype_hits:
        score -= min(0.18, 0.05 * len(hype_hits))
        flags.append("contains hype language: " + ", ".join(hype_hits))

    final_score = max(0.0, round(score, 2))
    hard_fail = "300k" in combined.lower() and not proof_items.strip()
    return {
        "ok": True,
        "pass": final_score >= 0.76 and not hard_fail,
        "score": final_score,
        "threshold": 0.76,
        "flags": flags,
        "positives": positives,
        "manual_approval_required": True,
    }


@tool(
    family="growth",
    safety="local_write",
    keywords=["website", "task", "launch", "queue", "go-live"],
)
def create_website_launch_task(
    area: str,
    title: str,
    notes: str,
    owner: str = "website",
    due_date: str = "",
) -> dict[str, Any]:
    """Stage a website launch task locally. This never deploys or changes DNS."""
    record = {
        "id": f"{_now()}-{_slug(title)}",
        "created_at": _now(),
        "status": "queued",
        "area": area,
        "title": title,
        "notes": notes,
        "owner": owner,
        "due_date": due_date,
        "deployment_boundary": "manual_or_separate_approved_deploy",
    }
    _store("website_launch_tasks.jsonl").append([record])
    return _receipt(ok=True, action="create_website_launch_task", record=record)
