"""Patterns library — keyword-indexed reusable building blocks for ADK agents.

Each pattern's frontmatter (in its docstring) declares:
- keywords: lazy-load triggers for AI keyword matching
- intention: plain English "what does this save me from rebuilding"
- function: one-line technical description
- depends_on: other patterns it imports
- used_by: which tools/agents currently use it
- example: one-line usage

See inventory.yaml for the master index. _lint.py catches drift.
"""
from .agent_factory import make_agent, make_model
from .jsonl_store import JSONLStore
from .mimo_stream_runner import run as mimo_stream_run
from .oauth_client import OAuthAPIClient, OAuthError
from .receipt_tool import receipt
from .whitelist import WhitelistStore

__all__ = [
    "JSONLStore",
    "OAuthAPIClient",
    "OAuthError",
    "WhitelistStore",
    "make_agent",
    "make_model",
    "mimo_stream_run",
    "receipt",
]
