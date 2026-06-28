# A2 — Stand up the control-plane reviewer (paste-ready brief for mimocode)

Copy everything in the box below into mimocode. It's self-contained (assumes zero context).

---

```
TASK: Stand up the "control-plane reviewer" for the GitHub repo
github.com/forschzachary/forsch-adk-workspace (a PRIVATE, PERSONAL-account repo).

WHY THIS EXISTS
We are arming a server-side merge gate on `main`: a GitHub Repository Ruleset with an
EMPTY bypass list, requiring (a) a passing status check named `verify` and (b) a
code-owner review ONLY on "control-plane" files. Routine changes auto-merge on green
`verify` with no review. But a small set of files (the gate itself) must get a second
set of eyes — and since this is a solo operator who cannot approve their own PRs, that
reviewer must be a NON-HUMAN identity that approves automatically AFTER independently
re-verifying the change. This task builds that reviewer.

CONTROL-PLANE FILES (the paths that require the reviewer):
  .github/**, .pre-commit-config.yaml, scripts/check_*.py,
  agent_specs/agents.yaml, release-please-config.json, repo_manifest.yaml, factory/**

THE ONE NON-NEGOTIABLE RULE
The reviewer must NOT be a rubber stamp. It approves a PR ONLY after checking out the
PR head in a clean runner and re-running the full invariant suite (the same checks the
`verify` workflow runs: `uv lock --check`, `uv run python scripts/check_bijection.py`,
`scripts/check_structure.py`, `uv build --all-packages`, pytest). If any check fails it
must request changes, not approve. A bot that approves without re-verifying is worse
than no reviewer (false assurance) and is explicitly forbidden.

DECISION TO MAKE FIRST (pick one, state your choice + reasoning):
  (A) DEDICATED bot identity — a separate GitHub identity whose only job is reviewing.
      RECOMMENDED: clean separation of duties; the thing that reviews the factory's work
      is not the same thing that produced it.
  (B) A LEAD AGENT wearing the reviewer hat — reuse an existing automation identity.
      Lighter, but weaker as a gate (closer to self-review).

CONSTRAINTS YOU MUST VERIFY AGAINST CURRENT GITHUB DOCS BEFORE BUILDING
(this is a personal private repo — these bite):
  1. Teams don't exist on personal accounts, so CODEOWNERS can only list individual
     USER accounts (not a team). A GitHub App's `app[bot]` user generally cannot be a
     CODEOWNER. Verify the current rule.
  2. "Require review from Code Owners" on a PRIVATE personal repo may require a paid
     plan (GitHub Pro). Verify whether this repo's plan supports it.
  3. If either constraint blocks the CODEOWNERS path, use the FALLBACK below — it
     achieves the identical gate without depending on code-owner-review at all.

RECOMMENDED IMPLEMENTATION — pick the path that the constraints above allow:

  PATH 1 (code-owner review, if constraints 1+2 are satisfied):
    - Create/choose the reviewer identity (a machine USER account, e.g.
      `forsch-factory-bot`, is the most reliable CODEOWNER on a personal repo; a GitHub
      App is fine only if you confirm its bot user can be a code owner here).
    - Add it as a collaborator with write access. Add it to .github/CODEOWNERS as the
      owner of the control-plane paths listed above.
    - Store its credential as a repo secret (a fine-grained PAT for the machine user
      with `pull_requests: write`, `contents: read`; or an App id + private key).
    - Add `.github/workflows/control-plane-review.yml`: on `pull_request` touching a
      control-plane path -> checkout PR head -> run the full invariant suite -> if green,
      `gh pr review --approve` AUTHENTICATED AS THE BOT (not GITHUB_TOKEN, which can't
      approve); if red, `gh pr review --request-changes`.

  PATH 2 (FALLBACK — pure status check, no CODEOWNERS, RECOMMENDED if any constraint bites):
    - Skip code-owner review entirely. Instead add a SECOND required status check named
      e.g. `control-plane-approved` to the ruleset.
    - `.github/workflows/control-plane-review.yml`: on any PR, detect whether it touches
      a control-plane path. If it does NOT, succeed immediately (check passes — routine
      PRs are unaffected). If it DOES, checkout PR head -> run the full invariant suite ->
      pass ONLY if all green. Mark this job's check `control-plane-approved`.
    - Net effect: control-plane PRs can't merge unless the re-verify passes; routine PRs
      ignore it. Same gate, zero CODEOWNERS/plan dependency, all status-check primitives
      we already rely on.

ACCEPTANCE TESTS (must all pass before declaring done):
  1. A control-plane PR that is GREEN gets auto-approved (Path 1) / passes
     `control-plane-approved` (Path 2) and becomes mergeable.
  2. A control-plane PR that breaks an invariant (e.g. delete a line from
     scripts/check_bijection.py, or add a stray dir) gets changes-requested / a RED
     `control-plane-approved`, and the merge button stays blocked.
  3. A ROUTINE PR (touches no control-plane path) needs no review and merges on `verify`
     alone.
  4. There is NO way to get an approval without the invariant suite passing (no manual
     bypass, no `--no-verify` path, empty ruleset bypass list).

NOTES
  - `uv` is the package manager; in CI use the `astral-sh/setup-uv` action so `uv` is on
    PATH. Repo uses a uv workspace (members under packages/*, agents/*, clusters/*).
  - Do NOT arm or modify the `main` ruleset itself in this task — only build the reviewer
    + its workflow + (Path 1) the CODEOWNERS entry. Arming the ruleset is a separate,
    gated step done later with a human present. Report back what the ruleset will need to
    reference (the check name / code-owner) so it can be wired in then.
  - Reference design: the operator's strategy doc section "7.x Server-side enforcement".
  - If you hit a constraint that makes BOTH paths impossible, STOP and report — do not
    invent a weaker gate.

DELIVERABLES: the reviewer identity (created + access configured), the
control-plane-review.yml workflow, (Path 1) the CODEOWNERS entry, a short README of how
it works, and the results of the 4 acceptance tests on throwaway PRs.
```

---

## Quick orientation (for you, not for the paste)

- **My recommendation on the decision:** go **dedicated bot identity** (option A) — a reviewer that's separate from the agents producing the work is a real gate; a lead reviewing its own output isn't.
- **Expect the agent to land on Path 2** (the `control-plane-approved` status check). On a personal private repo, code-owner-required-review is the fiddly path (no teams, possible plan gate), and Path 2 gives the identical guarantee using the status-check machinery we already trust. Either is fine — the acceptance tests are what matter.
- **It won't touch the live ruleset** — it only builds the reviewer + workflow and reports what to wire in. Arming the gate stays a human-present step (Task 8).
