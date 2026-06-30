# LinkedIn Growth Team Go-Live Plan

Date: 2026-06-30
Branch: `codex/linkedin-brand-team`
Boundary: staged planning, local queues, scoring, metrics, and evals only. No
live LinkedIn or website side effects.

## Team

### `brand`

Owns Zach's public positioning: LinkedIn headline, About, Featured copy, proof
framing, website hero language, and brand consistency review.

Best-practice basis:

- LinkedIn requires accurate identity/profile information and real, authentic
  information. This is why `brand` must score and stage profile copy, not apply
  it live.
- LinkedIn says members should review AI-generated content before sharing. This
  is why every `brand` output returns a Zach-approval boundary.
- Prior Hubert notes converge on the headline: `Technical Support Leader |
  Practical AI for Support Ops | Building The Coordination Layer`.

Tools:

- `get_linkedin_brand_brief`
- `score_linkedin_draft`
- `stage_linkedin_profile_update`
- `get_personal_site_launch_brief`
- `audit_personal_site_launch`
- `get_linkedin_metric_dashboard`
- `list_linkedin_autonomous_actions`

Morning use:

1. Ask `brand` for the current positioning brief.
2. Ask it to score the headline/About copy.
3. Stage only the approved profile sections.
4. Zach manually edits LinkedIn from his own browser.

### `social`

Owns LinkedIn content and engagement preparation: post drafts, comment/reply
options, weekly batches, review queues, and the morning go-live checklist.

Best-practice basis:

- LinkedIn's User Agreement bars scraping and unauthorized automated actions
  such as creating, commenting on, liking, sharing, messaging, or driving
  inauthentic engagement with bots.
- LinkedIn's professional policies require truthful, non-misleading, professional
  expression.
- LinkedIn's article/newsletter guidance frames recurring long-form content as a
  way to build an engaged community, which fits The Coordination Layer better
  than one-off hype posts.

Tools:

- `get_linkedin_brand_brief`
- `create_linkedin_draft`
- `list_linkedin_drafts`
- `score_linkedin_draft`
- `create_linkedin_go_live_plan`
- `record_linkedin_metric_snapshot`
- `get_linkedin_metric_dashboard`
- `run_linkedin_observability_cycle`
- `list_linkedin_autonomous_actions`

Morning use:

1. Ask `social` for `create_linkedin_go_live_plan`.
2. Record a manual or approved-export metric snapshot if one is missing.
3. Ask for `get_linkedin_metric_dashboard`.
4. Ask it to stage one launch post, two support-ops field notes, and five comment
   drafts.
5. Review scores, flags, and local-only autonomous action receipts.
6. Zach manually posts/comments after final read.

### `website`

Owns the personal branded website launch surface: site plan, SEO basics,
accessibility checks, CTA clarity, metadata, proof page sequencing, and launch
tasks.

Best-practice basis:

- Google Search Central frames SEO as helping search engines understand content
  and helping users decide whether to visit. It also warns there are no secrets
  that automatically rank a site first.
- Google recommends checking whether a site is indexed and making sure people
  know about the site before over-optimizing.
- WCAG's quick reference emphasizes programmatically determinable information,
  structure, and relationships, so launch readiness includes semantic headings,
  clear labels, and accessible media/text alternatives.

Tools:

- `get_personal_site_launch_brief`
- `audit_personal_site_launch`
- `create_website_launch_task`
- `get_linkedin_brand_brief`
- `get_linkedin_metric_dashboard`
- `list_linkedin_autonomous_actions`

Morning use:

1. Ask `website` for the launch brief.
2. Check `get_linkedin_metric_dashboard` for link-click and site-session gaps.
3. Audit the home page copy and metadata.
4. Queue launch tasks for missing CTA, metadata, accessibility, proof, analytics,
   or newsletter wiring.
5. Deploy/DNS changes remain separate and approval-gated.

## LinkedIn Observability And Autonomy

The observability layer is intentionally local-first. It records metrics Zach
enters manually or imports from an approved export/API path, then lets the team
take only safe internal actions.

Tracked fields:

- Audience: `followers`, `connections`, `followers_gained_7d`.
- Profile discovery: `profile_views_7d`, `search_appearances_7d`.
- Content performance: `post_impressions_7d`, `post_reach_7d`,
  `post_count_7d`, `reactions_7d`, `comments_7d`, `reposts_7d`,
  `saves_7d`, `sends_7d`, `link_clicks_7d`.
- Owned-surface conversion: `website_sessions_7d`,
  `newsletter_subscribers`.

Safe autonomous actions:

- Queue a local content draft when cadence, impressions, or engagement drop.
- Queue a local profile CTA review when profile views do not become link clicks.
- Queue a local website CTA/tracking task when sessions do not become
  subscribers.
- Request a fresh metric snapshot when data is stale or missing.

The bots may run `run_linkedin_observability_cycle`, but that only writes local
draft/action/task records. It never scrapes, publishes, comments, messages,
accepts connections, edits profile fields, changes DNS, deploys a site, or
claims a public action happened.

## Morning Go-Live Sequence

1. Review the branch diff and eval results.
2. Ask `brand`: "Summarize the approved LinkedIn profile edits and stop rules."
3. Ask `social`: "Record this metric snapshot, show the dashboard, run the
   local-only observability cycle, and list the action receipts."
4. Ask `social`: "Give me the non-destructive LinkedIn go-live plan and staged
   draft queue."
5. Ask `website`: "Audit the personal-site launch surface and list only
   blockers."
6. Zach manually applies any LinkedIn/profile/site changes.
7. Record what went live, what stayed queued, and next review date.

## Stop Rules

- No agent posts, comments, DMs, accepts connections, edits the LinkedIn profile,
  scrapes LinkedIn, publishes a website, changes DNS, changes analytics, or
  claims a live action occurred.
- Metrics must come from Zach, an approved export, or an explicitly authorized
  API path. The local tools do not log in, scrape, or automate LinkedIn.
- Any $300k claim stays out of the headline/banner until the proof page exists.
- Employer/customer/private-family/pricing/hiring details require Zach review.
- If any eval fails, do not use the corresponding agent for go-live decisions
  until the failure is read and resolved.

## Evals

The evals are deterministic tool/rubric checks so they work without a live model
or LinkedIn credentials.

Run the growth evals:

```bash
PYTHONPATH=packages/adk-components/src python3 -m forsch.adk_components.testing.growth_eval --evalsets-root packages/live-agent-graph/evalsets --agent brand --evalset brand_profile_voice --json
PYTHONPATH=packages/adk-components/src python3 -m forsch.adk_components.testing.growth_eval --evalsets-root packages/live-agent-graph/evalsets --agent social --evalset linkedin_draft_safety --json
PYTHONPATH=packages/adk-components/src python3 -m forsch.adk_components.testing.growth_eval --evalsets-root packages/live-agent-graph/evalsets --agent social --evalset linkedin_observability_actions --json
PYTHONPATH=packages/adk-components/src python3 -m forsch.adk_components.testing.growth_eval --evalsets-root packages/live-agent-graph/evalsets --agent website --evalset website_launch_readiness --json
```

The live graph `/agent-eval-run` endpoint now shells this same runner and writes
`packages/live-agent-graph/.eval_runs/<agent>/last.json`.

## Sources

- LinkedIn User Agreement: https://www.linkedin.com/legal/user-agreement
- LinkedIn Professional Community Policies: https://www.linkedin.com/legal/professional-community-policies
- LinkedIn Organization Share Statistics: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics
- LinkedIn Social Metadata API: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/social-metadata-api
- LinkedIn Article and Newsletter Ads: https://business.linkedin.com/marketing-solutions/native-advertising/articles-and-newsletters
- Google Search Central SEO Starter Guide: https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- W3C WCAG 2.2 Quick Reference: https://www.w3.org/WAI/WCAG22/quickref/

Internal source notes used:

- `/Users/zacharyforsch/Dev/Hubert/workspace/reports/linkedin-go-live-20260528/linkedin-team-ops.md`
- `/Users/zacharyforsch/Dev/Hubert/workspace/reports/linkedin-go-live-20260528/linkedin-wording-pass-2026-06-05.md`
- `/Users/zacharyforsch/Dev/Hubert/workspace/reports/linkedin-go-live-20260528/about-rewrite-zach-voice.md`
- `/Users/zacharyforsch/Dev/Hubert/workspace/linkedin/linkedin-dry-run-20260601-091612.md`
