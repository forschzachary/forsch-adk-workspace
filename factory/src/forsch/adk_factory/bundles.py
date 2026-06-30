"""Collapse per-agent bundle references + explicit tools into one flat tool list.

Generation-time only: the runnable ``agent.py`` never knows bundles existed.
This is a refactor of *declaration*, not behavior — an agent's expanded tool set
is exactly the set it declared before bundles. Fail loud on any ambiguity: a
silently-wrong tool set is the bug class this whole workspace exists to kill.
"""

from __future__ import annotations

from typing import Optional, Union


class BundleError(ValueError):
    """Raised on an unknown bundle, both ``only`` + ``exclude`` on one ref, or a
    filter naming a tool that is not a member of the bundle."""


def _bundle_tools(bundle_def) -> list[str]:
    """Return a bundle definition's tool list, accepting either a raw dict
    (``{"tools": [...]}``) or a ``ToolBundle`` pydantic model."""
    if hasattr(bundle_def, "tools"):
        return list(bundle_def.tools or [])
    return list((bundle_def or {}).get("tools", []) or [])


def _coerce_ref(ref) -> tuple[str, Optional[str], list[str]]:
    """Normalize a bundle reference (str | dict) -> (name, mode, names).

    ``mode`` is ``'only'`` | ``'exclude'`` | ``None``.
    """
    if isinstance(ref, str):
        return ref, None, []
    if not isinstance(ref, dict) or "bundle" not in ref:
        raise BundleError(
            f"bundle ref must be a name or a mapping with a 'bundle:' key, got {ref!r}"
        )
    name = ref["bundle"]
    has_only, has_excl = "only" in ref, "exclude" in ref
    if has_only and has_excl:
        raise BundleError(f"bundle ref {name!r}: only/exclude are mutually exclusive")
    if has_only:
        return name, "only", list(ref["only"] or [])
    if has_excl:
        return name, "exclude", list(ref["exclude"] or [])
    return name, None, []


def expand_bundles(
    tools: Optional[list[str]],
    bundles: Optional[list[Union[str, dict]]],
    bundle_defs: dict,
) -> list[str]:
    """Collapse bundle refs + explicit tools into one flat, de-duped, ordered list.

    Args:
        tools: the agent's explicit ``tools:`` list (may be None/empty).
        bundles: the agent's ``bundles:`` refs — each a bundle name (str) or a
            mapping ``{bundle: <name>, only|exclude: [...]}``.
        bundle_defs: the manifest's ``tool_bundles`` map (name -> dict|ToolBundle).

    Ordering (locked, plan §1.3): bundle tools first, in the order bundles are
    declared, each bundle's tools in the bundle's own ``tools:`` order after that
    ref's ``only``/``exclude`` filter; then explicit ``tools:`` appended. De-dupe
    preserves first occurrence.

    Raises:
        BundleError: unknown bundle name; ``only`` + ``exclude`` on one ref; or a
            filter that names a tool not in the bundle (catches typos + drift).
    """
    out: list[str] = []
    for ref in (bundles or []):
        name, mode, names = _coerce_ref(ref)
        if name not in bundle_defs:
            raise BundleError(
                f"unknown bundle {name!r} (have: {sorted(bundle_defs)})"
            )
        bundle_tools = _bundle_tools(bundle_defs[name])
        bundle_set = set(bundle_tools)
        for n in names:
            if n not in bundle_set:
                raise BundleError(
                    f"bundle ref {name!r} {mode} names {n!r} which is not in the bundle"
                )
        if mode == "only":
            keep = set(names)
            bundle_tools = [t for t in bundle_tools if t in keep]
        elif mode == "exclude":
            drop = set(names)
            bundle_tools = [t for t in bundle_tools if t not in drop]
        out.extend(bundle_tools)
    out.extend(tools or [])

    seen: set[str] = set()
    deduped: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped


def validate_bundles(manifest) -> None:
    """Run ``expand_bundles`` for every agent, surfacing ``BundleError``s early.

    A bad ``only:`` typo or an unknown bundle reference should block before any
    render. Pure — no I/O. Raises the first ``BundleError`` it hits.
    """
    bundle_defs = manifest.tool_bundles
    for aid, spec in manifest.agents.items():
        try:
            expand_bundles(spec.tools, spec.bundles, bundle_defs)
        except BundleError as e:
            raise BundleError(f"agent {aid!r}: {e}") from e
