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

echo "[3/4] bridge (all six agent packages editable)"
cd "$A/bridge"; rm -rf .venv
uv venv
uv pip install -e "$A/components" \
  -e "$A/agents/stability" -e "$A/agents/ops" -e "$A/agents/social" \
  -e "$A/agents/brand" -e "$A/agents/assistant" -e "$A/agents/build" \
  -e ".[dev]"
./.venv/bin/python -m pytest tests/test_stability_route.py -q

echo "[4/4] builder (cockpit dashboard)"
cd "$A/builder"; rm -rf .venv
uv sync
./.venv/bin/python -m pytest -q

echo "All ADK workspace venvs rebuilt and green."
