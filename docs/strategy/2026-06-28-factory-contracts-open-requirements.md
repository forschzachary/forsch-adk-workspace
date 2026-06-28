# Factory Contracts — captured requirements (feeds the pattern-contracts spec)

| | |
|---|---|
| **Status** | CAPTURED REQUIREMENTS — not yet a full spec; written post-migration |
| **Date** | 2026-06-28 |
| **Source** | Operator design review of the repo-strategy doc + resolutions |
| **Parent** | [Repository & Git Discipline](2026-06-28-repository-and-git-discipline.md) — the topology layer this sits on top of |
| **Becomes** | The agent-factory pattern-contracts spec (Abstract Factory / Command / Chain / Singleton **+ Builder + Template Method**), authored after the monorepo migration lands |

> The repo-strategy doc hardened the **git-topology** layer. This doc captures the **factory** layer one level up — the hard problems that the topology invariants *imply* but don't themselves solve. It is the requirements record for the spec that comes after migration. Nothing here is implemented yet.

---

## R1 — `new-agent` must emit ONE atomic, gate-passing changeset (the headline)

A brand-new `agents/<id>/` dir fails the repo-strategy gate the instant it exists unless the *same* changeset also satisfies all twelve R-STRUCT invariants. So the factory's `new-agent` verb is a **transaction over multiple files**, all-or-nothing:

| Must write, atomically | For invariant |
|---|---|
| `agents/<id>/{pyproject.toml, project.md, src/…}` | R-STRUCT-2, -5, -12 |
| `agent_specs/agents.yaml` (the spine) | R-STRUCT-4 |
| control-surface registry overlay | R-STRUCT-4 |
| **regenerate** `agent-graph-v2.json` (derived; run `build_live_graph.py`) | R-STRUCT-9 |
| `release-please-config.json` + `.release-please-manifest.json` (seed real version) | R-STRUCT-7, -10 |
| intra-dep as `forsch-adk-components==X.Y.Z` **+** `{ workspace = true }` | R-STRUCT-11 |
| a valid Conventional Commit with a recognized scope | R-STRUCT-8 |

If any of these is omitted, **the factory's own first commit is structurally un-mergeable** — the factory becomes the new source of "your git is a mess." Acceptance: a golden-file test (R6) asserts the scaffold passes all twelve checks in an ephemeral repo.

## R2 — The flow is async (resolved; mirrored into repo-strategy §4.2)

Verbs return a **tracking handle, not a finished unit**; UI shows `queued → verifying → merged → live`. "Pending merge/deploy" is a first-class orchestration state. **Approver model decided:** ruleset requires `verify` + `require_code_owner_review` with **zero blanket approvals**, so routine changesets auto-merge on green CI (no self-approval deadlock); control-plane PRs need a **GitHub App that re-runs the invariant suite from a clean checkout** and approves on green (a rubber-stamp bot is forbidden — false assurance). Empty bypass stays empty.

## R3 — Contract vs runtime split in `project.md` (resolved; mirrored into repo-strategy §6)

`project.md` carries **contract only** (`name/kind/version/depends_on/owner`). `status` + `handoff_pct` move to the **non-git runtime store** (serve.py state / `/pulse` layer) — forced by R-GATE-2 (box authors zero commits). R-STRUCT-5 then guards version alone.

## R4 — Concurrency: single-writer factory

Two leads invoking the factory near-simultaneously collide on the high-contention files. `agent-graph-v2.json` is removed from the hazard set by treating it as a **derived artifact** (regenerate, never 3-way-merge). The remaining two — `uv.lock` and the release-please manifest — are serialized: **the factory is the single sanctioned writer, behind one advisory lock.** **Decided (2026-06-28): a `flock`-based advisory lockfile on the box** (e.g. `flock /run/lock/forsch-factory.lock <verb>`) — every factory invocation must hold it to write. This is correct while all leads run on the one box (true today), needs no new service, and is dead simple/proven. It promotes to a single factory daemon/work-queue only if leads ever become multi-host (revisit then). Rebase-and-re-lock-in-CI stays the fallback for the rare race that slips the lock — not the default, because `uv.lock` conflicts are miserable.

## R5 — One invariant engine, three call sites, one transaction boundary

- **Single module** `scripts/check_*` holds all invariant logic, imported by **(1)** the pre-commit framework, **(2)** the `verify` CI job, and **(3)** the factory's **dry-run pre-flight in a temp `git worktree`** (validate *before* committing, so a crashed run never leaves a half-scaffolded unit poisoning the live tree). If the factory's pre-flight and CI ever diverge you get "passes locally, fails server-side" — the exact failure being killed.
- **Each verb is a unit-of-work:** build the full multi-file changeset in a staging worktree → validate → commit-or-discard. All-or-nothing on disk before git is touched. (This is the **Builder** pattern; see Patterns.)

## R6 — The factory is load-bearing infra; give it teeth

It is the *only* sanctioned topology writer — a bug doesn't make a typo, it makes an un-mergeable repo on every click. Requirements:
- **Golden-file tests:** `new-agent foo`, `new-cluster bar`, `release baz` each emit a changeset passing **all twelve** invariants in an ephemeral repo.
- **`factory/` is allowlisted** in `repo_manifest.yaml` (done in repo-strategy §9) and is itself a tested workspace package — versioned and gated like everything else.

## R7 — Reserved-name / collision guard

`new-agent <id>` must reject ids colliding with: an existing agent/cluster/package, an `archive/<id>` tag, a **PEP 503-normalized** name clash, and **the fluff-sweep globs** (`*_spawn_test`, `guild_*`, `wow_guild_*`, `e2e_proof*`, …). Creating an agent whose name matches the auto-archiver pattern (repo-strategy §9) is a real edge that would get it swept.

## R8 — Audit trail for Surface B (the LLM trust boundary)

The plain-English→CLI mapper is an LLM and *is* the weak side of the trust boundary. Therefore:
- The factory CLI **hard-validates every arg against a closed enum** (known ids, the R-STRUCT-8 scope list) so a confused agent can't burn a CI round-trip on a half-valid commit. (This is Command-pattern validation before `execute()`.)
- Every invocation writes an **immutable receipt** — `intent → exact command → resulting commit/PR sha` — using the library's existing **`@receipt`** decorator. The honest-receipt pattern already in the patterns library *is* the audit mechanism; no new infra. This is how you debug "why did ops-lead scaffold *that*."

---

## Patterns (the §13 set, revised by this review)

The spine shifts from Abstract Factory to **Builder + Command**:

| Pattern | Role here | Note from review |
|---|---|---|
| **Builder** *(added)* | assembles the atomic multi-file changeset (R1, R5) | makes the transaction first-class, not ad-hoc |
| **Command** | each verb is a command object with `execute()` **and `undo()`** | the payoff is the **compensating action** (delete branch, close PR, drop staged node) — deterministic self-cleanup, since reverting a subtree merge is a documented footgun |
| **Chain of Responsibility** | the validation pipeline = the ordered R-STRUCT links | must be the **same** chain as R5's single engine, not a parallel re-implementation |
| **Template Method** *(added)* | agent / cluster / package scaffold variants | shared skeleton, differing steps |
| **Abstract Factory** | the one `make_agent` that all spawn paths route through | the original load-bearing fix (no second LiteLlm constructor) |
| **Singleton** | shared resources (LiteLLM gateway, rate limiter, mimo runner) | **caution:** in the long-lived, multi-agent, pull-deploy service a cached `agents.yaml`/registry goes stale the moment another lead's PR merges — a silent-drift generator (the class R-STRUCT-4 exists to catch). Rule: **read-through, or hard-invalidate on every deploy/merge.** |

---

## Resolved design decisions (2026-06-28, C1–C4)

Path-independent (no migrated-tree dependency), so locked now.

### C1 — `undo()` catalog (Command compensating actions)

Split by merged-vs-unmerged; never a history rewrite (the ruleset forbids force-push anyway):

| Verb state | `undo()` | Why safe |
|---|---|---|
| Pushed, PR open/abandoned | delete branch + close PR | staging worktree already discarded; `main` never touched — uniform across all verbs |
| Merged to `main` | a compensating **forward** verb (`remove-agent` / `unship`), itself a gated changeset | no force-push/rewrite; same machinery as create, inverted — also gives a real `remove-agent` for free (needed for the no-fluff sweep) |
| `ship` deploy fails post-merge | the deploy self-rolls-back (`git reset --hard HEAD@{1}` in `deploy.sh`) | a deploy rollback, not a git one |
| `release` PR | not the factory's to undo — release-please owns its PRs | keeps the factory out of release-please's lane |

### C2 — stale-PR cleanup: janitor cron

A scheduled janitor (GitHub Action on a cron, or a box timer) closes + deletes factory-opened PRs/branches with no activity for N days (default 7). Leads may also explicitly cancel their own via the verb's `undo()`. Chosen over "leads own their lifecycle" because it assumes no lead liveness — an always-on lead that crashes still gets its orphans swept.

### C3 — runtime store: SQLite owned by serve.py

`status` + `handoff_pct` (and other live state) persist in a small **SQLite DB in a non-git runtime dir** (e.g. `/root/.hermes/state/runtime.db`), owned by serve.py, read by the UI. NOT serve.py memory (lost on restart — `handoff_pct` is a tracked metric), NOT `/pulse` (ephemeral health), NOT git (R-GATE-2). SQLite over a JSON file because `status` is written by the running services concurrently (not only behind the factory's `flock`), and SQLite gives safe concurrent writes with no new service.

### C4 — release-please PRs: `verify` yes, reviewer no

release-please's own PRs edit `.release-please-manifest.json` (a control-plane path) but are machine-authored, narrow, and from a trusted tool. They still run the required `verify` check (can't merge if they break the build) but are **exempt from the control-plane reviewer** — scoped to PRs authored by `release-please[bot]` touching only release-managed files. Requiring the reviewer to approve the release bot's own PRs is circular friction with no added safety.

## Open questions for the spec (post-migration)

1. ~~The advisory-lock/work-queue mechanism for the single-writer factory (R4)~~ **RESOLVED 2026-06-28: `flock` advisory lockfile on the box** (all leads run on one box today; promote to a daemon/queue only if they go multi-host). See R4.
2. ~~The compensating-action catalog~~ **RESOLVED (C1/C2 above).**
3. ~~Where the runtime store physically lives~~ **RESOLVED (C3 above): SQLite.**
4. ~~Whether the reviewer gates release-please's own PRs~~ **RESOLVED (C4 above): verify yes, reviewer no.**
5. **(remaining)** The exact `verify` job's pytest scope per package, and whether `uv build --all-packages` runs on every PR or only release PRs (build time vs coverage) — decide when the spec is written against the consolidated tree.
6. **(remaining)** The janitor's N-day threshold and whether it also prunes merged `archive/*` working branches.
