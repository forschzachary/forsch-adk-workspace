# ScreeningRoom native ADK Discord bots — deploy image (Hetzner).
#
# Runs Huberto + screening_ops (+ optional curator) via
#   python -m forsch.adk_bridge.discord_main
#
# Design (matches bridge/Dockerfile's philosophy): third-party deps are baked in,
# but the forsch.* code is NOT installed — it is mounted from the workspace at
# runtime and found via PYTHONPATH, so a `git pull` + restart picks up new code
# with no rebuild. The image only changes when a *dependency* changes.
#
# Node is included because the bots shell out to the zero-dep `sr` CLI
# (screening-room/scripts/sr), which is mounted read-only and pointed at by SR_CLI.
#
# Build:  docker compose -f deploy/docker-compose.yml build
# Up:     docker compose -f deploy/docker-compose.yml up -d
FROM python:3.13-slim

# tini = proper PID 1 / signal forwarding; git = safe.directory for the mounted
# repos; curl + ca-certificates = connectivity pre-checks and TLS to the gateway.
# nodejs + npm = run the `sr` CLI (Debian trixie ships Node 20.x, which satisfies
# the CLI's ESM + global fetch usage). gnupg/lsb-release kept out — stdlib Node is enough.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini git curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN git config --system --add safe.directory '*'

# Third-party Python deps ONLY. The forsch.* packages (bridge + agents) are mounted
# from the workspace and resolved via PYTHONPATH — never pip-installed here.
# Versions track bridge/pyproject.toml + bridge/Dockerfile.
RUN pip install --no-cache-dir \
        "google-adk[extensions]==2.3.0" \
        "discord.py>=2.4" \
        "pyyaml>=6" \
        "pydantic>=2" \
        "httpx>=0.27"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FORSCH_ADK_WORKSPACE=/workspace \
    HOME=/root

# The workspace (forsch repo) is bind-mounted here at runtime; nothing is COPYed in,
# so the image stays generic and a code change never needs a rebuild.
WORKDIR /workspace

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "forsch.adk_bridge.discord_main"]
