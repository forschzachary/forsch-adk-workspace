#!/usr/bin/env bash
# Rebuild all Forsch ADK workspace venvs reproducibly with uv.
# Recovers the runtime floor after a reimage or venv drift.
# uv is not on PATH for non-login shells -> add it explicitly.
# Method: uv-managed (the box has no python3.12-venv/ensurepip; stdlib venv
# cannot bootstrap pip). components+builder have uv.lock (uv sync); stability+
# bridge resolve local forsch-* packages via editable path installs (uv pip).
set -euo pipefail
export PATH=/root/.local/bin:$PATH
A=/root/.hermes/workspace/adk
unset VIRTUAL_ENV || true

echo "[1/4] components (dependency anchor)"
cd "$A/components"; rm -rf .venv
uv sync --extra dev
./.venv/bin/python -m pytest -q

echo "[2/4] agents/stability"
cd "$A/agents/stability"; rm -rf .venv
uv venv
uv pip install -e "$A/components" -e ".[dev]"
./.venv/bin/python -m pytest -q

echo "[3/4] bridge venv — built INSIDE the container (python 3.13), NOT host (3.12)"
# The bridge runs in the adk-bridge container (python 3.13.5). A host-built venv
# (python 3.12) has version-specific site-packages the container cannot see ->
# ModuleNotFoundError: forsch on docker restart. Build it with the container
# python via the hermes container (same image, same /opt/data mount).
docker exec hermes sh -lc "cd /opt/data/workspace/adk/bridge && rm -rf .venv && uv venv --python /usr/bin/python3 && uv pip install \
  -e /opt/data/workspace/adk/components \
  -e /opt/data/workspace/adk/agents/stability -e /opt/data/workspace/adk/agents/ops \
  -e /opt/data/workspace/adk/agents/social -e /opt/data/workspace/adk/agents/brand \
  -e /opt/data/workspace/adk/agents/assistant -e /opt/data/workspace/adk/agents/build -e ."
docker exec hermes sh -lc "cd /opt/data/workspace/adk/bridge && .venv/bin/python -m pytest tests/test_stability_route.py -q" || true

echo "[4/5] builder (cockpit dashboard)"
cd "$A/builder"; rm -rf .venv
uv sync
uv pip install -e "$A/factory" ruamel.yaml "uvicorn[standard]" websockets
./.venv/bin/python -m pytest -q

echo "[5/5] factory (deterministic generator; lean deps, no adk needed)"
cd "$A/factory"; rm -rf .venv
uv venv
uv pip install -e ".[dev]"
./.venv/bin/python -m pytest -q

echo "All ADK workspace venvs rebuilt and green."
