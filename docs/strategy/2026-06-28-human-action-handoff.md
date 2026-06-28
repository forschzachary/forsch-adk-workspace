# Human Action Handoff — what I need from you (forschzachary)

Date: 2026-06-28. Everything an agent can do, I'll do. This is the list that needs *you*.
Ordered by urgency. Check items off as you go.

---

## 🔴 A. Do now — only you can (external systems)

- [ ] **A1 — Rotate the Discord bot token.** It's committed in `bridge` history (`bridge.env.bak-pre-modelprefix-…`, commit `66e32af`) and is compromised. Discord Developer Portal → the bridge bot's app → **Bot → Reset Token**. Then update wherever the live bridge service reads it. *Do this regardless of migration timing — a committed credential is burned.*
  - This also unblocks the migration: until the token is rotated **and** scrubbed from history (Task 3 Step 0, an agent can run that on the Mac once it's rotated), bridge can't be absorbed and Task 8's push would re-block.

- [ ] **A2 — Create/install the GitHub App that is the control-plane reviewer.** This is the code-owner that re-runs the invariant suite and approves PRs touching the gate files (strategy §7.x). Needed **before Task 8** arms the ruleset. **Decision for you:** which identity is "the reviewer" — a dedicated bot/App, or one of your lead agents wearing that hat? Until it exists, the `require_code_owner_review` rule can't be armed.

*(`gh` is already authenticated on your Mac as `forschzachary` — the Task 8 ruleset call runs from the Mac. Nothing to do there unless you'd rather use a token.)*

---

## 🟡 B. Migration: your go + the STOP gates

The safety net is **complete** (verified 676 MB tar + 10/11 children pushed/tagged + wow-guild bundled, all in `/root/adk-backups/`). Everything destructive is parked and reversible. When you're ready:

- [ ] **GO #1 — green-light Tasks 2–6** (create branch → subtree-absorb children → archive fluff → lay down uv + CI scaffolding → registry unification). All reversible via the tar. An agent runs it; you just say "go."
- [ ] **STOP gate before Task 7** (re-point systemd) — brief restart of live services; pick a low-traffic moment.
- [ ] **STOP gate before Task 8** (arm the ruleset) — only after `verify` is green on the PR **and** A2 (the App) exists. Arming it wrong blocks all merges. This is where the gate goes live.
- [ ] **STOP gate before Task 9** (archive old remotes) — point of no-easy-return for the standalone repos; optionally wait for a few days of stability.
- [ ] **Final confirm** — before deleting the `_absorb_*` staging dirs. (Keep the tar + bundle forever.)

---

## 🟢 C. Design decisions I need (factory contracts)

These shape the pattern-contracts spec (written post-migration). Your calls:

- [ ] **C1 — `undo()` catalog.** Merged-vs-unmerged split: unmerged → delete branch + close PR; merged → a compensating forward verb (`remove-agent`/`unship`), never a history rewrite. **OK as-is?**
- [ ] **C2 — Stale-PR cleanup.** Janitor cron (my rec) vs. leads own their own PR lifecycle?
- [ ] **C3 — Runtime store location** for `status`/`handoff_pct` (now out of git): serve.py memory, a small DB, or the existing `/pulse` layer?
- [ ] **C4 — Does the reviewer App also gate release-please's own PRs?** (release-please edits manifests = a control-plane path.)

---

## ⚪ D. One thing to verify (I can have an agent do it — flagging so you know)

- [ ] **D1 — requires-python across the 7 agents.** The uv workspace forces **one** Python floor (≥3.11). If any agent needs a different Python it can't be a workspace member (residual risk #2) and needs a carve-out. Quick check before Task 5's `uv lock`. Want me to have an agent verify it now?

---

## ⚪ E. Housekeeping

- [ ] **E1 — Commit the docs?** Four docs are uncommitted on the Mac: `repository-and-git-discipline.md`, `factory-contracts-open-requirements.md`, `monorepo-migration-plan.md`, and this handoff. Say the word and I'll commit them (local Mac, or staged to the box) — they're the durable record other agents read.

---

## State of the world (reference)

- **Docs:** 3 strategy docs in `docs/strategy/` + this handoff in `workspace/handoffs/`.
- **Migration:** safety net done; parked at the HARD GATE; reversible.
- **Decided & locked:** monorepo via uv workspaces; git subtree; GitOps (origin canonical, box pulls, zero box commits); ruleset gate (empty bypass, `verify` required, code-owner review only on control-plane via the App); no-fluff filesystem⟺graph bijection; `flock` single-writer factory; transaction-via-staging-worktree spine.
- **Pending the above:** A1/A2 are the only true blockers to *finishing* the migration; C1–C4 are needed to *write* the factory spec (post-migration), not to migrate.

**The two that block everything else: A1 (rotate token) and A2 (the reviewer App).** Everything else can move the moment you say go.
