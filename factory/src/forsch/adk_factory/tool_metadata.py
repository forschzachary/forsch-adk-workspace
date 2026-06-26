"""Tool metadata: the @tool decorator and ToolRegistry.

Every tool declares its own family, safety tier, client class, and Authsome
provider at the source via the @tool decorator. There is exactly ONE source of
truth per tool — the tool itself.

families.yaml is a GENERATED read-model the cockpit renders, never edited by
hand and never written by a heuristic.

Safety tiers (per EDIT 2 of the ADK Factory v2 plan):
    read_only   — no side effects. One-click wire. One-click scaffold.
    local_write — writes files / local state. Sandbox on test, confirm on first run.
    destructive — deletes, overwrites, or shells out arbitrarily. Denylist +
                  path allowlist + dry-run + human confirmation required.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional

# yaml is imported lazily — only generate_families_yaml() needs it.
# This keeps the decorator importable without pyyaml installed.

# -- safety tier ------------------------------------------------------------

SafetyTier = Literal["read_only", "local_write", "destructive"]

# -- denylist patterns for destructive tools --------------------------------

DESTRUCTIVE_DENYLIST: list[str] = [
    # rm variants: -rf, -fr, -r -f, --recursive --force, and rm -r /
    r"rm\s+(-[rf]+|-[rf]\s+-[rf]|--recursive\s+--force|--force\s+--recursive)\b",
    r"rm\s+-r\s+/",
    r"mkfs\b",
    r"dd\s+if=",
    r":\(\)\s*\{",
    # chmod -R 777 / and chmod 777 -R /
    r"chmod\s+(-R\s+777\s+/|777\s+-R\s+/)",
    r"truncate\b",
    r">\s*/dev/sd[a-z]",
    # git clean: -fdx, -xfd, -dfx (any order of f,d,x)
    r"git\s+clean\s+-[dfx]+",
    r"shutdown\b",
    r"reboot\b",
    r"halt\b",
    r"poweroff\b",
]

# -- the decorator ----------------------------------------------------------

@dataclass
class ToolMeta:
    """Metadata attached to every tool by the @tool decorator."""

    name: str
    family: str
    safety: SafetyTier = "read_only"
    client: str = ""
    auth: str = ""
    description: str = ""
    signature: str = ""
    source_file: str = ""
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_REGISTRY: dict[str, ToolMeta] = {}


def tool(
    *,
    family: str,
    safety: SafetyTier = "read_only",
    client: str = "",
    auth: str = "",
) -> Callable[[Callable], Callable]:
    """Decorator that declares a tool's family, safety, client, and auth provider."""
    def _decorator(fn: Callable) -> Callable:
        fq_name = f"{fn.__module__}.{fn.__qualname__}"
        sig = _format_signature(fn)
        src = _source_path(fn)
        meta = ToolMeta(
            name=fq_name,
            family=family,
            safety=safety,
            client=client,
            auth=auth,
            description=(fn.__doc__ or "").strip().split("\n")[0],
            signature=sig,
            source_file=src,
        )
        _REGISTRY[fq_name] = meta
        return fn
    return _decorator


def _format_signature(fn: Callable) -> str:
    try:
        sig = inspect.signature(fn)
        params = []
        for name, param in sig.parameters.items():
            if param.annotation is not inspect.Parameter.empty:
                ann = _type_name(param.annotation)
                params.append(f"{name}: {ann}")
            else:
                params.append(name)
        ret = ""
        if sig.return_annotation is not inspect.Parameter.empty:
            ret = f" -> {_type_name(sig.return_annotation)}"
        return f"{fn.__name__}({', '.join(params)}){ret}"
    except (ValueError, TypeError):
        return f"{fn.__name__}(...)"


def _type_name(ann: Any) -> str:
    if hasattr(ann, "__name__"):
        return ann.__name__
    return str(ann).replace("typing.", "").replace("NoneType", "None")


def _source_path(fn: Callable) -> str:
    try:
        return str(Path(inspect.getfile(fn)).resolve())
    except (TypeError, OSError):
        return ""


# -- registry ---------------------------------------------------------------

class ToolRegistry:
    """Collects all @tool-decorated functions and generates families.yaml."""

    @staticmethod
    def all_tools() -> dict[str, ToolMeta]:
        return dict(_REGISTRY)

    @staticmethod
    def by_family(family: str) -> list[ToolMeta]:
        return [m for m in _REGISTRY.values() if m.family == family]

    @staticmethod
    def by_safety(tier: SafetyTier) -> list[ToolMeta]:
        return [m for m in _REGISTRY.values() if m.safety == tier]

    @staticmethod
    def families() -> dict[str, dict]:
        result: dict[str, dict] = {}
        for meta in _REGISTRY.values():
            f = result.setdefault(meta.family, {
                "safety": meta.safety,
                "tools": [],
                "clients": set(),
                "auths": set(),
            })
            f["tools"].append(meta.name)
            if meta.client:
                f["clients"].add(meta.client)
            if meta.auth:
                f["auths"].add(meta.auth)
        for v in result.values():
            v["tools"] = sorted(v["tools"])
            v["clients"] = sorted(v["clients"])
            v["auths"] = sorted(v["auths"])
        return result

    @staticmethod
    def expand_wildcard(pattern: str) -> list[str]:
        if not pattern.endswith(".*"):
            return [pattern]
        family = pattern[:-2]
        return [m.name for m in _REGISTRY.values() if m.family == family]

    @staticmethod
    def generate_families_yaml() -> str:
        import yaml
        data: dict[str, dict] = {}
        for family_name, fam in ToolRegistry.families().items():
            data[family_name] = {
                "safety": fam["safety"],
                "tools": fam["tools"],
                "clients": fam["clients"],
                "auths": fam["auths"],
            }
        return yaml.dump(
            {"version": 1, "families": data},
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    @staticmethod
    def discover_and_register(package_paths: list[str]) -> int:
        before = len(_REGISTRY)
        for pkg_path in package_paths:
            _import_recursive(pkg_path)
        return len(_REGISTRY) - before


def _import_recursive(package_path: str) -> None:
    try:
        importlib.import_module(package_path)
    except ImportError:
        return
    mod = sys.modules.get(package_path)
    if mod is None or not hasattr(mod, "__path__"):
        return
    for p in mod.__path__:
        root = Path(p)
        if not root.is_dir():
            continue
        for py_file in sorted(root.rglob("*.py")):
            if py_file.name.startswith("_"):
                continue
            rel = py_file.relative_to(root.parent)
            mod_path = ".".join(rel.with_suffix("").parts)
            try:
                importlib.import_module(mod_path)
            except ImportError:
                pass
