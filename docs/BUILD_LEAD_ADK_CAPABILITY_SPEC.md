# Build Lead ADK Capability Spec

Status: draft for review  
Owner: Build Lead ADK agent  
Source repo target: `forsch-agent-build` plus shared tools in `forsch-adk-components`  
Last updated: 2026-06-20

## 1. Purpose

The Build Lead should become a real ADK-native engineering agent, not a thin clone of the old Hermes `build-lead` profile.

The old Hermes profile is useful evidence for role shape and capability needs, but it is the wrong runtime layer to copy. The ADK Build Lead should use curated Python tool shims, shared component clients, and explicit safety contracts rather than importing Hermes profile state, Hermes tool dispatch, or local-only memory.

Target behavior:

- inspect repos, PRs, diffs, tests, and deployment readiness;
- explain engineering risk in plain language;
- propose small implementation plans;
- run read-only verification by default;
- perform mutations only through explicitly approved, narrow tools later.

## 2. Non-goals

The Build Lead is not:

- a wrapper around Hermes tools;
- a copy of `~/.hermes/profiles/build-lead`;
- a general shell agent;
- a secret-bearing process;
- an autonomous deployer or merger in the first slice;
- the owner of runtime bridge routing.

Do not import or depend on Hermes state databases, profile config, session stores, or memory candidates. Those may inform design, but they are not part of the ADK runtime contract.

## 3. Evidence From Old Build Lead Profile

Read-only inspection of the Mac profile showed these reusable ideas:

- profile path: `~/.hermes/profiles/build-lead`;
- primary posture: engineering/build lead with evidence discipline;
- useful preloaded skills:
  - `systematic-debugging`;
  - `requesting-code-review`;
  - `deployment-operator`;
  - `github-code-review`;
  - `context7-find-docs`;
  - `writing-plans`;
  - `context-router`;
- recommended tool classes:
  - terminal;
  - file;
  - code execution;
  - web/browser/search;
  - session search;
  - skills;
  - memory;
  - todo;
- useful surfaces:
  - Discord;
  - webhook;
  - API server;
  - MCP servers;
- useful operating principle: candidate memory and durable evidence, not silent local state.

Interpretation: reuse the capability pattern, not the runtime.

## 4. Architecture

Use this shape:

```text
Discord
  -> adk-bridge
  -> forsch-agent-build
  -> ADK tool declarations
  -> forsch-adk-components Python shims
  -> constrained local command / GitHub API / docs API / repo filesystem
```

The Build Lead package owns:

- role instructions;
- Build-specific tool selection;
- Build-specific tests and eval prompts;
- output contracts for reviews/plans/status reports.

The shared components package owns:

- reusable tool shims;
- path guards;
- command allowlists;
- Authsome-backed clients;
- GitHub read clients;
- docs lookup adapters;
- common result schemas.

The bridge owns only:

- Discord ingress/egress;
- channel routing;
- ADK Runner/session lifecycle;
- transport-level logging.

## 5. Safety Model

### L0: Read-only, first slice

Allowed:

- inspect repo status;
- inspect recent commits;
- inspect PR metadata/diffs;
- read files inside approved workspace roots;
- search files inside approved workspace roots;
- run allowlisted test/status commands;
- fetch public or Authsome-backed read-only documentation/API data;
- produce plans, findings, and verification summaries.

Forbidden:

- arbitrary shell;
- file writes;
- git commit/push/merge;
- dependency upgrades;
- service restarts;
- editing `.env`, secrets, or profile configs;
- reading raw secret values;
- changing `agent_specs/agents.yaml` or `bridge/bridge_config.yaml` without an explicit route-contract task.

### L1: Narrow mutation, later

Potential future tools, each requiring explicit approval and tests:

- write a bounded file patch in an approved repo;
- create a branch;
- commit staged Build Lead changes;
- open a PR;
- comment on a PR;
- update a CRM Task or Run Record with final status.

L1 does not include direct merges, deploys, or production service restarts unless Zach creates that policy explicitly.

## 6. First Tool Shim Set

Implement in `forsch-adk-components` as `src/forsch/adk_components/tools/build_tools.py`.

### `get_workspace_repos(root: str | None = None) -> dict`

Purpose: list known repos the Build Lead may inspect.

Rules:

- root defaults to `/opt/data/workspace/adk` on cloud;
- only returns directories with `.git`;
- redacts home-specific paths in user-facing summaries when needed;
- does not recurse into ignored runtime state.

### `get_repo_status(repo_path: str) -> dict`

Purpose: report branch, remote, cleanliness, and changed files.

Implementation:

- path must resolve under approved workspace roots;
- command allowlist:
  - `git status --short --branch`;
  - `git remote -v`;
  - `git log --oneline -3`.

Output:

```json
{
  "repo_path": "...",
  "branch": "main",
  "remote": "https://github.com/...",
  "clean": true,
  "changed_files": [],
  "recent_commits": []
}
```

### `list_recent_commits(repo_path: str, limit: int = 5) -> dict`

Purpose: summarize recent repo movement.

Rules:

- `limit` clamped to `1..20`;
- no full patch output;
- return commit SHA prefix, subject, author, date.

### `search_project(pattern: str, path: str, file_glob: str | None = None) -> dict`

Purpose: safe code search.

Rules:

- path must resolve under approved roots;
- pattern length capped;
- output capped to a small result count;
- no binary files;
- prefer ripgrep if available.

### `read_project_file(path: str, offset: int = 1, limit: int = 200) -> dict`

Purpose: read bounded source snippets.

Rules:

- path must resolve under approved roots;
- deny `.env`, key files, SQLite DBs, auth files, and profile state;
- limit maximum lines and bytes;
- indicate truncation.

### `inspect_github_pr(owner_repo: str, pr_number: int) -> dict`

Purpose: read PR state and diff summary.

Implementation:

- use `gh` through Authsome where available;
- read-only fields only: title, state, author, base/head, mergeability, files, checks, review state;
- no comments or mutations in L0.

### `run_allowed_check(repo_path: str, check_name: str) -> dict`

Purpose: run a named, safe verification command.

Rules:

- no raw command strings from the model;
- `check_name` maps to repo-local allowlisted commands;
- timeout required;
- output capped and redacted.

Initial check names:

- `python_import_agent`;
- `pytest_quick`;
- `git_generated_guard`;
- `package_metadata`.

## 7. Build Agent Instruction Contract

The Build Lead should be instructed to:

- verify before claiming;
- prefer small diffs and narrow plans;
- identify repo ownership before edits;
- distinguish source cleanliness from runtime health;
- avoid touching route/interface files during parallel work unless explicitly assigned;
- output findings first for reviews;
- propose one next action when the user sounds overloaded;
- never ask for raw secrets.

Suggested core instruction:

```text
You are the Build Lead for Forsch. You own engineering inspection, PR review, implementation planning, and safe verification. Before making claims, use tools to inspect live repo/API state. Prefer read-only evidence. Do not mutate files, Git state, deployments, secrets, bridge routes, or agent specs unless the task explicitly grants that authority and the matching tool exists. Report risks plainly, with file paths and verification evidence.
```

## 8. Output Contracts

### Repo Inspection

```text
repo: <name/path>
state: clean | dirty | blocked
branch: <branch>
remote: <remote>
findings:
- <risk/evidence>
next: <one recommended action>
```

### PR Review

Findings first, ordered by severity:

```text
findings:
- severity: high|medium|low
  file: path:line
  issue: ...
  evidence: ...
open questions:
- ...
verification:
- command/result summary
```

### Implementation Plan

```text
goal: ...
constraints:
- ...
steps:
1. file/path - exact change
2. test command - expected signal
rollback:
- ...
```

### Run Record Summary

When integrated with CRM/run records later:

```json
{
  "agent": "build",
  "task_ref": "CRM Task/... or null",
  "trigger": "discord|scheduled|manual",
  "repos_touched": [],
  "tools_used": [],
  "claims_verified": [],
  "blockers": [],
  "next_action": "..."
}
```

## 9. Tests and Evals

### Unit tests in `forsch-adk-components`

- path guard allows approved workspace files;
- path guard rejects `/etc/passwd`, `.env`, SQLite DBs, and profile auth files;
- repo status parses clean and dirty states;
- search caps output;
- `run_allowed_check` rejects unknown check names;
- GitHub PR inspection command construction does not expose tokens.

### Build agent tests in `forsch-agent-build`

- imports `agent` and/or `root_agent`;
- model is `LiteLlm`;
- expected Build tools are attached;
- instruction contains read-only and evidence boundaries.

### Evals

Start with text fixtures:

1. dirty repo, no user permission to edit -> report and ask for explicit edit scope;
2. PR review with obvious bug -> findings first;
3. request to deploy from dirty tree -> block and explain;
4. request to touch `bridge_config.yaml` during parallel dashboard work -> refuse unless route-contract task is explicit;
5. user asks for broad build help -> inspect first, then propose one narrow next action.

## 10. Relationship to CRM Task / Run Record

CRM should be the human-facing task index, not the full execution log.

Future shape:

- `CRM Task` = requested unit of work;
- `Run Record` = machine execution summary;
- artifact links = logs, reports, diffs, PRs, screenshots.

The Build Lead should eventually read assigned CRM Tasks and write final summaries only after write policy is approved. Full logs should live in repo/storage artifacts, linked from CRM, not pasted wholesale into Frappe.

## 11. Relationship to Bridge Work

This spec does not require changing:

- `agent_specs/agents.yaml`;
- `bridge/bridge_config.yaml`;
- Discord route assignments.

Bridge work remains separate:

- inject correct LiteLLM env into `adk-bridge`;
- verify `#team-build` can reach `forsch-agent-build`;
- verify tool calls execute through ADK once tools are attached.

During parallel dashboard work, treat route/interface files as read-only.

## 12. Open Questions for Review

1. Should Build Lead L0 include `run_allowed_check`, or should all command execution wait until L1?
2. Should GitHub PR inspection use `gh` via Authsome, direct GitHub REST via Authsome, or both?
3. What are the approved workspace roots besides `/opt/data/workspace/adk` and `/opt/data/repos`?
4. Should Build Lead receive docs lookup first through Context7 MCP, Google Developer Knowledge MCP, or plain web search wrappers?
5. Should Build Lead own deployment readiness checks, or should it hand those to Ops Lead?
6. What Discord channel should receive Build Lead run summaries once bridge routing is healthy?

## 13. Proposed First Implementation Slice

1. Add `build_tools.py` to `forsch-adk-components` with read-only repo/file/PR tools.
2. Add tests for path guards, repo status, file search/read, and command allowlists.
3. Export tools from `forsch.adk_components.tools`.
4. Attach the read-only tools to `forsch-agent-build`.
5. Add Build agent import/tool tests.
6. Do not edit route/interface files.
7. Verify locally with component tests and Build agent import tests.
8. Push via PR unless Zach explicitly asks for direct main.
