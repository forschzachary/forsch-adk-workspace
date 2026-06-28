# Repository & Git Discipline — Forsch ADK Workspace

| | |
|---|---|
| **Status** | **HARDENED** — proven-methods-only; CI is a REQUIRED server-side gate from day one |
| **Date** | 2026-06-28 |
| **Author** | Claude (Opus 4.8) + operator; hardened by an 18-agent adversarial workflow that empirically tested every claim on the live box |
| **Canonical repo** | `github.com/forschzachary/forsch-adk-workspace` |
| **Canonical CI check name** | `verify` |
| **Supersedes** | The embedded-repo topology (11 nested `.git` dirs measured on the box) |
| **Downstream of this** | The agent-factory pattern-contracts spec (lands only after this migration) |

> ⚠️ **REALITY WARNING.** As of this writing the control plane below is **DESIGNED but NOT YET APPLIED**. Empirical checks on the live box proved: **zero** rulesets, **zero** branch protection, **zero** `.github/workflows`, **no** `uv.lock`, **no** bijection script, **11** embedded `.git` dirs, and the parent repo **7 commits ahead of origin with a dirty tree**. A direct `git push` to `main` is currently **ACCEPTED**. Migration phase **P0.5** applies and re-verifies this control plane. **Nothing in this document is load-bearing until P0.5 passes its empirical tests.** Trust the `git push --dry-run` rejection test, not this prose.

---

## 0. The acceptance test (the one principle)

**If the operator ever has to think about git topology, the system has failed.** The operator has hit "your git is a mess" ~10 times. The goal is git organization that is **invisible** (intent via UI buttons or plain-English-to-an-agent, never raw git) and **self-enforcing** (discipline in tooling, never in human memory). This is **load-bearing for the operator's business.**

A second principle the operator added: **NO FLUFF.** The repo contains *only* what is visible on the live agent graph — clusters and their interface/router/agent/tool/datasource nodes, plus the shared library that backs them. Everything else is archived out (§9).

---

## 1. The problem (empirically grounded)

### 1.1 Root cause: embedded repositories (measured)

The monorepo `forsch-adk-workspace` already exists (box `/root/.hermes/workspace/adk`, branch `main`). It physically contains **11 embedded git repos** (own `.git`, own remotes, **no** `.gitmodules`), confirmed by `find -mindepth 2 -name .git`:

```
components/  live-agent-graph/  bridge/  spikes/gradio-chat/
agents/{assistant, brand, build, ops, social, stability, wow-guild}
```

Git cannot see inside an embedded repo — the parent cannot diff, lint, or atomically commit its children. On disk it looks unified; to git it is fragmented. Two hazards measured during hardening:

- **`agents/wow-guild`** has **no origin remote** — it needs a new remote *and* a `git bundle` before it can be safely removed (it is also fluff; see §9).
- **`components`** is checked out on branch **`part1-workspace-resolver`** (18 commits ahead of its own `main`, which is 7 behind `origin/main`). **The absorb ref must be a conscious operator choice** — absorbing the wrong ref passes the embedded-`.git` check while importing the wrong tree.
- This Mac mirror contains **only** `live-agent-graph/` (no sibling `agents/`, `components/`, `bridge/`). Any path-resolving check must run from the **monorepo root**, never from inside `live-agent-graph/`.

### 1.2 Symptom A — the dual registry (real, current bug)

`agent_specs/agents.yaml` (parent-owned, the ADK **runtime** manifest) vs `live-agent-graph/registry/agents/agents.yaml` (child-owned, the **control-surface** registry, the *only* thing `build_live_graph.py` reads). A spawned agent lands in the runtime registry but not the control-surface one, so it *runs but is invisible to the graph*. You cannot make those two writes atomic across two git repos. **The dual-registry bug is a symptom of the embedded-repo split.**

### 1.3 Symptom B — sync drift (measured) + the source-of-truth inversion

The box parent repo was measured **7 commits ahead of origin, unpushed, dirty tree**. The old discipline (box MEMORY.md) was *"the box is the source of truth and pushes to origin; Mac mirrors via reset --hard."* **That model is the bug.** The hardened model (proven GitOps, §2 / §8):

> **origin (GitHub) is the single source of truth.** CI gates on GitHub via a required ruleset check on `main`. The **box is a PULL-based deploy target** that pulls merged commits and runs box-only smoke as *post-deploy* verification (rollback on failure). **The box authors ZERO commits.** The Mac mirror pulls `--ff-only`.

This inversion makes the measured 7-ahead drift *unrepresentable*.

### 1.4 The misconception that drives the mess

> "To version components and agents independently, I need separate repos." **False, and load-bearing.** One repo holds many packages, each independently versioned and released via tags. Separate repos are warranted only when a component lives a life *outside* this system — and even then the consumer depends on a *published version*, never an embedded `.git` dir.

---

## 2. Principles

1. **Invisible.** Intent via UI buttons / plain-English-to-an-agent. No raw git for structure, ever.
2. **Self-enforcing — server-side.** Discipline lives in **(a)** a GitHub **Repository Ruleset** on `main` (required status check `verify` + required PR + block force-push + restrict deletions + linear history + **EMPTY bypass list**), and **(b)** the **pre-commit framework** for *fast local feedback only*. Local hooks are **NOT** the gate — `git commit --no-verify` skips any local hook and cannot reach GitHub's runner. The gate is server-side and re-runs the identical scripts on GitHub. The **empty bypass list** is what makes the gate bind the admin operator too.
3. **One source of truth.** One repo, one remote, atomic commits across the whole system; origin canonical (§1.3).
4. **Independent versions, shared history.** Semver per package + git tags. No repo split.
5. **`project.md` is the contract.** One required file per versionable unit. It already drives the UI (`handoff_pct` → tab %); it now also gates git.
6. **No fluff.** Filesystem ⟺ graph bijection (§9), enforced both directions.

---

## 3. Target topology (uv workspaces — confirmed proven)

One repository. Embedded repos are **dissolved in** via `git subtree` (history preserved). Package boundaries become *directories with their own `pyproject.toml`*. Tooling: **Astral `uv` workspaces** (verified on box at uv 0.11.23; pin `uv>=0.8` in CI/box env).

```
forsch-adk-workspace/                 ← ONE repo, ONE remote, origin canonical
├── packages/
│   ├── adk-components/  pyproject (name=forsch-adk-components, version 0.1.0)  ← shared library
│   └── live-agent-graph/  pyproject                                            ← control surface app
├── agents/<id>/        pyproject (name=agent-<id>) + project.md                ← versioned units
├── clusters/<name>/    cluster.yaml (pins) + project.md [+ pyproject]          ← consumers (UI tabs)
├── agent_specs/agents.yaml           ← single canonical runtime registry (the spine)
├── .github/workflows/{verify.yml, release-please.yml}   ← the server-side gate + version-out
├── .github/CODEOWNERS                ← guards the control-plane files
├── .pre-commit-config.yaml           ← fast local feedback (framework-managed)
├── release-please-config.json + .release-please-manifest.json
├── scripts/check_bijection.py        ← the no-fluff linter
├── repo_manifest.yaml                ← closed allowlist of non-node infra (§9)
└── uv.lock                           ← ONE root lockfile resolving all members
```

### 3.1 Exact `uv` config

**Root `pyproject.toml`** (virtual root, never published):

```toml
[project]
name = "forsch-adk-workspace"
version = "0.0.0"
requires-python = ">=3.11"          # ONE floor for ALL members (workspace intersection)

[tool.uv.workspace]
members = ["packages/*", "agents/*", "clusters/*"]   # clusters/* IS in the glob — see below
exclude = ["spikes/*"]

[tool.uv.sources]
forsch-adk-components = { workspace = true }
live-agent-graph      = { workspace = true }
```

> **Critical correction (proven):** the members glob **must** include `clusters/*`. A dir with a `pyproject.toml` *outside* the glob is invisible to the lock gate — a test cluster with an impossible dep `urllib3>=99999` passed `uv lock --check` (rc 0) because `members=[packages/*,agents/*]` never saw it. A WARN-level CI assertion confirms `{dirs containing pyproject.toml} == {glob-matched members}` (invariant **R-STRUCT-7**).

**An agent member** `agents/shelby/pyproject.toml` (depends on the shared lib):

```toml
[project]
name = "agent-shelby"
version = "2.1.0"                                    # # x-release-please-version
requires-python = ">=3.11"
dependencies = ["forsch-adk-components==1.4.0"]      # REAL == pin (ships into the wheel) — R-STRUCT-11
[tool.uv.sources]
forsch-adk-components = { workspace = true }          # in-repo dev → editable local copy
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

> **Dist-name + wheel-pin facts (proven, uv#9811):** `uv build` ships the `[project].dependencies` line **verbatim** into the wheel's `Requires-Dist` and **strips** the `{ workspace = true }` marker. A bare-named intra-dep ⇒ an *unconstrained* dist (silent: an external consumer of `agent-shelby` gets `>=…` not the exact tested `==1.4.0`). Therefore every intra-workspace dep carries an explicit `==`/tight `~=` constraint. The dependency token is **`forsch-adk-components`**, never `adk-components` (a name mismatch hard-fails uv with "Package metadata name does not match").

---

## 4. Human surfaces (zero memorization) + the single contract

The operator never recalls a command. Three surfaces, all routing through one entry point; the CLI is *plumbing for buttons and agents*, not hand-operated.

| Surface | Operator action | Underneath |
|---|---|---|
| **A — UI buttons** | clicks `+` tab, `+ New interface/router` | serve.py endpoint → factory CLI → commit |
| **B — plain English to an agent** | "make an agent that tracks invoices"; "ship shelby" | agent maps intent → factory CLI → commit |
| **C — backstop** | (nothing) | pre-commit hook blocks a malformed change locally; the ruleset blocks it server-side |

### 4.1 The contract verbs

| Verb | Intent | Git effect (invisible) |
|---|---|---|
| `factory new-agent <id> …` | create an agent | scaffold + `project.md` + register + Conventional Commit |
| `factory new-cluster <name>` | create a consumer | scaffold + `project.md` + commit |
| `factory release <unit> …` | **start a version-out** | emits a scoped Conventional Commit (`feat(<unit>): …`) **and** runs `uv lock` + stages `uv.lock` in the same commit. **It no longer edits `pyproject.toml` or runs `git tag`** — release-please derives the bump and creates the tag server-side (§5, §7.y). `uv version --bump` exists as a manual emergency override only. |
| `factory ship <cluster>` | deploy a consumer | pins versions + triggers the pull-based deploy |

**Invariant:** every structural git mutation is produced by a `factory` verb or rejected by the gate. No supported path hand-edits topology.

### 4.2 The flow is ASYNC (consequence of the gate)

Because merge is gated server-side (§7.x), a verb's real git effect is `branch → commit → push → open PR → await verify (+ code-owner review on control-plane) → auto-merge → box pulls + deploys`. So:

- A verb returns a **tracking handle (PR/branch), not a finished unit.** The UI shows **queued → verifying → merged → live**, never "exists now." Pretending the agent exists the instant you click is exactly the lie that erodes trust.
- Any orchestration that scaffolds a unit and then *uses* it must treat **"pending merge/deploy" as a first-class state** and await it. (A lead that spawns then immediately calls the new agent will otherwise race the gate.)
- Every verb carries an explicit **compensating action** (delete branch, close PR, drop the staged graph node) so a failed/abandoned click cleans itself up deterministically — no orphan branches. (This is the `undo()` of the Command pattern; see the factory-contracts doc.)

---

## 5. Versioning model ("version out", proven)

- **"Version out" = merge the release PR** (one click). release-please watches `main`, derives the semver bump from **Conventional Commits**, and on merge of its auto-opened release PR creates tag `<component>-vX.Y.Z` + a GitHub Release **server-side**. The operator never runs `git tag`.
- `[project].version` is the static source of truth, annotated `# x-release-please-version`, read by `uv`. Bumps are **derived, never hand-chosen**.
- **Clusters pin** in `cluster.yaml requires:`; that YAML is the human/UI contract and is *checked against* `pyproject.toml` (not a second source of truth) by **R-STRUCT-3**.
- **External reuse (operator confirmed wanted)** — proven install (verified in a scratch venv, uv 0.11.6), inline-URL form:

  ```bash
  uv add 'forsch-adk-components @ git+https://github.com/forschzachary/forsch-adk-workspace#subdirectory=packages/adk-components' --tag adk-components-v1.4.0
  ```
  > A git **tag name has zero connection** to the installed PEP 440 version — the install gets whatever `pyproject` declares at that commit. **R-STRUCT-10** enforces `tag <unit>-vX.Y.Z` ⇒ commit's `pyproject.version == X.Y.Z`, closing the "tag says 1.4.0, installs 0.1.0" gap.

---

## 6. The `project.md` contract

One required file per versionable unit. It carries **only contract fields** — the things that legitimately gate git. **Runtime fields live out of git entirely** (see below).

```yaml
---
name: shelby
kind: cluster            # agent | cluster | package
version: 2.1.0           # MUST equal pyproject [project].version (R-STRUCT-5)
owner: forsch
depends_on:              # pinned; every entry resolves (R-STRUCT-3)
  forsch-adk-components: "==1.4.0"
---
```

> **Contract vs runtime split (forced by R-GATE-2).** `status` (blank→building→built→live) and `handoff_pct` (the UI tab %) change constantly during normal operation. They **cannot** live in the gated `project.md`: every status tick would become a PR round-trip — absurd churn that tempts `--no-verify`. And the box authors **zero** commits (R-GATE-2), so it can't write them to git at all. Runtime state lives in the **non-git runtime store** the control surface already owns (serve.py state / the `/pulse` layer that drives reachable-vs-live). `project.md` is contract; the runtime layer is state; R-STRUCT-5 then guards version alone — which is all you actually want gated.

> All members share **one Python floor** (`>=3.11`) at the workspace root (uv takes the intersection). A member needing a different floor *leaves the workspace* as a `uv` path dependency. Workspaces also assume non-conflicting third-party deps (one shared venv); a genuine conflict forces a path-dependency carve-out. `release-please` / `uv version --package` is the **single writer** of versions, so `pyproject` and `project.md` cannot drift in the first place (R-STRUCT-5 is defense-in-depth).

---

## 7. Enforcement — invariants

Two tiers: **FAIL** blocks commit (locally) and merge (server-side); **WARN** reports. All run identically in the pre-commit framework *and* in the `verify` GitHub Actions job.

| ID | Sev | Rule | Proven mechanism |
|---|---|---|---|
| **R-STRUCT-1** | FAIL | No embedded/indexed repo below root; `.gitignore` must not contain `components/`, `bridge/`, `agents/*` | `git ls-files -s \| awk '$1==160000'` empty **AND** each tracked subdir's `git rev-parse --git-dir` == root **AND** `find -mindepth 2 \( -name .git -o -name '.git_*' \)` empty (catches a `.git`→`.git_disabled` rename) |
| **R-STRUCT-2** | FAIL | Every versionable unit has a valid `project.md` (§6) | parse frontmatter; assert fields + types |
| **R-STRUCT-3** | FAIL | Every `depends_on`/`requires` pin resolves to a real package version or pushed tag; YAML pins match `pyproject` | resolve against versions + `git tag` |
| **R-STRUCT-4** | FAIL | One canonical runtime registry: `agent_specs/agents.yaml` is the spine; control-surface registry ⊆ spine | set-compare IDs |
| **R-STRUCT-5** | FAIL | `pyproject.version == project.md version`; single writer | string-compare; writer = release-please |
| **R-STRUCT-6** | WARN | `main` has no unpushed/uncommitted drift (informational — box authors zero commits) | `git status` / ahead-count |
| **R-STRUCT-7** | FAIL | Every dir with a `pyproject.toml` is in **both** `release-please` manifests **and** the workspace members glob | set-compare dirs vs config |
| **R-STRUCT-8** | FAIL | Every commit reaching `main` is a valid Conventional Commit with a recognized package scope | commitlint (precondition for safe bump-derivation) |
| **R-STRUCT-9** | FAIL | **Filesystem⟺graph bijection (both directions)** (§9) | `scripts/check_bijection.py` keyed on `agent-graph-v2.json` node ids |
| **R-STRUCT-10** | FAIL | Tag `<unit>-vX.Y.Z` ⇒ commit `pyproject.version == X.Y.Z`; dist name `forsch-adk-components` | tag→version check |
| **R-STRUCT-11** | FAIL | Every intra-workspace dep has an explicit `==`/`~=` in `[project].dependencies` *plus* `{ workspace = true }` | reject bare names; assert wheel `Requires-Dist` matches resolved version |
| **R-STRUCT-12** | FAIL | One `requires-python` floor governs the workspace; off-floor members carve out to path deps | `uv lock` fails until resolved |
| **R-GATE-1** | FAIL | The `main` ruleset has an **EMPTY** bypass list, requires a PR + the strict `verify` check + **"require review from Code Owners"** (NOT a blanket approval count) + blocks force-push/deletion + linear history. Routine changesets (no CODEOWNERS path touched) auto-merge on green `verify`; control-plane PRs additionally need the re-verifying App's code-owner review | GitHub Repository Ruleset (REST) |
| **R-GATE-2** | FAIL | The box authors ZERO commits on the source of truth | deploy script is pull-only; audited |
| **R-ARCHIVE-1** | FAIL | Fluff is archived via annotated `archive/*` git tags then deleted from HEAD; zero hand-rolled `_archived/` dirs in the live tree | tag + `git rm` (§9) |

### 7.x Server-side gate (the un-bypassable layer)

- **`.github/workflows/verify.yml`** — job named exactly **`verify`**. Runs: `uv lock --check` (freshness, no build) → separate `uv sync --locked --all-packages` (install proof) → `uv build --all-packages` + wheel `Requires-Dist` assertion → `uv run python scripts/check_bijection.py --all` → `uvx pre-commit run --all-files` → commitlint → pytest. **uv is put on PATH via `astral-sh/setup-uv@v5`** (uv is NOT on the box's non-interactive PATH; same hazard in any box hook → use an absolute path).
- **Ruleset** on `main` via `POST /repos/forschzachary/forsch-adk-workspace/rulesets` with `bypass_actors: []`: `pull_request` with **`required_approving_review_count: 0`** + **`require_code_owner_review: true`** + `dismiss_stale_reviews_on_push`, `required_status_checks` (`strict_required_status_checks_policy: true`, context `verify`), `non_fast_forward`, `deletion`, linear history. **Solo-operator resolution:** zero blanket approvals means a routine factory changeset (touching no CODEOWNERS path) auto-merges on green `verify` with no human/bot in the loop — no self-approval deadlock. `require_code_owner_review` only bites PRs that touch an owned (control-plane) file.
- **The control-plane reviewer is a GitHub App** (a lead agent's identity) listed as the CODEOWNER. It is **not a bypass actor** (bypass stays empty — you're still bound); its approval counts only because it **independently re-runs the full invariant suite from a clean checkout** and approves on green. A bot that merely clicks "approve" is false assurance and is forbidden.
- **IMPLEMENTED as Path 2 (status check, not code-owner review).** On a personal-account repo, App bot users can't be CODEOWNERs and code-owner-required review has plan constraints. So the built design (A2 / PR #3 on `forsch-adk-workspace`) replaces code-owner review with a **second required status check, `control-plane-approved`**: its workflow detects whether a PR touches a control-plane path (step-level, so routine PRs pass instantly), and on control-plane PRs runs the full invariant suite, passing only on green. The workflow file is itself a control-plane path (self-hardening — weakening the check trips the check). Same guarantee, zero CODEOWNERS/plan dependency. The `main` ruleset therefore requires **`["verify", "control-plane-approved"]`** with an empty bypass — no `require_code_owner_review`.
- **`.github/CODEOWNERS`** guards `/.github/`, `.pre-commit-config.yaml`, `scripts/check_*.py`, `agent_specs/agents.yaml`, `release-please-config.json`, `repo_manifest.yaml`, `factory/` — owner = the re-verifying App.
- **⚠️ ORDERING GOTCHA:** the `verify` workflow **must exist and have run at least once** before the strict required-check rule is armed — otherwise the required check is "a pending check that never arrives" and **blocks all merges permanently**. The required-check string must change in lockstep with any job rename.
- **Empirical acceptance:** after creation, `git push --dry-run origin main` MUST be **rejected** and `GET /repos/.../rules/branches/main` MUST return a non-empty array. Apply the same ruleset to every other independent remote that still exists.

### 7.y Version-out automation (release-please, manifest mode)

`release-please-config.json` (`release-type: python`, `separate-pull-requests: true`, `include-component-in-tag: true`, `tag-separator: "-"`, one `packages{}` entry per unit) + `.release-please-manifest.json` **seeded with current real versions** (components is **0.1.0** today — seeding 1.4.0 would mis-version) + `.github/workflows/release-please.yml` on `push: main` with `permissions: { contents: write, pull-requests: write }`. uv and release-please are complementary (uv = workspace/build/lock; release-please = bump/changelog/tag/release).
> The default `GITHUB_TOKEN` creates tags/releases but does **not** re-trigger downstream `on: push tag` workflows — a future publish-to-index job needs a PAT or GitHub App token (a real credential decision).

---

## 8. Migration plan (one-time, reversible)

### P0 — Freeze & snapshot (measured reality)
The parent is **7 commits ahead of origin with a DIRTY tree** (staged deletions, modified `agent_specs/agents.yaml`) — subtree refuses a dirty tree. Steps: commit/stash the parent clean; **commit untracked child files** (e.g. `components/screening_tools.py`) before absorbing (else subtree drops them); push all unpushed children + `git tag pre-monorepo-2026-06-28` in each; **`git bundle`** `agents/wow-guild` (no origin); full `tar` of `/root/.hermes/workspace/adk` (~2.6 G; 72 G free) — the authoritative rollback. Choose the absorb ref consciously for divergent children (`components` on `part1-workspace-resolver`; `live-agent-graph` stash: pop-and-commit vs leave-in-backup).

### P0.5 — Apply + verify the control plane (NEW — because it is 100% absent today)
Add `.github/workflows/verify.yml` so a `verify` check exists; let it run green once; **then** apply the `main` ruleset with required `verify` (empty bypass) via REST; install `/root/.hermes/deploy.sh` (pull + fail-closed `git rev-list origin/main..HEAD` guard + smoke + rollback); wire the push webhook + 60 s fetch-poll backstop. **Acceptance — do not proceed until all pass empirically:** a throwaway PR failing the linter cannot merge; `git push --dry-run origin main` is rejected; `GET /rules/branches/main` is non-empty; the box pulls on merge and authors no commit.

### P1/P2 — Absorb via subtree (exact mechanics)
Per child, strict order: **(1)** delete the child-ignoring `.gitignore` lines first (else subtree silently skips files); **(2)** resolve and check out the **intended ref explicitly** (do not trust the current branch); **(3)** `git subtree add --prefix=<dest> $(git -C <child> rev-parse --show-toplevel) <ref>` **without `--squash`**, from outside the worktree; **(4) verify with `git log --oneline | wc -l` (increases by the child's commit count) and `git subtree split --prefix=<dest> -b _check && git log --oneline _check | wc -l`** — **do NOT** use `git log -- <prefix>` (shows only the single "Add … from commit" line, indistinguishable from a squash — a git-noob would wrongly conclude history was lost and re-run with `--squash`, cementing real loss); **(5) only then** `rm -rf <child>` (subtree does not remove the in-place dir; an in-place untracked child makes `git subtree add` fail "prefix already exists"). Optional: if per-file blame at the *new* path is required, `git filter-repo --to-subdirectory-filter <prefix>/` on a clone of the source before merging (rewrites SHAs — acceptable; old remotes archived read-only).

### P3 — Re-point runtime
Update systemd unit paths, `FORSCH_ADK_WORKSPACE`, import paths; restart; verify health.

### P4 — Registry unification
`build_live_graph.py` reads `agent_specs` as the spine + control-surface registry as a presentation overlay; demote duplicated fields.

### P5 — Archive old remotes
Set `forsch-adk-components` and `live-agent-graph` (and each absorbed agent) remotes to read-only mirrors / archived (never deleted).

### Rollback (tiered, concrete)
Per-child before push: `git revert -m 1 <merge-sha>` (record every merge SHA; **reverting a subtree merge is a known footgun** — to re-merge you must revert the revert). Whole migration: restore the P0 tar (authoritative, includes every child `.git`). `wow-guild`: clone the bundle. Plus archived remotes as a third path.

---

## 9. No-fluff: filesystem ⟺ graph bijection

The live graph has **41 nodes / 29 links**; **7 agent nodes**; `agents.yaml` has **11 keys (4 are fluff)** — so the bijection linter is keyed on **`agent-graph-v2.json` node ids**, NOT `agents.yaml` (keying on `agents.yaml` would green-light fluff by the operator's own definition).

**Keepers** (graph-backed): `agents/{assistant,brand,build,ops,social,stability}` → agent nodes · `components/` → the shared lib backing all 12 tool nodes · `bridge/` → `ui:bridge` · `builder/` → `ui:cockpit` · `live-agent-graph/` → the control surface itself.
**Archive** (no graph node): `web_agents/` (stale duplicate tree), `agents/wow-guild` + ~16 spawn/e2e throwaways (`api_spawn_test`, `e2e_proof*`, `*_spawn_test`, `guild_*`, `wow_guild_*`, `raid_scheduler`, `testbot`, legacy `hubert`), `agent_specs/` legacy flat file, `graph/` (v1), `data/`, `spikes/` (locked), `_archived_agents/`, `_ios-shelby-reminders/`, `preambles/`, stale root snapshots (`CURRENT-STATE.md`, `DIRECTORY.md`, `GIT-DISCIPLINE.md`).
**Investigate** (one check before disposition): `agents/shelby`, `agents/screening`, `factory/`, `chat/`, `scripts/`, `docs/` — each must be covered by a live-graph node *or* the committed allowlist before being kept/folded/archived.

**Archive mechanism (proven): annotated `archive/*` tag + delete** — the standard "archive a tree without losing history" pattern, NOT a hand-rolled `_archived/` dir (the repo currently hand-rolls exactly the wrong thing). Per fluff path: `git tag -a archive/web_agents-2026-06-28 -m '…' <commit>` then `git rm -r web_agents && git commit`. The bytes stay reachable forever via the tag.

> **The graph is a derived artifact, not a source.** `agent-graph-v2.json` is generated by `build_live_graph.py` from the registry. So: (a) the factory never hand-writes a graph node — it writes the **sources** (`agent_specs` spine + control-surface overlay) and **regenerates** the graph as the last step of the changeset; (b) the committed graph is checked for *freshness* (regenerate → assert no diff), exactly like `uv lock --check` — it is never 3-way-merged (on conflict, regenerate). This removes `agent-graph-v2.json` from the concurrency-hazard set in §1, leaving only `uv.lock` and the release-please manifest (serialized behind the single-writer factory; see the factory-contracts doc).

**Bijection rule (R-STRUCT-9, both directions):** `set(agents/<x> dirs) == set(agent:<x> nodes in agent-graph-v2.json) == set(agent keys in agents.yaml)`, FAIL on any asymmetric element either way, **and** the regenerated graph matches the committed one (freshness); **plus** every `artifact:` path in the graph resolves on disk (after stripping the trailing `\s*\(.*\)\s*$` symbol annotation and expanding globs; skip logical descriptors). Resolve repo root via `git rev-parse --show-toplevel`. A **closed allowlist** of non-node infra lives in committed `repo_manifest.yaml`: `{ packages/, agents/, clusters/, components/, bridge/, builder/, live-agent-graph/, factory/, scripts/, .github/, repo_manifest.yaml, Makefile, README.md, CLAUDE.md, .gitignore, .pre-commit-config.yaml, release-please-config.json, .release-please-manifest.json, uv.lock, pyproject.toml }`. **`factory/` is explicitly allowlisted** — it is load-bearing infra (the only sanctioned topology writer), not fluff; the no-fluff sweep must never archive it. Reference impl proven on box: clean tree exits 0; after `mv bridge bridge_RENAMED` it prints MISSING and exits 1.

---

## 10. Decisions closed / what changed

All §10 open questions are **closed** per the hardening: uv workspaces **confirmed** (members glob includes `clusters/*`; fallback = uv path deps); `git subtree` no-`--squash` **confirmed** (filter-repo only if new-path per-file history needed; submodules rejected); absorb all 7 agents + bridge + components + live-agent-graph, archive spikes; top-level `/agents` layout. **Deleted:** "not moving CI off the box" — CI is a required GitHub Actions check from day one (release-please *requires* GitHub Actions, so box-run CI is explicitly not the model). Every hand-rolled mechanism was replaced by a proven tool: `.githooks/` → **pre-commit framework + GitHub Ruleset**; ad-hoc bump+tag → **release-please**; box-pushes-origin → **pull-based GitOps**; `find -name .git` → **`git ls-files -s` gitlink check**; `agents.yaml`-keyed bijection → **graph-keyed bijection**.

---

## 11. Residual risks (carry into the implementation plan)

1. **The control plane is 100% absent today** — nothing here is load-bearing until P0.5 applies *and re-verifies* it. Trust the `push --dry-run` rejection, not the prose.
2. **`requires-python` intersection across the 7 agents is unconfirmed** — if any needs a Python floor the others can't run, it can't be a workspace member (`uv lock` fails until carved out to a path dep). Check before P1.
3. **Per-child absorb ref is a conscious choice** (`components` on `part1-workspace-resolver`, 18 ahead of its own `main`). Wrong ref passes the `.git` check while importing the wrong tree.
4. **The bijection linter will correctly FAIL RED until the ~16 stray fluff dirs are archived** — so arm the required `verify` check *after* the archive pass, or the repo can never go green.
5. **release-please default token does not re-trigger tag workflows** — a future publish job needs a PAT / GitHub App token.
6. **Box-only smoke runs post-deploy** (after merge) with rollback — if smoke must *block before users*, add a staging pull target (additive). Decide if needed now.
7. **GitOps trigger** (webhook vs 60 s `git fetch` timer) unpicked — confirm the box can receive a GitHub webhook, else default to the poll backstop.
8. **`uv lock --check` proves manifest↔lock consistency, not registry freshness** — schedule a periodic `uv lock --upgrade`; do not claim it covers supply-chain drift.
9. **On-box tooling gaps that silently no-op gates if unaddressed:** uv not on non-interactive PATH (pin absolute / setup-uv); `gh` not installed (use REST with the stored token, or run gh from the Mac); `unzip` absent (use `python -m zipfile` for the `Requires-Dist` assertion).
10. **Investigate dirs** (`chat/`, `factory/`, `scripts/`, `docs/`, `builder/`, `agents/shelby`, `agents/screening`, `preambles/`) must each pass the bijection check (graph node or allowlist) before being kept/folded/archived.

---

## 12. Adversarial review surface (status)

All six original attack fronts plus four new ones were executed empirically on the box; **all 10 landed** and are folded in above. Notably: **(3)** `--no-verify` only skips the *local* hook — the gate is the server-side ruleset required-check on `main` (live evidence the current state is unprotected: rulesets `[]`, protection 404, `rules/branches/main` count 0, `push --dry-run` ACCEPTED); **(6)** the external git-tag install works *iff* the dep token is `forsch-adk-components`, the inline-URL `@ git+…#subdirectory=…` form with `--tag` is used, **and** `pyproject` version == the tag semver at that commit (uv#9811 + the tag-name-vs-version disconnect). Reviewers should re-run the §7.x empirical acceptance tests after P0.5 — that, not this document, is the proof.

---

## 13. After acceptance

1. `writing-plans` turns §8 (P0 → P5) into the ordered, reversible implementation plan with the exact commands and per-phase empirical acceptance tests.
2. Migration executes on the quiet field.
3. The agent-factory **pattern-contracts spec** (Abstract Factory / Command / Chain / Singleton) is written on the now-single, now-atomic, now-gated foundation — the only ground on which "bulletproof factory" is achievable.
