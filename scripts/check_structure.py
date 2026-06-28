#!/usr/bin/env python3
"""Structural invariant checks for the Forsch ADK monorepo (R-STRUCT-1/7/11/12).

Adapted from PR #3's check_structure.py to the consolidated uv-workspace layout
(packages/*, agents/*, clusters/*). Each check is a function returning a list of
violation strings; main() exits 1 if any check produced violations.

Implemented:
  R-STRUCT-1  No embedded/indexed repo below root, and .gitignore must not
              re-hide soon-to-be-absorbed child paths.
                * `git ls-files -s | awk '$1==160000'` (gitlinks) is empty
                * `find -mindepth 2 \\( -name .git -o -name '.git_*' \\)` is empty
                  (catches a `.git` -> `.git_disabled` rename)
                * .gitignore contains no `components/`, `bridge/`, `agents/*` line
  R-STRUCT-7  Every dir containing a pyproject.toml is BOTH in the workspace
              members glob AND in the release-please manifests; and the reverse.
  R-STRUCT-11 Every intra-workspace dependency (forsch-adk-components / any other
              in-workspace dist name) in [project].dependencies carries an
              explicit `==` or `~=` constraint AND has a [tool.uv.sources] entry
              with `workspace = true`.
  R-STRUCT-12 (informational) one requires-python floor governs the workspace;
              members declaring a higher floor are reported (uv lock is the hard
              gate, this only surfaces drift early).

Exit 0 = all checks pass. Non-zero = at least one failure.
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)

ROOT_PYPROJECT = ROOT / "pyproject.toml"
RP_CONFIG = ROOT / "release-please-config.json"
RP_MANIFEST = ROOT / ".release-please-manifest.json"

# In-workspace distribution names: every dir with a pyproject's [project].name.
# Computed lazily in check_intra_dep_pins().


def fail(msg: str) -> None:
    print(f"  FAIL: {msg}", file=sys.stderr)


def _load_toml(p: Path) -> dict:
    return tomllib.loads(p.read_text())


def dirs_with_pyproject() -> set[str]:
    """Repo-relative dirs (under packages/, agents/, clusters/) that have a
    pyproject.toml — i.e. the *actual* members uv will resolve."""
    out: set[str] = set()
    for top in ("packages", "agents", "clusters"):
        base = ROOT / top
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / "pyproject.toml").exists():
                out.add(f"{top}/{child.name}")
    return out


def workspace_members_globs() -> list[str]:
    if not ROOT_PYPROJECT.exists():
        return []
    data = _load_toml(ROOT_PYPROJECT)
    return (
        data.get("tool", {})
        .get("uv", {})
        .get("workspace", {})
        .get("members", [])
    )


def glob_matches(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in globs)


# ── R-STRUCT-1 ──────────────────────────────────────────────────────────────
def check_no_embedded_repo() -> list[str]:
    v: list[str] = []
    # gitlinks (submodule-like indexed repos)
    out = subprocess.run(
        ["git", "ls-files", "-s"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        if line.split(" ", 1)[0] == "160000":
            v.append(f"gitlink (embedded repo) indexed: {line}")
    # nested .git / .git_* dirs below root
    found = subprocess.run(
        [
            "find", ".", "-mindepth", "2",
            "(", "-name", ".git", "-o", "-name", ".git_*", ")",
        ],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    for line in found.splitlines():
        if line:
            v.append(f"nested git dir present: {line}")
    # .gitignore must not re-hide absorbed child paths
    gi = ROOT / ".gitignore"
    if gi.exists():
        for ln in gi.read_text().splitlines():
            s = ln.strip()
            if s.startswith("#") or not s:
                continue
            if s in ("components/", "bridge/", "components", "bridge") or (
                s.startswith("agents/") and s not in ("agents/", "agents")
            ):
                v.append(f".gitignore re-hides absorbed child path: '{s}'")
    return v


# ── R-STRUCT-7 ──────────────────────────────────────────────────────────────
def check_members_match() -> list[str]:
    v: list[str] = []
    member_dirs = dirs_with_pyproject()
    globs = workspace_members_globs()
    if not globs:
        v.append("root pyproject has no [tool.uv.workspace] members glob")
        return v
    # every dir-with-pyproject is matched by the members glob
    for rel in sorted(member_dirs):
        if not glob_matches(rel, globs):
            v.append(f"dir with pyproject not covered by members glob: {rel}")

    # release-please manifests must list exactly the member dirs
    rp_paths: set[str] = set()
    if RP_MANIFEST.exists():
        rp_paths = set(json.loads(RP_MANIFEST.read_text()).keys())
    else:
        v.append(".release-please-manifest.json missing")
    cfg_paths: set[str] = set()
    if RP_CONFIG.exists():
        cfg = json.loads(RP_CONFIG.read_text())
        cfg_paths = set((cfg.get("packages") or {}).keys())
    else:
        v.append("release-please-config.json missing")

    only_members = member_dirs - rp_paths
    only_manifest = rp_paths - member_dirs
    for p in sorted(only_members):
        v.append(f"member dir missing from release-please manifest: {p}")
    for p in sorted(only_manifest):
        v.append(f"release-please manifest entry has no member dir: {p}")
    if cfg_paths != member_dirs:
        for p in sorted(member_dirs - cfg_paths):
            v.append(f"member dir missing from release-please-config packages: {p}")
        for p in sorted(cfg_paths - member_dirs):
            v.append(f"release-please-config package has no member dir: {p}")
    return v


# ── R-STRUCT-11 ─────────────────────────────────────────────────────────────
def _workspace_dist_names() -> set[str]:
    names: set[str] = set()
    for rel in dirs_with_pyproject():
        try:
            data = _load_toml(ROOT / rel / "pyproject.toml")
        except tomllib.TOMLDecodeError:
            continue
        name = data.get("project", {}).get("name")
        if name:
            names.add(name)
    return names


def _dep_name(token: str) -> str:
    # split off version / extras / markers
    for sep in ("==", "~=", ">=", "<=", ">", "<", "!=", "===", "[", ";", " "):
        idx = token.find(sep)
        if idx != -1:
            token = token[:idx]
    return token.strip()


def check_intra_dep_pins() -> list[str]:
    v: list[str] = []
    ws_names = _workspace_dist_names()
    for rel in sorted(dirs_with_pyproject()):
        p = ROOT / rel / "pyproject.toml"
        try:
            data = _load_toml(p)
        except tomllib.TOMLDecodeError as exc:
            v.append(f"{rel}/pyproject.toml parse error: {exc}")
            continue
        project = data.get("project", {})
        deps = project.get("dependencies", []) or []
        uv_sources = data.get("tool", {}).get("uv", {}).get("sources", {})
        for dep in deps:
            name = _dep_name(dep)
            if name in ws_names and name != project.get("name"):
                # must carry an explicit == or ~= pin
                if ("==" not in dep) and ("~=" not in dep):
                    v.append(
                        f"{rel}: intra-workspace dep '{dep}' lacks explicit ==/~= pin (R-STRUCT-11)"
                    )
                # must have a workspace source entry
                src = uv_sources.get(name)
                if not (isinstance(src, dict) and src.get("workspace") is True):
                    v.append(
                        f"{rel}: intra-workspace dep '{name}' missing [tool.uv.sources] workspace=true"
                    )
    return v


# ── R-STRUCT-12 (informational) ─────────────────────────────────────────────
def check_python_floor() -> list[str]:
    v: list[str] = []
    floor = None
    if ROOT_PYPROJECT.exists():
        floor = _load_toml(ROOT_PYPROJECT).get("project", {}).get("requires-python")
    for rel in sorted(dirs_with_pyproject()):
        try:
            rp = _load_toml(ROOT / rel / "pyproject.toml").get("project", {}).get(
                "requires-python"
            )
        except tomllib.TOMLDecodeError:
            continue
        if rp and floor and rp != floor:
            # surface drift only; uv lock is the hard gate
            print(f"  WARN: {rel} requires-python {rp!r} != root {floor!r}")
    return v


def main() -> int:
    checks = [
        ("R-STRUCT-1  no embedded repo / gitignore hygiene", check_no_embedded_repo),
        ("R-STRUCT-7  members glob == pyproject dirs == release-please", check_members_match),
        ("R-STRUCT-11 intra-dep == pins + workspace source", check_intra_dep_pins),
        ("R-STRUCT-12 single python floor", check_python_floor),
    ]
    failures = 0
    for label, fn in checks:
        print(f"--- {label} ---")
        viol = fn()
        if viol:
            for m in viol:
                fail(m)
            failures += 1
        else:
            print("  OK")

    print()
    if failures:
        print(f"RESULT: {failures} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
