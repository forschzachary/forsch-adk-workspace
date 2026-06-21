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

echo "[3/5] bridge — native container image (no venv; deps baked, code mounted)"
# The native adk-bridge has no venv: third-party deps are baked into the image
# and forsch.* is mounted via PYTHONPATH. Rebuild the image, not a venv.
( cd "$A/bridge" && docker compose build )

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
