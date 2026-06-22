# Handoff — Shelby household kit (2026-06-21)

What got done, and **every bump worth fixing for next time**. Author: Hubert (Claude).

## Done this session (committed, local-only)
- `components` `063e132` — household kit: `log_groceries`, `get_grocery_log`, `add_reminder`
  (`forsch.adk_components.tools.household`), append-only JSONL under
  `$FORSCH_ADK_WORKSPACE/data/household` (override `FORSCH_HOUSEHOLD_DATA`). 11 tests; suite 36 passed.
- workspace `712be46` — wired the 3 tools into `shelby` in `agents.yaml`; `safety_level
  read_only -> local_write`; `.gitignore` excludes `data/household/`; regenerated wrapper.
- workspace `7bc0a5d` — made her reminder instruction honest about local-only v1.

`add_reminder` returns `synced: false` + "logged locally — not yet synced to Apple Reminders".
**Not yet runnable in chat** (see scope below).

## Bumps (the fix-it list)

1. **Factory CLI is a silent no-op.** `CLAUDE.md` documents
   `python -m forsch.adk_factory.cli apply --agent <id>`, but `factory/.../cli.py` has **no
   `__main__`/argparse** — it imports, defines functions, exits 0, writes nothing, no error.
   Had to drive `apply()` from Python. → *Add a real CLI entrypoint, or fix the doc.*

2. **`apply()` only writes the web wrapper, not the runnable package.** `apply()`→`plan()`→
   `render_agent()` emits only `web_agents/<id>/root_agent.yaml`. The runnable
   `agents/<id>/.../agent.py` comes from `render_agent_package()`, which `apply()` never calls.
   So even driven correctly it half-generates, contradicting "factory generates both."
   → *Have `apply()` include `render_agent_package`.*

3. **Generated package is gitignored and repo-less.** `agents/*` is gitignored by the workspace
   repo and `agents/shelby/` has no nested git repo, so `agent.py` lives only on disk — a
   reimage/clone won't have it until regenerated, and there's no per-agent repo like the other
   agents. → *Decide Shelby's repo story; add a shelby step to `rebuild_venvs.sh`.*

4. **Git friction as root.** Repos owned by uid 10000; running as root triggers "dubious
   ownership", and `git config --global` fails because **`$HOME` is unset**, so the
   safe.directory exception can't persist. Every git call needs inline
   `-c safe.directory=... -c user.name=Hubert -c user.email=hubert@forsch.local`.
   → *Set `HOME` and a system gitconfig with safe.directory + the Hubert identity.*

5. **Doc/state drift on the runtime surface.** `CLAUDE.md` says the bridge is a **Chainlit**
   chat surface; `bridge/bridge_config.yaml` and `CURRENT-STATE.md` say **Discord**. The live
   bridge is Discord (channel→agent routing). → *Reconcile the docs to the live surface.*

6. **Builder doc drift.** `builder/STATUS.md` describes a Phase-1 **read-only** dashboard on
   `127.0.0.1:8765` with Generate/Deploy **disabled**; the service deployed at the Tailscale
   Funnel `:8443` is the **edit-capable** canvas with Run/Deploy/Generate + a web terminal,
   gated only by a URL token. → *Update STATUS.md to the deployed reality; document token handling.*

7. **No Apple Reminders path + Linux box.** Spec assumed "create a real Apple Reminder," but the
   box is Linux with zero Apple/CalDAV/osascript plumbing anywhere. Resolved for v1 as
   local-only with honest receipt. → *To get phone sync: pick a mechanism (iCloud CalDAV needs
   an Apple ID + app-specific password) and provision creds.*

8. **Smoke-test one-liner assumes a venv the bridge doesn't use.** The pasted
   `agents/shelby/.venv/bin/adk run web_agents/shelby` expects a standalone shelby venv, but the
   bridge runs agents from a baked Docker **image** via PYTHONPATH — no per-agent venvs, and
   `rebuild_venvs.sh` has no shelby step. → *Either add a shelby venv builder or use a
   bridge-based smoke test.*

9. **`safety_level` is decorative.** Nothing branches on it (stored + displayed only). Set
   shelby → `local_write` (a new, unvalidated value). → *Make it an enforced enum or document
   it as a label.*

## Open decision blocking "runnable"
**Where does Shelby live?** She's a personal agent for Zach's wife, not a Forsch team lead, so a
`#team-*` Discord channel is wrong. Options: a dedicated private channel, DM routing, or a
different surface entirely. Needed before wiring `bridge_config.yaml`.
