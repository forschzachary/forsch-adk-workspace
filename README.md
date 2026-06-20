# ADK Workspace — Forsch Team Agents

Google ADK 2.x-based multi-agent system. One shared component library, independent team-lead agents, and a read-only stability governor.

## Structure

```
adk/
├── components/          # Shared library (one git repo)
│   ├── pyproject.toml
│   └── src/forsch/adk_components/
│       ├── tools/       # Shared tools (GitHub, Authsome, Slack, etc.)
│       ├── models/      # Shared Pydantic models / data contracts
│       └── testing/     # Shared test harness, eval framework
├── agents/              # Per-agent repos (independent git, versioning, CI)
│   ├── build/           # Product & engineering agent
│   ├── brand/           # Brand & marketing agent
│   ├── ops/             # Operations & infrastructure agent
│   ├── assistant/       # Personal assistant agent
│   ├── social/          # Social media agent
│   └── stability/       # Read-only stability governor
├── agent_specs/         # Canonical agent manifest
└── docs/                # Cross-agent architecture, runbooks, ADK patterns
```

## Team leads

| Agent | Role | Key responsibilities |
|-------|------|---------------------|
| build | Product & engineering | PR review, issue triage, dev workflow, code quality |
| brand | Brand & marketing | Content strategy, positioning, design review, copy |
| ops | Operations | Infrastructure, deployment, monitoring, incident response |
| assistant | Personal assistant | Calendar, email, tasks, scheduling, reminders |
| social | Social media | Posting, engagement tracking, analytics, content calendar |
| stability | Stability governor | Read-only workspace audits, import checks, service health, safe-change reports |

Memory agent is excluded — separate solution in progress.

## Shared components

All agents depend on `forsch-adk-components` for:
- **tools**: Authsome-backed business clients, CRM read tools, stability inspection, service health probes
- **models**: Shared Pydantic schemas (Task, PR, Event, etc.)
- **testing**: Eval harness, mock providers, regression suite

## Per-agent repo pattern

Each agent is a standalone Python package with its own git repo:

```
agents/<name>/
├── pyproject.toml
├── README.md
├── src/forsch/agent_<name>/
│   ├── __init__.py
│   ├── agent.py          # ADK Agent definition
│   ├── workflow.py       # ADK Workflow (if graph-based)
│   ├── tools.py          # Agent-specific tools
│   └── prompts.py        # System instructions, prompt templates
├── tests/
│   ├── test_agent.py
│   └── test_tools.py
└── evals/                # Agent-specific eval datasets
```

## Getting started

```bash
# Install shared components (editable)
cd components && uv pip install -e .

# Install an agent (editable)
cd agents/build && uv pip install -e .

# Run an agent
python -m forsch.agent_build.agent
```

## ADK version

Pinned to `google-adk>=2.0`. Currently installed: 2.3.0.
