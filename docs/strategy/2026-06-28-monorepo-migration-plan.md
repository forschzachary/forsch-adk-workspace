# Monorepo Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Companion specs (read first):** [Repository & Git Discipline](2026-06-28-repository-and-git-discipline.md) (the *why* + invariants) and [Factory Contracts](2026-06-28-factory-contracts-open-requirements.md). This plan executes §8 of the strategy doc.

**Goal:** Dissolve the ~11 embedded git repos inside `forsch-adk-workspace` into one clean monorepo with a uv workspace, archive all non-graph fluff, and arm a server-side merge gate — without losing a single commit or breaking the live services.

**Architecture:** All work happens **on the box** (`/root/.hermes/workspace/adk`, the live source of truth) over SSH. The migration is staged on a branch, validated green, then the control plane is armed *last* (after the tree is fluff-free, so the bijection check can pass). Every destructive step is preceded by a verified backup and a human STOP checkpoint.

**Tech Stack:** git, git-subtree, `uv` workspaces (Astral), GitHub Actions + Repository Rulesets, release-please, pre-commit framework, systemd.

---

## ⚠️ EXECUTION RULES (read before Task 0)

1. **Run every git/file command ON THE BOX**, not the Mac: prefix with
   `ssh -i ~/.ssh/zachfleet_vps -o ConnectTimeout=6 root@100.120.21.13 '<cmd>'`. The box is the source of truth; the Mac is a mirror.
2. **`uv` is NOT on the non-interactive PATH.** Always invoke it as `/root/.local/bin/uv`.
3. **STOP checkpoints are mandatory.** Where you see **🛑 STOP**, halt, report state to the human, and wait for explicit "go" before proceeding. Never auto-proceed past a STOP.
4. **Fail closed.** If any "Expected" output does not match, STOP and report — do not improvise or continue. A surprise during a repo migration means the map is wrong.
5. **Never `rm` anything until Task 1's backup is verified.** Task 1 is a HARD GATE.
6. **Do not force-push, do not `reset --hard` the live tree, do not touch `agents/*` working dirs of running services** until Task 7 re-points them.
7. Work on branch `consolidate/monorepo` throughout; `main` stays untouched until Task 8.

---

## Task 0: Preconditions & tooling verification (read-only)

**Files:** none (verification only).

- [ ] **Step 1: Snapshot current parent state**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  echo "branch: $(git branch --show-current)" && \
  echo "ahead/behind origin/main: $(git rev-list --left-right --count origin/main...HEAD)" && \
  echo "dirty: $(git status --porcelain | wc -l)"'
```
Expected: `branch: main`, `ahead/behind origin/main: 0	7` (or larger ahead), `dirty: ~25`. If branch is not `main`, STOP.

- [ ] **Step 2: Verify required tooling exists (the earlier check was masked by a fallback — verify each cleanly)**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'for t in /root/.local/bin/uv /usr/lib/git-core/git-subtree; do [ -x "$t" ] && echo "OK $t" || echo "MISSING $t"; done; \
  for c in gh git-filter-repo unzip; do command -v $c >/dev/null 2>&1 && echo "OK $c" || echo "MISSING $c (fallback noted in plan)"; done'
```
Expected: `OK /root/.local/bin/uv`, `OK /usr/lib/git-core/git-subtree`. `gh`, `git-filter-repo`, `unzip` may be MISSING — that is fine; the plan uses REST/python fallbacks. Record which are missing.

- [ ] **Step 3: Confirm the control plane is absent (baseline for Task 8 acceptance)**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  echo "workflows: $(ls .github/workflows 2>/dev/null | wc -l)" && echo "uv.lock: $(ls uv.lock 2>/dev/null || echo NONE)"'
```
Expected: `workflows: 0`, `uv.lock: NONE`. (If a control plane already exists, STOP — the migration may be partially done.)

- [ ] **Step 4: Confirm GitHub auth path for the ruleset (Task 8 needs it)**

The ruleset is applied via the GitHub REST API. `gh` is likely absent on the box. Decide the auth path now:
- If `gh` is available on the **Mac**, Task 8's ruleset call runs from the Mac.
- Else, a `GITHUB_TOKEN` with `repo` + `administration:write` scope must be available. Verify with:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && [ -f .serve-env ] && grep -l GITHUB .serve-env >/dev/null 2>&1 && echo "token file present" || echo "NO token on box — use Mac gh"'
```
Record the chosen path. **🛑 STOP if neither `gh` (Mac) nor a scoped token is available** — the gate cannot be armed without it, and the gate is the point.

**Prerequisite the human must confirm before Task 8:** the **GitHub App** that will act as the control-plane code-owner reviewer (per strategy §7.x) must exist and be installed on the repo. If it does not exist yet, Tasks 0–7 can still run; Task 8's ruleset is armed with `require_code_owner_review` only once the App is ready. Flag this to the human now.

---

## Task 1: Full backup & per-child safety net (HARD GATE)

**Files:** creates `/root/adk-backups/` on the box.

> No work that deletes or rewrites anything may begin until every step here is verified. Every embedded child currently has **unpushed commits** and several are **dirty** — losing this is losing real work.

- [ ] **Step 1: Full tarball of the entire workspace (includes every child `.git`)**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'mkdir -p /root/adk-backups && \
  tar czf /root/adk-backups/adk-pre-monorepo-2026-06-28.tar.gz -C /root/.hermes/workspace adk && \
  ls -lh /root/adk-backups/adk-pre-monorepo-2026-06-28.tar.gz'
```
Expected: a file ~1–2 GB (workspace is 2.6G uncompressed; 72G free). **This tar is the authoritative rollback for the entire migration.**

- [ ] **Step 2: Verify the tar is readable and complete**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'tar tzf /root/adk-backups/adk-pre-monorepo-2026-06-28.tar.gz | grep -c "adk/components/.git/" && \
  tar tzf /root/adk-backups/adk-pre-monorepo-2026-06-28.tar.gz | grep -c "adk/agents/stability/.git/"'
```
Expected: both counts > 0 (the child `.git` dirs are inside the tar). If either is 0, the backup is incomplete — STOP.

- [ ] **Step 3: Commit each dirty child, then push every child to its remote; tag each `pre-monorepo`**

The children with unpushed work: components(+dirty), live-agent-graph(+2), bridge(+1,dirty), assistant(+3), brand(+2), build(+2), ops(+1), social(+2), stability(+2). Spikes/gradio-chat(dirty) and wow-guild(no remote) are handled in Steps 4–5.

For each child WITH a remote, run this procedure (substitute `<dir>` and `<ref>` from the table below):
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk/<dir> && \
  git add -A && (git diff --cached --quiet || git commit -m "chore: pre-monorepo snapshot of in-flight work") && \
  git tag -f pre-monorepo-2026-06-28 && \
  git push origin HEAD && git push -f origin pre-monorepo-2026-06-28'
```

| `<dir>` | current branch (`<ref>`) | disposition |
|---|---|---|
| `components` | `part1-workspace-resolver` | KEEP → `packages/adk-components` |
| `live-agent-graph` | `main` | KEEP → `packages/live-agent-graph` |
| `bridge` | `main` | KEEP → `bridge/` |
| `agents/assistant` | `main` | KEEP → `agents/assistant` |
| `agents/brand` | `main` | KEEP → `agents/brand` |
| `agents/build` | `main` | KEEP → `agents/build` |
| `agents/ops` | `main` | KEEP → `agents/ops` |
| `agents/social` | `main` | KEEP → `agents/social` |
| `agents/stability` | `main` | KEEP → `agents/stability` |
| `spikes/gradio-chat` | `main` | ARCHIVE (push for safety, then archive in Task 4) |
| `agents/wow-guild` | `main` | ARCHIVE, **NO REMOTE** → Step 5 |

Expected per child: `git push` succeeds (or "Everything up-to-date"), tag pushed.

> **⚠️ `bridge` remote push is INTENTIONALLY SKIPPED.** `bridge` commit `66e32af` contains a committed Discord bot token (`bridge.env.bak-…`); GitHub Push Protection blocks the push, and pushing it would expose the secret. **Do not push `bridge`'s remote and do not use any "allow secret" unblock URL.** `bridge`'s safety net is the verified tar (Task 1 Steps 1–2) plus its local snapshot commit. The token is scrubbed from `bridge`'s history in **Task 3 Step 0** before absorption — that is where it must be removed (else Task 8's monorepo push re-blocks on the same secret). **Rotate the Discord bot token in the Discord developer portal regardless** — a committed credential is compromised.

> **🛑 DECISION — `components` ref:** it is on `part1-workspace-resolver` (18 ahead of its own `main`). Confirm with the human that `part1-workspace-resolver` is the ref to absorb (it is the working branch with the patterns library). Record the answer; Task 3 uses it.

- [ ] **Step 4: Bundle `agents/wow-guild` (no remote — tar/push won't save it)**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk/agents/wow-guild && \
  git bundle create /root/adk-backups/wow-guild-2026-06-28.bundle --all && \
  git bundle verify /root/adk-backups/wow-guild-2026-06-28.bundle'
```
Expected: `The bundle records a complete history` / `is okay`. wow-guild is fluff (archived in Task 4) but its history is now recoverable from this bundle.

- [ ] **Step 5: Record every child HEAD sha (rollback reference) into the backup dir**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  for d in components live-agent-graph bridge spikes/gradio-chat agents/assistant agents/brand agents/build agents/ops agents/social agents/stability agents/wow-guild; do \
    echo "$d $(git -C $d rev-parse HEAD) $(git -C $d branch --show-current)"; done | tee /root/adk-backups/child-heads-2026-06-28.txt'
```
Expected: 11 lines, each `<dir> <sha> <branch>`. **🛑 STOP — HARD GATE.** Report the backup file sizes, the child-heads list, and the `components` ref decision. Do not proceed to Task 2 until the human confirms the safety net is complete.

---

## Task 2: Create the consolidation branch & clean the parent tree

**Files:** Modify `/root/.hermes/workspace/adk/.gitignore`; create branch `consolidate/monorepo`.

- [ ] **Step 1: Commit the parent's own dirty state so subtree has a clean tree**

`git subtree add` refuses a dirty index. Commit the parent's staged/untracked changes first.
Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  git checkout -b consolidate/monorepo && \
  git add -A && git commit -m "chore: snapshot parent working tree before monorepo consolidation"'
```
Expected: new branch `consolidate/monorepo`, one commit. (If "nothing to commit", that's fine — the tree was already clean.)

- [ ] **Step 2: Remove child-ignoring lines from `.gitignore` (subtree silently skips ignored paths)**

Inspect and edit:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && grep -nE "components|bridge|^agents/|live-agent-graph" .gitignore || echo "no child-ignoring lines"'
```
If any lines match a child path, remove exactly those lines (use an editor; do not blanket-truncate `.gitignore`). Then:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && git add .gitignore && git commit -m "chore: stop ignoring soon-to-be-absorbed child paths" || echo "no change"'
```
Expected: child paths no longer appear in `.gitignore`.

---

## Task 3: Absorb each KEEP child via git subtree (history-preserving)

**Files:** creates `packages/adk-components/`, `packages/live-agent-graph/`, keeps `bridge/`, `agents/{assistant,brand,build,ops,social,stability}/` as plain tracked dirs.

- [ ] **Step 0 (BRIDGE ONLY): scrub the committed secret from `bridge`'s history before absorbing it**

`bridge` carries a Discord token in `bridge.env.bak-pre-modelprefix-20260621-145317` across its history. Absorbing `bridge` via subtree would import that into the monorepo and **re-trigger push protection at Task 8**. Scrub it first. `git-filter-repo` is missing on the box — do this on the **Mac** (install with `brew install git-filter-repo` or `uv tool install git-filter-repo`), on a fresh clone, then use that scrubbed clone as the absorb source:
```bash
# On the Mac:
git clone /path/to/bridge-clone bridge-scrubbed   # or clone the box copy via ssh/rsync
cd bridge-scrubbed
git filter-repo --path bridge.env.bak-pre-modelprefix-20260621-145317 --invert-paths --force
git filter-repo --path-glob '*.env.bak*' --invert-paths --force   # belt-and-suspenders: drop all env backups
git log --all --oneline | wc -l                                    # history preserved, minus the secret blob
git log -p --all | grep -c 'Discord' || echo "token gone"          # expect: token gone
```
Then in Step 1/Step 3 below, use this scrubbed clone as the subtree `SRC` for `bridge` (not the box's in-place `bridge/`). Verify the token is absent in the absorbed tree before continuing. **The Discord token must already be rotated** (operator action). If the token still resolves anywhere in the scrubbed history, STOP.

> Procedure per child. Order is strict: (1) the in-place child dir must be REMOVED from the worktree first (an untracked child makes `git subtree add` fail "prefix already exists"), but we must absorb its history from a path that still has the `.git`. So we **move** the child aside, then subtree-add from the moved copy, then delete the moved copy.

- [ ] **Step 1: Define the absorb function (run once per session)**

For each KEEP child, run this exact sequence (substitute `SRC`, `DEST`, `REF`):
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'set -e; cd /root/.hermes/workspace/adk; \
  SRC=components; DEST=packages/adk-components; REF=part1-workspace-resolver; \
  mv "$SRC" "/root/adk-backups/_absorb_$(basename $SRC)"; \
  ASRC="/root/adk-backups/_absorb_$(basename $SRC)"; \
  git -C "$ASRC" checkout "$REF"; \
  COUNT=$(git -C "$ASRC" rev-list --count "$REF"); echo "source commits: $COUNT"; \
  git subtree add --prefix="$DEST" "$ASRC" "$REF"; \
  echo "=== VERIFY: total log grew by ~$COUNT ===" '
```
Expected: `git subtree add` prints "Added dir '<DEST>'"; no error. Record the subtree merge SHA (`git rev-parse HEAD`) for rollback.

- [ ] **Step 2: Verify history was preserved (do NOT trust `git log -- <prefix>`)**

`git log -- <prefix>` shows only the single "Add … from commit" line and looks identical to a squash. Use the real test:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  git subtree split --prefix=packages/adk-components -b _verify_components && \
  echo "reconstructed commits: $(git rev-list --count _verify_components)" && \
  git branch -D _verify_components'
```
Expected: `reconstructed commits` ≈ the source `COUNT` from Step 1 (history is present). If it shows 1, history was lost — STOP and restore from tar.

- [ ] **Step 3: Repeat Steps 1–2 for every KEEP child**

| SRC | DEST | REF |
|---|---|---|
| `components` | `packages/adk-components` | `part1-workspace-resolver` (per Task 1 decision) |
| `live-agent-graph` | `packages/live-agent-graph` | `main` |
| `bridge` | `bridge` | `main` |
| `agents/assistant` | `agents/assistant` | `main` |
| `agents/brand` | `agents/brand` | `main` |
| `agents/build` | `agents/build` | `main` |
| `agents/ops` | `agents/ops` | `main` |
| `agents/social` | `agents/social` | `main` |
| `agents/stability` | `agents/stability` | `main` |

After each, verify with Step 2 (substitute the DEST). Record each merge SHA.

- [ ] **Step 4: Confirm zero embedded repos remain among absorbed children**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  git ls-files -s | awk "\$1==160000{print}" | head && \
  find packages agents bridge -mindepth 2 -name .git -o -name ".git_*" 2>/dev/null | head'
```
Expected: both empty (no gitlinks, no nested `.git`). The moved originals live safely in `/root/adk-backups/_absorb_*` until Task 9.

---

## Task 4: Archive the fluff (annotated tag + remove)

**Files:** removes the no-graph dirs; creates `archive/*` tags.

> Proven archive pattern: tag the tree, then `git rm`. The bytes stay reachable forever via the tag. NO hand-rolled `_archived/` dir survives.

- [ ] **Step 1: Archive each fluff path**

For each fluff path, run (substitute `<path>` and a slug):
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  git tag -a archive/<slug>-2026-06-28 -m "pre-consolidation <path>" HEAD && \
  git rm -r --quiet --ignore-unmatch <path> && echo "archived <path>"'
```

Fluff paths (from strategy §9): `web_agents`, `agent_specs` *(see note)*, `graph`, `data`, `spikes`, `_archived_agents`, `_ios-shelby-reminders`, `preambles`, `CURRENT-STATE.md`, `DIRECTORY.md`, `GIT-DISCIPLINE.md`, and the stray agent dirs: `agents/{wow-guild,agent_logic_specialist,hubert,api_spawn_test,cookie_spawn_test,proxy_spawn_test,test_autospawn,test_ui_spawn,testbot,e2e_proof,e2e_proof_2026,raid_scheduler,guild_herald,guild_quartermaster,guild_treasurer,wow_guild_bot,wow_guild_helper}`.

> **⚠️ `agent_specs/` is NOT fluff yet** — it is the canonical runtime spine (R-STRUCT-4) until Task 6 unifies the registry. Do **not** archive `agent_specs/` here. It is listed in §9 as legacy only in the sense that its *location* may move; keep it until Task 6 explicitly handles it.

- [ ] **Step 2: Commit the archive sweep**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  git commit -m "chore: archive non-graph fluff (tags archive/*-2026-06-28)"'
```
Expected: one commit removing the fluff. **🛑 STOP** — report the list of archived paths and tags to the human for a sanity check before scaffolding. A wrongly-archived keeper is recoverable from its tag, but confirm now.

---

## Task 5: Lay down the uv workspace + enforcement scaffolding

**Files:** Create root `pyproject.toml`, per-package `pyproject.toml`, `scripts/check_bijection.py`, `scripts/check_structure.py`, `.pre-commit-config.yaml`, `.github/workflows/verify.yml`, `.github/workflows/release-please.yml`, `release-please-config.json`, `.release-please-manifest.json`, `.github/CODEOWNERS`, `repo_manifest.yaml`.

> Full file contents below. After this task the tree must be GREEN (workspace locks, bijection passes) so Task 8 can arm the gate.

> **ADOPT THE PROVEN REVIEWER (from PR #3 on `forsch-adk-workspace`).** The A2 agent already built and proved the **Path 2** control-plane gate: `.github/workflows/control-plane-review.yml` (the `control-plane-approved` status check, step-level path detection, self-hardening) + `.github/workflows/verify.yml` + `scripts/check_structure.py` + `scripts/check_bijection.py`. **Do NOT merge PR #3** (its checks target the *pre-migration* layout). Instead, pull those 4 files from PR #3's branch as the **starting point** for the steps below, then ADAPT them to the consolidated tree: (a) `check_bijection.py` must be the **graph-keyed** bijection from strategy §9 (set(agents/<x>)==graph agent nodes==registry keys + artifact-path existence) — PR #3's version is package-path/yaml-focused and is a *different* check; keep both concerns but the graph bijection is R-STRUCT-9; (b) `check_structure.py` updates to the `packages/*`,`agents/*`,`clusters/*` layout (R-STRUCT-1/7/11/12); (c) `verify.yml` and `control-plane-review.yml` carry over as-is (their trigger design is correct). After migration lands, PR #3 is closed as superseded.

- [ ] **Step 1: Root `pyproject.toml`** — create `/root/.hermes/workspace/adk/pyproject.toml`:

```toml
[project]
name = "forsch-adk-workspace"
version = "0.0.0"
requires-python = ">=3.11"

[tool.uv.workspace]
members = ["packages/*", "agents/*", "clusters/*"]
exclude = []

[tool.uv.sources]
forsch-adk-components = { workspace = true }
```

- [ ] **Step 2: Per-package `pyproject.toml`** — ensure each `packages/*` and `agents/*` has a `[project]` with `name`, `version` (annotated `# x-release-please-version`), `requires-python = ">=3.11"`, a `[build-system]` (hatchling), and — for agents — `dependencies = ["forsch-adk-components==<current components version>"]` plus `[tool.uv.sources] forsch-adk-components = { workspace = true }`. Discover the components current version first:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'grep -m1 "^version" /root/.hermes/workspace/adk/packages/adk-components/pyproject.toml'
```
Use that exact version in the agents' `==` pin (do NOT invent 1.4.0). If a member lacks a `pyproject.toml`, create a minimal one.

- [ ] **Step 3: Lock the workspace**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && /root/.local/bin/uv lock'
```
Expected: `uv.lock` created, resolution succeeds. If it fails on `requires-python` intersection (residual risk #2), the offending member needs a path-dependency carve-out — STOP and report which member.

- [ ] **Step 4: `scripts/check_bijection.py`** — create it (keyed on the live graph, both directions, per strategy §9):

```python
#!/usr/bin/env python3
"""Filesystem<->graph bijection + artifact-path existence check (R-STRUCT-9)."""
import json, sys, os, glob, re, subprocess, pathlib

ROOT = pathlib.Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip())
GRAPH = ROOT / "packages/live-agent-graph/agent-graph-v2.json"
if not GRAPH.exists():
    GRAPH = ROOT / "live-agent-graph/agent-graph-v2.json"  # pre-migration fallback
REGISTRY = ROOT / "packages/live-agent-graph/registry/agents/agents.yaml"

def agent_dirs():
    d = ROOT / "agents"
    return {p.name for p in d.iterdir() if p.is_dir()} if d.exists() else set()

def graph_agent_nodes(g):
    return {n["id"].split(":",1)[1] for n in g.get("nodes", [])
            if str(n.get("id","")).startswith("agent:")}

def registry_agents():
    import yaml
    data = yaml.safe_load(REGISTRY.read_text()) if REGISTRY.exists() else {}
    return set((data or {}).get("agents", {}).keys())

ANNOT = re.compile(r"\s*\(.*\)\s*$")
LOGICAL = re.compile(r"external dependency|LiteLLM|authsome|Discord|agents\.yaml group")

def artifact_paths_ok(g):
    bad = []
    for n in g.get("nodes", []):
        a = n.get("artifact")
        if not a or "/" not in a or LOGICAL.search(a):
            continue
        p = ANNOT.sub("", a).strip()
        if not (os.path.exists(ROOT / p) or glob.glob(str(ROOT / p))):
            bad.append(a)
    return bad

def main():
    g = json.loads(GRAPH.read_text())
    dirs, nodes, reg = agent_dirs(), graph_agent_nodes(g), registry_agents()
    errs = []
    if dirs != nodes:
        errs.append(f"agents/ dirs != graph agent nodes: only-dir={dirs-nodes} only-graph={nodes-dirs}")
    if nodes != reg:
        errs.append(f"graph nodes != registry keys: only-graph={nodes-reg} only-reg={reg-nodes}")
    bad = artifact_paths_ok(g)
    if bad:
        errs.append(f"artifact paths missing on disk: {bad}")
    if errs:
        print("BIJECTION FAIL:"); [print("  -", e) for e in errs]; sys.exit(1)
    print("BIJECTION OK"); sys.exit(0)

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Regenerate the graph, then run the bijection check**

Run:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk/packages/live-agent-graph && \
  /root/.local/bin/uv run python build_live_graph.py 2>&1 | tail -3 && \
  cd /root/.hermes/workspace/adk && /root/.local/bin/uv run python scripts/check_bijection.py'
```
Expected: `BIJECTION OK`. If it FAILs, the failing element is real fluff still present or a missing graph node — fix (archive or regenerate) until green. **The gate cannot be armed until this is green.**

- [ ] **Step 6: `.pre-commit-config.yaml`** — create it:

```yaml
repos:
  - repo: local
    hooks:
      - id: check-bijection
        name: filesystem<->graph bijection
        entry: /root/.local/bin/uv run python scripts/check_bijection.py
        language: system
        pass_filenames: false
      - id: check-structure
        name: structural invariants (R-STRUCT 1,7,11,12)
        entry: /root/.local/bin/uv run python scripts/check_structure.py
        language: system
        pass_filenames: false
      - id: uv-lock-check
        name: uv.lock fresh
        entry: /root/.local/bin/uv lock --check
        language: system
        pass_filenames: false
```
> `scripts/check_structure.py` implements R-STRUCT-1 (embedded repo: `git ls-files -s | awk '$1==160000'` + the disabling-name find), R-STRUCT-7 (members glob == dirs-with-pyproject), R-STRUCT-11 (intra-deps carry `==`). Write it following those exact mechanisms from strategy §7; keep each check a function returning a list of violations, `sys.exit(1)` if any. (This script is short enough to author directly from the §7 table.)

- [ ] **Step 7: `.github/workflows/verify.yml`** — the required CI check (job name **must** be `verify`):

```yaml
name: verify
on:
  pull_request:
  push: { branches: [main] }
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv lock --check
      - run: uv sync --locked --all-packages
      - run: uv build --all-packages
      - run: uv run python scripts/check_bijection.py
      - run: uv run python scripts/check_structure.py
      - run: uvx pre-commit run --all-files
      - run: uv run pytest -q
```

- [ ] **Step 8: release-please config + manifest + workflow, CODEOWNERS, repo_manifest.yaml**

Create `release-please-config.json` (`release-type: python`, `separate-pull-requests: true`, `include-component-in-tag: true`, `tag-separator: "-"`, one `packages{}` entry per `packages/*` and `agents/*`), `.release-please-manifest.json` seeded with each package's **current real version** (read from each `pyproject.toml` — do not invent), `.github/workflows/release-please.yml` (`googleapis/release-please-action@v4`, on `push: main`, `permissions: {contents: write, pull-requests: write}`), `.github/CODEOWNERS` (owner = the App, guarding `/.github/`, `.pre-commit-config.yaml`, `scripts/check_*.py`, `agent_specs/agents.yaml`, `release-please-config.json`, `repo_manifest.yaml`, `factory/`), and `repo_manifest.yaml` (the closed allowlist from strategy §9). Use the exact field values listed in strategy §7.x and §7.y.

- [ ] **Step 9: Commit the scaffolding**

```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && git add -A && \
  git commit -m "feat: uv workspace + enforcement scaffolding (verify, release-please, bijection, pre-commit)"'
```

---

## Task 6: Registry unification (spine + derived overlay)

**Files:** Modify `packages/live-agent-graph/build_live_graph.py` to read `agent_specs/agents.yaml` as the spine; demote the control-surface registry to a presentation overlay.

- [ ] **Step 1: Make the graph builder read the spine for the agent SET**

Edit `build_live_graph.py` so the set of agents comes from `agent_specs/agents.yaml` (runtime truth), with the control-surface registry supplying only presentation fields (`role`, `group`, display model). Regenerate and re-run the bijection check (Task 5 Step 5). Expected: `BIJECTION OK`, and `set(graph nodes) ⊆ set(agent_specs keys)`.

- [ ] **Step 2: Commit**

```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && git add -A && \
  git commit -m "feat: graph reads agent_specs spine; control-surface registry is presentation overlay (R-STRUCT-4)"'
```

---

## Task 7: Re-point the runtime (systemd + GitOps deploy)

**Files:** systemd units (discover via `systemctl cat`), `/root/.hermes/deploy.sh` (new).

> **🛑 STOP before this task** — it touches live services. Confirm with the human that a brief restart is acceptable, and do it when traffic is low.

- [ ] **Step 1: Discover the units and their path assumptions**

```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'systemctl cat live-agent-graph.service adk-api.service 2>/dev/null | grep -E "ExecStart|WorkingDirectory|Environment|EnvironmentFile"'
```
Record every path that points at the old layout (e.g. `…/adk/live-agent-graph/serve.py` → now `…/adk/packages/live-agent-graph/serve.py`) and `FORSCH_ADK_WORKSPACE`.

- [ ] **Step 2: Update the unit paths to the new layout, `daemon-reload`, restart, verify health**

Edit the units (or their `EnvironmentFile`) to the `packages/…` paths. Then:
```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'systemctl daemon-reload && \
  systemctl restart live-agent-graph.service && sleep 3 && \
  curl -s http://127.0.0.1:8888/factory-overview | head -c 200'
```
Expected: a JSON response with `reachable: true`. If the service fails, restore the unit files from the Task 1 tar and STOP.

- [ ] **Step 3: Install the pull-based deploy script (box authors zero commits — R-GATE-2)**

Create `/root/.hermes/deploy.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd /root/.hermes/workspace/adk
git fetch origin main
if [ -n "$(git rev-list origin/main..HEAD)" ]; then
  echo "REFUSING: box has local commits origin/main lacks (R-GATE-2 violation)"; exit 1
fi
git reset --hard origin/main
/root/.local/bin/uv sync --frozen
# box-only smoke as POST-deploy verification:
/root/.local/bin/uv run python packages/live-agent-graph/smoke_check.py || { echo "SMOKE FAILED — rolling back"; git reset --hard HEAD@{1}; exit 1; }
systemctl restart live-agent-graph.service
echo "deployed $(git rev-parse --short HEAD)"
```
Make executable (`chmod +x`). Do **not** wire the webhook trigger yet — that is part of arming the gate (Task 8).

---

## Task 8: Arm the control plane (LAST — tree must be green)

**Files:** GitHub ruleset (remote), branch `main`.

> **🛑 STOP before this task.** Arming the gate on a not-yet-green tree, or before the `verify` workflow has run once, **permanently blocks all merges** (residual risk: the required check would be "pending forever"). Confirm: (a) Task 5 Step 5 is green, (b) the App reviewer exists (Task 0 prerequisite).

- [ ] **Step 1: Push the consolidation branch and open a PR to main**

```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && git push origin consolidate/monorepo'
```
Open a PR `consolidate/monorepo → main` (via `gh` on the Mac or the web UI). **The `verify` workflow runs here for the first time.**

- [ ] **Step 2: Confirm `verify` runs and goes GREEN on the PR**

Wait for the PR's `verify` check. Expected: green. If red, read the failing step, fix on the branch, push, re-run. **Do not arm the ruleset while `verify` is red.**

- [ ] **Step 3: Merge the PR (this is the migration landing on `main`)**

Merge via the UI/`gh`. Expected: `main` now has the monorepo. The box's `deploy.sh` (Task 7) can now pull it.

- [ ] **Step 4: Create the ruleset (only AFTER `verify` has run green at least once)**

From the auth path chosen in Task 0 (**gh-on-Mac**, authenticated as `forschzachary`), POST the ruleset to `/repos/forschzachary/forsch-adk-workspace/rulesets` with **Path 2** (the implemented design — pure status checks, no CODEOWNERS): `bypass_actors: []`, `pull_request` (`required_approving_review_count: 0`, `dismiss_stale_reviews_on_push: true`, **no** `require_code_owner_review` — the control-plane gate is a status check, not a code-owner review), `required_status_checks` (`strict_required_status_checks_policy: true`, contexts: **`["verify", "control-plane-approved"]`**), `non_fast_forward`, `deletion`, and required linear history. Both checks must have run at least once on the migration PR before they can be required (the ordering gotcha applies to BOTH).

- [ ] **Step 5: EMPIRICAL acceptance — the gate must actually bind**

```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'cd /root/.hermes/workspace/adk && \
  git fetch origin && git push --dry-run origin HEAD:main 2>&1 | tail -3'
```
Expected: **REJECTED** (protected branch / PR required). Also confirm `GET /repos/forschzachary/forsch-adk-workspace/rules/branches/main` returns a **non-empty** array. If a direct push is still ACCEPTED, the gate is not armed — STOP and report. **This test, not the doc, is the proof the system is bulletproof.**

- [ ] **Step 6: Open a throwaway failing PR to prove the gate blocks**

Create a branch that breaks the bijection (e.g. `mkdir agents/zzz_test` with no graph node), push, open a PR. Expected: `verify` is RED and the merge button is blocked. Delete the branch after. This proves the gate rejects bad changesets end-to-end.

---

## Task 9: Archive old remotes & clean up absorb staging

**Files:** GitHub repo settings (archive); `/root/adk-backups/_absorb_*`.

> **🛑 STOP before this task** — archiving remotes is the point of no easy return for the old repos. Confirm the migration is healthy (services up, gate armed, a week of stability if desired) first.

- [ ] **Step 1: Archive each absorbed repo's GitHub remote (read-only mirror, never delete)**

For each of `forsch-adk-components`, `live-agent-graph`, `forsch-adk-bridge`, `forsch-agent-{assistant,brand,build,ops,social,stability}`, set the GitHub repo to **Archived** (Settings → Archive, or REST `PATCH /repos/{owner}/{repo}` `{"archived": true}`). Do **not** delete.

- [ ] **Step 2: Remove the absorb-staging copies once everything is confirmed green**

```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 'ls /root/adk-backups/_absorb_* -d && echo "delete these only after final confirmation"'
```
Keep the tar (`adk-pre-monorepo-2026-06-28.tar.gz`) and the `wow-guild` bundle indefinitely. **🛑 STOP** — get explicit human confirmation before deleting the `_absorb_*` staging dirs.

---

## Rollback reference (tiered)

- **A single child absorption (before Task 8 merge):** `git revert -m 1 <merge-sha>` on `consolidate/monorepo`. ⚠️ Reverting a subtree merge is a footgun — to re-absorb that child later you must first revert the revert. Prefer restoring from staging.
- **Whole migration (any time before Task 9 cleanup):** restore the authoritative tar:
  ```bash
  ssh … 'cd /root/.hermes/workspace && mv adk adk-broken-$(date +%s) && tar xzf /root/adk-backups/adk-pre-monorepo-2026-06-28.tar.gz'
  ```
  then `daemon-reload` + restart services. This restores every child `.git` and the exact pre-migration state.
- **`wow-guild`:** `git clone /root/adk-backups/wow-guild-2026-06-28.bundle`.
- **Old remotes:** archived (Task 9), never deleted — un-archive to recover.

---

## Self-review coverage

Maps to strategy §8: Task 1 = P0; Tasks 2–4 = P1/P2 (absorb + archive); Task 5 = scaffolding (the uv/CI/release-please layer §3/§7); Task 6 = P4 (registry unification); Task 7 = P3 (re-point) + GitOps; Task 8 = P0.5 control-plane apply+verify (correctly placed LAST, per residual risk #4); Task 9 = P5 (archive remotes). The empirical acceptance tests from the spec are Task 8 Steps 5–6. Every destructive step is gated by the Task 1 backup and a human STOP.
