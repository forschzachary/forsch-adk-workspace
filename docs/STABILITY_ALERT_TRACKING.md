# Stability Alert Tracking

Purpose: record ADK workspace stability alerts in a small, reviewable format before any automated remediation exists.

## Safety Boundary

This tracker is documentation-only. It does not authorize service restarts, credential changes, destructive git commands, broad refactors, or production incident response. Every non-read-only action still needs the current autonomy level and a verified rollback note.

## Alert Record Schema

Use one table row per distinct alert. Update `last_seen`, `count`, `status`, and `last_action_taken` when the same alert recurs.

| Field | Meaning |
| --- | --- |
| `alert_id` | Stable identifier, e.g. `ADK-STAB-YYYYMMDD-001`. |
| `source` | Audit, test, bridge log, service health probe, runbook review, or simulated alert. |
| `severity` | `info`, `low`, `medium`, `high`, or `critical`. Start simulated alerts no higher than `medium` unless evidence says otherwise. |
| `first_seen` | ISO-8601 timestamp for first observation. |
| `last_seen` | ISO-8601 timestamp for most recent observation. |
| `count` | Number of observations for the same underlying issue. |
| `affected_component` | Repo, package, bridge route, service, or documentation area affected. |
| `suggested_owner_agent` | Stability, ops, build, assistant, brand, social, or human. |
| `status` | `new`, `triaged`, `monitoring`, `mitigated`, `resolved`, or `wont_fix`. |
| `last_action_taken` | Evidence-backed action already taken, not an intent. |
| `trend_note` | Whether the alert is new, recurring, improving, worsening, or likely a false positive. |

## Severity Guide

- `info`: observation only; no action needed.
- `low`: docs drift, missing directory note, or local-only warning with no runtime effect.
- `medium`: deterministic audit/test failure, bridge route drift, or import issue affecting local validation.
- `high`: repeated failure affecting a live ADK route or service health check.
- `critical`: confirmed production outage, data loss risk, destructive command attempt, or credential exposure.

## Current Alerts

| alert_id | source | severity | first_seen | last_seen | count | affected_component | suggested_owner_agent | status | last_action_taken | trend_note |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| ADK-STAB-20260620-001 | deterministic audit | medium | 2026-06-20T06:23:40+00:00 | 2026-06-20T06:35:58+00:00 | 3 | `components/scripts/stability_audit.py` run environment | stability | mitigated | Added regression for missing workspace and changed audit to report import failures instead of ambient successes. | improved; existing-workspace import isolation remains future hardening |
| ADK-STAB-20260620-002 | workspace inspection | low | 2026-06-20T06:23:40+00:00 | 2026-06-20T06:29:00+00:00 | 2 | `/opt/data/workspace/adk/bridge` | stability | resolved | Created `bridge/DIRECTORY.md` and verified expected bridge config, Runner, and safety notes. | documentation hygiene gap closed |
| ADK-STAB-20260620-003 | git status | medium | 2026-06-20T06:23:40+00:00 | 2026-06-20T06:27:51+00:00 | 2 | components and agent repos | human | monitoring | Recorded dirty files before evaluation changes. | pre-existing dirty state; treat as user-owned |
| ADK-STAB-20260620-004 | bridge route tests | low | 2026-06-20T06:31:41+00:00 | 2026-06-20T06:31:41+00:00 | 1 | `bridge` test environment | stability | new | Observed `Unknown config option: asyncio_mode` warning while route tests passed. | likely missing dev optional dependency in bridge venv |
| ADK-STAB-20260620-005 | manifest review | low | 2026-06-20T06:32:31+00:00 | 2026-06-20T06:32:31+00:00 | 1 | `agent_specs/agents.yaml` and bridge config | stability | triaged | Confirmed manifest lists only stability while bridge routes six agents; no autonomous config expansion taken. | design/config asymmetry needs supervised decision |
| ADK-STAB-20260620-006 | subagent inspection | low | 2026-06-20T06:34:47+00:00 | 2026-06-20T06:34:47+00:00 | 1 | `stability_tools.check_service_health` | stability | triaged | Identified arbitrary endpoint probe surface; no code change yet. | needs constrained endpoint design before higher autonomy |
| ADK-STAB-20260620-007 | simulated alert | medium | 2026-06-20T06:35:58+00:00 | 2026-06-20T06:35:58+00:00 | 1 | missing-workspace audit behavior | stability | mitigated | Added regression and deterministic audit behavior for missing workspaces; verified existing workspace audit still passes. | simulated alert resolved under supervision |

## Monitoring Candidates

These are safe candidates for deterministic monitoring before any autonomous remediation:

| monitor | signal | suggested threshold | safe first response |
| --- | --- | --- | --- |
| import audit | `summary.failed_agent_imports` from `scripts/stability_audit.py` | any non-empty list | classify affected agent and inspect package path before editing |
| dirty repos | `summary.dirty_repos` from `scripts/stability_audit.py` | new dirty path not already recorded | record status and require human review before touching dirty files |
| bridge route drift | compare `bridge/bridge_config.yaml`, route tests, and `agent_specs/agents.yaml` | route without manifest entry or import target | docs/config triage; no automatic expansion |
| service health | `services[].ok` from full audit | repeated failure across two checks | inspect local logs/config; no restart without explicit approval |
| directory notes | expected structural folders missing `DIRECTORY.md` | any missing required note | Level 1 docs-only fix after folder read |
| runbook staleness | runbook command fails while equivalent current command passes | one verified mismatch | patch docs with exact command and validation evidence |

## Update Rules

1. Record evidence before changing status.
2. Prefer grouping repeated observations into an existing alert over creating duplicates.
3. Mark simulated alerts clearly in `source` or `trend_note`.
4. Link every implemented fix to its validation command in the overnight worklog.
5. If an alert requires action above the current autonomy level, leave it `triaged` and record the requested permission instead of acting.
