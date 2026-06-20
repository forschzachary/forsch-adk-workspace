# ADK agent runbook

## Quick start

```bash
# One-time: install shared components
cd /opt/data/workspace/adk/components
uv pip install -e ".[dev]"

# Install and run an agent
cd /opt/data/workspace/adk/agents/build
uv pip install -e ".[dev]"
python -m forsch.agent_build.agent
```

## Adding a new shared tool

1. Create the module in `components/src/forsch/adk_components/tools/`:

```python
# components/src/forsch/adk_components/tools/frappe_client.py
import httpx
from google.adk.tools import ToolContext

async def get_crm_leads(doctype: str = "CRM Lead", limit: int = 20, tool_context: ToolContext = None):
    """Fetch leads from Frappe CRM via Authsome."""
    # Use authsome run under the hood
    ...
```

2. Export it in `components/src/forsch/adk_components/tools/__init__.py`:

```python
from .frappe_client import get_crm_leads
```

3. Agents import it:

```python
from forsch.adk_components.tools import get_crm_leads

agent = Agent(
    name="brand_agent",
    tools=[get_crm_leads],
    ...
)
```

## Adding a new agent

```bash
# Create the repo on GitHub first, then:
mkdir -p /opt/data/workspace/adk/agents/<name>/src/forsch/agent_<name>/
mkdir -p /opt/data/workspace/adk/agents/<name>/tests/
mkdir -p /opt/data/workspace/adk/agents/<name>/evals/

cd /opt/data/workspace/adk/agents/<name>
git init
git checkout -b main

# Copy pyproject.toml from an existing agent, update name/description
# Create agent.py stub
# uv pip install -e ".[dev]"
# git add -A && git commit -m "chore: initial scaffold"
# git remote add origin git@github.com:forschzachary/forsch-agent-<name>.git
# git push -u origin main
```

## Running tests

```bash
# Per-agent
cd /opt/data/workspace/adk/agents/build
python -m pytest

# All agents
for d in /opt/data/workspace/adk/agents/*/; do
  echo "=== $d ==="
  cd "$d" && python -m pytest
done

# Components library
cd /opt/data/workspace/adk/components
python -m pytest
```

## Linting

```bash
# Per-agent
cd /opt/data/workspace/adk/agents/build
ruff check .

# All
for d in /opt/data/workspace/adk/components /opt/data/workspace/adk/agents/*/; do
  echo "=== $d ==="
  cd "$d" && ruff check .
done
```

## Authsome credential pattern

Every external API call in agent tools should use this pattern:

```python
import subprocess
import json
import os

AUTHSOME_BIN = "/opt/data/home/.local/bin/authsome"
AUTHSOME_BASE = os.environ.get("AUTHSOME_BASE_URL", "http://127.0.0.1:7998")

def authsome_curl(method: str, url: str, data: dict = None) -> dict:
    """Make an authenticated HTTP call through Authsome."""
    env = {**os.environ, "AUTHSOME_BASE_URL": AUTHSOME_BASE}
    cmd = [AUTHSOME_BIN, "run", "--", "curl", "-fsS", "-X", method, url]
    if data:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Authsome call failed: {result.stderr}")
    return json.loads(result.stdout)
```

## CRM health check (ops agent example)

```bash
# From this box, via Authsome:
AUTHSOME_BASE_URL=http://127.0.0.1:7998 /opt/data/home/.local/bin/authsome run -- \
  curl -fsS -H "Host: crm.forschfrontiers.com" \
  https://frappe-web-production-7412.up.railway.app/api/method/ping

# Lead count:
AUTHSOME_BASE_URL=http://127.0.0.1:7998 /opt/data/home/.local/bin/authsome run -- \
  curl -fsS -H "Host: crm.forschfrontiers.com" \
  "https://frappe-web-production-7412.up.railway.app/api/method/frappe.client.get_count?doctype=CRM+Lead"
```

## Common issues

### "No module named forsch.adk_components"
You forgot to install the components library in editable mode:
```bash
cd /opt/data/workspace/adk/components && uv pip install -e .
```

### Authsome connection refused
Authsome daemon is down. Check:
```bash
curl http://127.0.0.1:7998/health
```
If it fails, restart the stack:
```bash
cd /opt/data/services/authsome && docker compose up -d
```

### LiteLLM returns 400
Database disconnected. Check:
```bash
curl http://127.0.0.1:4000/health/readiness
```
If `db: Not connected`, LiteLLM needs a database reconnect. See `canonical/business-stack/hubert-litellm/` for details.

### Git push fails with "no remote"
Local clones were created without remotes. Add them:
```bash
cd /opt/data/workspace/adk/agents/build
git remote add origin git@github.com:forschzachary/forsch-agent-build.git
```
