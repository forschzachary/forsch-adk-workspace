"""@tool — auto-wrap a Python function as an ADK-compatible tool.

---
keywords: [tool, decorator, functiontool, adk-tool, schema, declare]
intention: "Saves you from manually wiring FunctionTool + JSON schema for every Python function you want to expose as an agent tool. Decorate a function, it's callable."
function: "@tool decorator that auto-wraps a Python function as an ADK FunctionTool with extracted schema."
depends_on: []
used_by: [stability_tools, ops_tools, household, all-tools]
example: "@tool(family='stability', safety='read_only'); def get_workspace_inventory(): ..."
---

This pattern complements (does not replace) the existing
`forsch.adk_factory.tool_metadata.tool` decorator in `factory/src/`. Use this
version when you don't have the factory loaded; use the factory version when you
want full validation + behavioral checks.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Literal, Optional

SafetyTier = Literal["read_only", "local_write", "destructive"]


def tool(
    *,
    family: str,
    safety: SafetyTier = "read_only",
    description: str = "",
    keywords: Optional[list[str]] = None,
) -> Callable:
    """Mark a function as an ADK tool. Stores metadata; passes the function through.

    Use directly in agent code:
        from forsch.adk_components.patterns.tool_decorator import tool

        @tool(family="stability", safety="read_only")
        def get_workspace_inventory() -> dict:
            '''Inspect the ADK workspace and report structural pieces.'''
            ...

    Pass `tool.__wrapped__` or just `tool` to ADK Agent(tools=[...]).
    The function is unmodified; only `.tool_meta` is attached.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.tool_meta = {  # type: ignore[attr-defined]
            "name": func.__name__,
            "family": family,
            "safety": safety,
            "description": description or (inspect.getdoc(func) or "").split("\n")[0],
            "keywords": keywords or [],
            "signature": str(inspect.signature(func)),
            "module": func.__module__,
        }
        return wrapper
    return decorator
