# Stability Governor Agent Design

## Working Name

`stability` or `governor`.

My vote: `stability` for the agent ID, `Forsch Stability Governor` for the display name. It says what it does without cosplaying a cybernetic parliament.

## Core Idea

A dedicated ADK agent whose only job is protecting Hubert and the surrounding agent stack from drift, breakage, configuration rot, unsafe self-modification, and silent degradation.

It is not a general coding agent. It is an outside observer and systems caretaker.

It watches, audits, proposes, verifies, and escalates. It does not casually mutate production.

## Why This Agent Should Exist

Hubert is becoming infrastructure, not just a chat surface. The risk is not one spectacular failure; it is slow entropy:

- config drift between Hermes, LiteLLM, Authsome, ADK, bridge services, and skills
- model/provider changes that silently break tool behavior
- generated agents with stale imports or broken ADK assumptions
- Discord bridge/session bugs that appear only during live use
- memory/skill accumulation that becomes contradictory
- long-running services dying quietly
- risky “vibe-coded” edits bypassing test and rollback discipline

The Stability Governor is the counterweight: boring, suspicious, receipt-oriented, and hard to impress.

## Relationship To Aura's Governor

Borrow the useful pattern, not the mythology.

Aura pattern worth stealing:

- outside observer separate from the normal cognitive loop
- dependency graphing and codebase hygiene
- staged refactor planning
- proof receipts for changes
- rollback packets before promotion
- fault localization and repair suggestions
- central gate for risky actions

What we should not copy literally:

- pretending every tool execution needs a cryptographic constitution on day one
- hot-reloading self-modified cognitive handlers into production
- overbuilding 20Hz-loop machinery that does not map to Hermes/ADK
- giving the agent unilateral authority to rewrite live systems

Our version is more practical: stable infra guardian first, recursive self-improvement governor later.

## Scope Boundary

The Stability Governor monitors and protects:

```text
/opt/data/config.yaml                 # Hermes config
/opt/data/.env                        # only metadata/required keys, never raw secret output
/opt/data/workspace/adk/              # ADK agents/components/bridge/docs
/opt/data/services/authsome/          # Authsome health and version state
LiteLLM proxy                         # model list, health, fallback drift
Hermes gateway/logs                   # service health and repeated errors
skills/memory docs                    # structural hygiene, not personal content overreach
```

It does not own:

- Zach's whole filesystem
- arbitrary app code unless added as a watched target
- direct deployment without approval
- secrets
- user-facing personality
- product decisions

## Autonomy Levels

### L0: Read-Only Auditor

Can inspect files, logs, git status, service health, and dependency graphs. Produces reports only.

Allowed without approval:

- read repo state
- run safe status commands
- run tests configured as read-only verification
- generate architecture reports
- create proposed plans

### L1: Prepared Fixes

Can create branches/patches/plans, but cannot apply to production automatically.

Allowed without approval:

- write proposed patch files under a staging directory
- open local draft reports
- produce rollback packet metadata

Requires approval:

- editing tracked source/config
- restarting services
- installing/upgrading packages

### L2: Guarded Maintenance

Can apply low-risk edits after passing checks, with rollback packets.

Allowed after policy approval:

- update generated docs
- refresh generated agent wrappers
- remove cache files
- apply formatting-only fixes

Always requires explicit human approval:

- config changes affecting model/provider/credentials/gateway
- dependency upgrades
- service restarts
- bridge routing changes
- anything touching secrets

### L3: Self-Improvement Governor

Future. The agent can manage autonomous repair proposals and run them in isolated worktrees/containers with proof receipts. Promotion still requires a policy gate.

Do not build L3 first. That is how people summon bureaucracy with a stack trace.

## Architecture

```text
Discord / scheduled run
        │
        ▼
Stability Governor ADK agent
        │
        ├── inventory tools
        │   ├── filesystem manifest
        │   ├── git status/diff/log summaries
        │   ├── service health checks
        │   └── config/schema checks
        │
        ├── graph tools
        │   ├── Python import graph
        │   ├── ADK agent registry graph
        │   ├── bridge route graph
        │   └── external dependency graph
        │
        ├── verification tools
        │   ├── pytest targeted suites
        │   ├── `hermes mcp test`
        │   ├── ADK import smoke tests
        │   └── bridge config validation
        │
        ├── receipt tools
        │   ├── snapshot before changes
        │   ├── hash changed files
        │   ├── record commands/checks
        │   └── write rollback packet
        │
        └── reporting sinks
            ├── Discord trace webhook
            ├── docs/reports/*.md
            └── optional cron delivery
```

## Agent Spec Draft

```yaml
agents:
  stability:
    status: draft
    repo_path: agents/stability
    package: forsch.agent_stability
    export_attr: root_agent
    adk_name: stability_governor
    display_name: Stability Governor
    description: Outside observer for Hubert and the ADK agent stack; audits stability, drift, and safe-change readiness.
    instruction_file: instructions/stability.md
    tools:
      - forsch.adk_components.tools.stability.collect_workspace_inventory
      - forsch.adk_components.tools.stability.collect_git_state
      - forsch.adk_components.tools.stability.check_hermes_health
      - forsch.adk_components.tools.stability.check_litellm_health
      - forsch.adk_components.tools.stability.check_authsome_health
      - forsch.adk_components.tools.stability.validate_adk_agents
      - forsch.adk_components.tools.stability.build_python_import_graph
      - forsch.adk_components.tools.stability.create_rollback_packet
      - forsch.adk_components.tools.stability.write_stability_report
    discord:
      channels:
        - "#team-stability"
      dm_fallback: false
    tracing:
      enabled: true
      include_tool_args: false
    autonomy:
      level: L0
      can_write: false
      can_restart_services: false
      requires_approval_for:
        - source_edits
        - config_edits
        - dependency_changes
        - service_restarts
        - secrets_access
    web:
      enabled: true
      editable_yaml: true
    evals:
      smoke_prompts:
        - "audit the ADK workspace and tell me what is most likely to break next"
        - "check whether the Google Developer Knowledge MCP is configured and healthy"
        - "inspect the ADK bridge config for route drift"
        - "prepare a safe plan to normalize agent exports to root_agent"
```

## Instruction Shape

The Stability Governor should sound like a systems engineer, not a life coach.

Core instruction:

```text
You are the Stability Governor for Hubert and the Forsch ADK agent stack.
Your job is to preserve runtime stability, detect drift, and prepare safe changes.
You are conservative by default. You prefer verified evidence over speculation.
You never claim a system is healthy without checking live state.
You separate findings into: critical, degraded, noisy, and suggested cleanup.
You do not edit source, configs, credentials, or services unless the current autonomy policy permits it.
For every proposed change, include verification commands and rollback steps.
```

Hard behavioral rules:

- Never read or print raw secrets.
- Never run destructive git commands.
- Never restart production services without explicit approval.
- Never edit Hermes config directly in L0/L1.
- Never mark a change safe without tests or a stated reason tests cannot run.
- Always distinguish “observed” from “inferred.”

## Tool Design

### 1. Inventory Tools

`collect_workspace_inventory(root: str) -> dict`

Returns a bounded manifest:

- structural directories
- package files
- generated docs
- untracked caches
- file counts by extension
- recently modified files

No raw file dumps.

### 2. Git State Tools

`collect_git_state(paths: list[str]) -> dict`

For each repo:

- branch
- remote
- status summary
- last commit
- uncommitted file list
- ahead/behind if available

### 3. Health Tools

`check_hermes_health() -> dict`

- `hermes doctor` if safe
- `hermes mcp list/test google-dev-knowledge`
- gateway process/log status if accessible

`check_litellm_health() -> dict`

- GET `/health` if present
- GET `/v1/models`
- compare against expected configured models

`check_authsome_health() -> dict`

- GET Authsome health endpoint
- version if available

### 4. ADK Validation Tools

`validate_adk_agents(workspace: str) -> dict`

- import each agent package
- check `root_agent` exists
- check ADK Web wrappers exist
- check bridge route points to importable attr
- check generated YAML parses

### 5. Graph Tools

`build_python_import_graph(paths: list[str]) -> dict`

Initial implementation can be simple AST parsing:

- modules
- imports
- local package edges
- suspicious cycles
- forbidden imports such as `google-generativeai`

Later upgrade to pydeps/grimp if useful.

### 6. Receipt Tools

`create_rollback_packet(targets: list[str], reason: str) -> dict`

Creates under:

```text
/opt/data/workspace/adk/state/stability/rollback_packets/<timestamp>/
```

Includes:

- file hashes
- git status
- copied original files for intended edits
- command log
- verification plan
- restore script for file copies only

### 7. Report Tools

`write_stability_report(title: str, content: str) -> str`

Writes:

```text
/opt/data/workspace/adk/docs/reports/stability-YYYYMMDD-HHMMSS.md
```

## Receipts: Practical Version

We do not need heavy crypto first. Start with deterministic evidence receipts:

```json
{
  "receipt_version": 1,
  "agent": "stability_governor",
  "created_at": "2026-06-20T...Z",
  "intent": "normalize root_agent exports",
  "targets": ["agents/build/src/forsch/agent_build/agent.py"],
  "pre_hashes": {"path": "sha256..."},
  "commands_planned": ["pytest ..."],
  "rollback_packet": ".../rollback_packets/20260620...",
  "approval_required": true
}
```

Later we can sign receipts. First make them useful.

## Fault Pipeline, Forsch Version

Aura has a shadow healer. Our version should be:

1. detect failure in logs/tests/import smoke
2. classify failure: import, config, dependency, credential, runtime, unknown
3. isolate minimal failing command
4. propose fix
5. create rollback packet
6. apply only if autonomy level permits
7. rerun verification
8. report

No mystical self-healing. Just disciplined debugging with a receipt.

## First Build Slice

Build L0 read-only governor first.

Deliverables:

1. `agents/stability` package
2. `web_agents/stability` wrapper/YAML
3. `#team-stability` bridge route placeholder
4. shared stability tools in components
5. report writer
6. three smoke prompts
7. first report: ADK workspace stability audit

No edits. No service restarts. No rollback automation yet.

## First Real Prompt

```text
Audit the ADK workspace and Hubert runtime support stack. Tell me what is most likely to break next, what evidence you observed, and what the safest next maintenance action is. Do not modify files.
```

Expected output:

- critical findings
- degraded findings
- hygiene/noise
- suggested next action
- evidence commands/results
- no fake certainty

## Design Decision

This should be the first real agent before `build`.

Why: it becomes the safety rail for every later vibe-coded agent. If Zach wants to make agents through conversational design, the first agent should be the one that keeps that process from turning into spaghetti with a Discord token.

Dry? yes. Correct? also yes.
