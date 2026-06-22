"""Shared pytest fixtures / env setup for the adk-chat test suite.

cl_app imports chainlit and opens HUBERT_SOUL_PATH at module-load time, so the
env must be primed before that import. Set sensible defaults here so tests can
import cl_app without a live service env.
"""
import os

os.environ.setdefault("IS_SANDBOX", "1")
os.environ.setdefault(
    "HUBERT_SOUL_PATH",
    "/root/.hermes/workspace/adk/chat/hubert_soul.md",
)
