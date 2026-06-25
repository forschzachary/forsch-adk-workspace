# Native ADK bridge — slim, no hermes, no s6, no gateway.
# forsch.* code comes from the mounted workspace via PYTHONPATH (so Generate ->
# agent.py -> restart -> live keeps working, and there is no venv to mismatch).
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends tini git \
    && rm -rf /var/lib/apt/lists/*

RUN git config --system --add safe.directory '*'

# third-party deps only; the forsch packages are mounted, not installed
RUN pip install --no-cache-dir \
      "google-adk[extensions]==2.3.0" \
      "discord.py>=2.4" \
      "pyyaml>=6" \
      "pydantic>=2" \
      "httpx>=0.27" \
      "fastapi>=0.110" \
      "uvicorn[standard]>=0.30" \
      "gradio>=5"

ENV PYTHONUNBUFFERED=1
WORKDIR /workspace/bridge
ENTRYPOINT ["tini","--"]
CMD ["python","-m","forsch.adk_bridge.http"]
