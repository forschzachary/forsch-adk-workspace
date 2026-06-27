"""Patterns library — keyword-indexed reusable building blocks for ADK agents.

Each pattern's frontmatter (in its docstring) declares:
- keywords: lazy-load triggers for AI keyword matching
- intention: plain English "what does this save me from rebuilding"
- function: one-line technical description
- depends_on: other patterns it imports
- used_by: which tools/agents currently use it
- example: one-line usage

See inventory.yaml for the master index.
"""
from .jsonl_store import JSONLStore

__all__ = ["JSONLStore"]
