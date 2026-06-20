# Current State

Last verified: 2026-06-20.

## Cleaned-up source ownership

The ADK work is no longer intentionally local-only. It is split across GitHub repos by ownership:

- `forschzachary/forsch-adk-workspace` - workspace docs, manifests, ADK Web wrappers.
- `forschzachary/forsch-adk-components` - shared component package. Stability tools are in PR #1.
- `forschzachary/forsch-agent-stability` - packaged read-only Stability Governor agent.
- `forschzachary/forsch-adk-bridge` - Discord bridge runtime and route config.

## Runtime state

The live durable bridge is a Docker container:

- name: `adk-bridge`
- image: `hermes-agent`
- restart policy: `unless-stopped`
- network: `host`
- mount: `/root/.hermes -> /opt/data`
- command: `cd /opt/data/workspace/adk/bridge && . .venv/bin/activate && exec python -m forsch.adk_bridge.bridge`

The bridge has connected to Discord and resumed sessions. Older logs include a model-routing failure from a missing Gemini API key, so future runtime work should check LiteLLM/ADK model configuration before assuming agent responses are healthy.

## Verification evidence

Latest known verification commands:

```bash
# Components stability tests
cd /opt/data/workspace/adk/components
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  ./.venv/bin/python -m pytest tests/test_stability_audit_script.py tests/test_stability_tools.py -q
# 10 passed

# Stability audit
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  ./.venv/bin/python scripts/stability_audit.py --skip-services
# failed_agent_imports: []
# failed_services: []
# workspace_exists: true
# dirty_repo_count: 6

# Stability agent package
cd /opt/data/workspace/adk
PYTHONPATH=/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  /opt/data/workspace/adk/components/.venv/bin/python \
  -m pytest /opt/data/workspace/adk/agents/stability/tests/test_agent.py -q
# 1 passed

# Bridge route tests
cd /opt/data/workspace/adk/bridge
PYTHONPATH=/opt/data/workspace/adk/bridge/src:/opt/data/workspace/adk/agents/stability/src:/opt/data/workspace/adk/components/src \
  ./.venv/bin/python -m pytest tests/test_stability_route.py -q
# 4 passed
```

## Known open items

- Merge or continue PR #1 in `forsch-adk-components`.
- Decide whether `web_agents/*/tmp/*` wrappers should remain tracked. They are source wrappers, not session DBs, but they may be redundant with the parent wrappers.
- Fix bridge model routing so agents consistently use LiteLLM/Authsome paths rather than falling back to raw Gemini configuration.
- Resolve unrelated dirty work in existing agent repos: ops, assistant, brand, build, social.

## Resume instructions for future agents

1. Read `GIT-DISCIPLINE.md` first.
2. Run `git status -sb` in the exact repo you plan to touch.
3. Do not edit nested repos from the workspace repo by accident.
4. Keep source durable: commit and push meaningful work before calling it done.
5. Never track runtime DBs, `.adk` sessions, caches, venvs, or secrets.
