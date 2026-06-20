# ADK cross-agent architecture

## Overview

Five independent agents, one shared component library, one credential gateway. Agents communicate through shared tools and data contracts, not direct RPC. Each agent owns its domain; cross-cutting concerns live in the components library.

```
                    ┌─────────────────────────────┐
                    │        Authsome              │
                    │   (credential gateway)       │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                 │
     ┌────────▼──────┐  ┌─────▼──────┐  ┌──────▼────────┐
     │  GitHub API   │  │ Frappe CRM │  │  Gmail/Cal API │
     └───────────────┘  └────────────┘  └───────────────┘
                               │
                               │
    ┌──────────────────────────┼──────────────────────────┐
    │                          │                          │
    │              forsch-adk-components                  │
    │         (shared tools, models, testing)            │
    │                          │                          │
    └──────────────────────────┼──────────────────────────┘
                               │
         ┌─────────┬───────────┼───────────┬─────────┐
         │         │           │           │         │
    ┌────▼───┐ ┌───▼────┐ ┌───▼───┐ ┌────▼───┐ ┌───▼────┐
    │ build  │ │ brand  │ │  ops  │ │assistant│ │ social │
    └────────┘ └────────┘ └───────┘ └────────┘ └────────┘
```

## Design principles

### 1. Agents don't call agents
Agents communicate through shared state (CRM, files, databases), not direct agent-to-agent RPC. If the brand agent needs lead data, it queries CRM — it doesn't ask the build agent. This keeps agents independently deployable and testable.

### 2. Tools are shared, instructions are owned
The components library owns API clients, data models, and test harnesses. Each agent owns its instructions, workflows, and domain-specific logic. A new API integration (e.g., Stripe) goes into components once and is available to all agents.

### 3. Authsome is the only credential surface
No agent gets its own API key. Every external call — GitHub, CRM, Gmail, Stripe — goes through `authsome run`. This means one audit log, one secret store, one rotation surface.

### 4. CRM is the business state layer
Frappe CRM holds contacts, leads, and custom DocTypes. Agents that need business context read from CRM rather than maintaining their own databases. This avoids data duplication and keeps CRM as the single source of truth.

## Agent domains

### build — product & engineering
- **Owns:** GitHub PR review, issue triage, code quality checks, CI/CD pipeline
- **Tools needed:** GitHub API (via Authsome), git operations, linting/type-checking
- **State:** Stateless — reads from GitHub, writes PR comments and issue labels
- **CRM interaction:** Triggers CRM redeploy on `forsch_frontiers` app changes

### brand — brand & marketing
- **Owns:** Content strategy, positioning, design review, copywriting
- **Tools needed:** Notion (content calendar), CRM (contact lists), image generation
- **State:** Content calendar in CRM as custom DocTypes
- **CRM interaction:** Reads contacts for campaigns, writes content calendar items

### ops — infrastructure & operations
- **Owns:** Deployment, monitoring, incident response, health checks
- **Tools needed:** Railway CLI/API, Docker, system metrics, CRM health endpoints
- **State:** Monitoring dashboards, incident logs
- **CRM interaction:** Monitors CRM health, tracks lead counts as business metrics

### assistant — personal assistant
- **Owns:** Calendar, email, tasks, scheduling, reminders
- **Tools needed:** Gmail API, Google Calendar API (both via Authsome)
- **State:** Task lists, calendar state
- **CRM interaction:** Syncs calendar events with CRM contacts

### social — social media
- **Owns:** Posting, engagement tracking, analytics, content calendar
- **Tools needed:** X/Twitter API, social platform APIs, CRM (lead lists)
- **State:** Post queue, analytics cache
- **CRM interaction:** Pulls lead lists for outreach targeting

## Data flow patterns

### Pattern A: Agent → Authsome → External API
```
agent.tools.github_client.create_pr(...)
  → authsome run -- curl -X POST https://api.github.com/...
    → GitHub API
      → response → agent
```
Used for: GitHub, CRM REST API, Gmail, Stripe, any external HTTP API.

### Pattern B: Agent → CRM (read)
```
agent.tools.frappe_client.get_list("CRM Lead", filters={...})
  → authsome run -- curl https://frappe-web-production-7412.up.railway.app/api/...
    → Frappe REST API
      → lead data → agent
```
Used for: brand pulling contacts, social pulling lead lists, assistant syncing contacts.

### Pattern C: Agent → CRM (write)
```
agent.tools.frappe_client.create_doc("FF Content Calendar", data={...})
  → authsome run -- curl -X POST https://frappe-web-production-7412.up.railway.app/api/...
    → Frappe REST API
      → created doc → agent
```
Used for: brand writing content calendar items, ops writing incident reports.

### Pattern D: Agent → filesystem / local state
```
agent writes to /opt/data/workspace/adk/state/<agent>/
```
Used for: agent-specific state that doesn't belong in CRM (eval results, temporary caches).

## Model routing

All agents route through LiteLLM for model access:

```
agent.model_request("gpt-5.5", prompt)
  → LiteLLM proxy (http://127.0.0.1:4000)
    → gpt-5.5 (primary) or deepseek (fallback)
      → response → agent
```

This gives unified cost tracking, fallback chains, and one place to manage provider keys. Agents should not hardcode model names — use environment variables or a shared config.

## Testing strategy

### Unit tests (per-agent)
- Agent instruction compliance (does it follow its domain rules?)
- Tool output parsing (does it handle API responses correctly?)
- Workflow branching (does it take the right path given input X?)

### Integration tests (components library)
- Authsome → GitHub round-trip
- Authsome → CRM round-trip
- LiteLLM → model round-trip

### Eval datasets (per-agent)
- Curated input/output pairs for each agent's domain
- Regression suite to catch instruction drift
- ADK's built-in eval framework for scoring

## Deployment options

| Option | Pros | Cons |
|--------|------|------|
| Cloud box (this machine) | Already has Authsome, LiteLLM, ADK installed | Single point of failure, shares resources with Hubert |
| Railway services | Isolated, scalable, same platform as CRM | New deploy surface, needs Authsome reachability |
| Hermes cron jobs | No new infra, uses existing scheduler | Ephemeral sessions, no persistent agent state |
| Zach's Mac | Direct access, low latency | Not always on, not a server |

Likely answer: cloud box for development, Railway for production agents that need uptime, Hermes cron for scheduled tasks.
