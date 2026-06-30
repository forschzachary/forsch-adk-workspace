# ScreeningRoom — Full Buildout (as-built review)

**Date:** 2026-06-30
**Status:** **BUILT** — all 10 phases committed locally. Nothing pushed, nothing deployed, no live side effects yet.
**Branches:** forsch bots `feat/screeningroom-huberto` · SR app + `sr` CLI `feat/sr-stack-diagnose`
**Verified this review:** 16 bot modules import clean · `node --check scripts/sr` OK · 93 bot-phase tests pass · agents build (Huberto **28** tools, ops 8, curator 15).

> This is the design + as-built record for review. The day-of actions (deploy + live checks) live in
> `2026-06-30-MORNING-CHECKLIST.md`. The detailed implementation (files, line numbers, pseudo-code) is
> in the git history of each commit below.

---

## 0. What needs YOUR decision (review these first)

| # | Decision | Recommendation |
|---|---|---|
| 1 | ~~Hetzner gateway blocker~~ — **RESOLVED (Zach):** LiteLLM already runs ON Hetzner, so co-locating the bots means localhost. Not a blocker — it's the reason Hetzner is the right home. | At deploy, set `LITELLM_BASE_URL` to the box-local address (e.g. `http://127.0.0.1:<port>`) instead of the Mac's public/tailnet URL. |
| 2 | **Uncommitted SR web-app changes** — `src/app/api/events/route.ts` (+110), `src/lib/discord.ts` (+99), new `src/app/api/events/announce/route.ts`. A Discord events/announce API an agent built **beyond scope**, unverified/untested. | Review → test → commit, **or** revert. Inert until decided (uncommitted = not deployed). |
| 3 | **`agent_specs/agents.yaml` churn** — uncommitted whitespace/line-wrap reflow of the 6 **legacy** Factory leads (not the bots; semantically equal, `forsch plan stability` still clean). | **Revert** — it's noise. |
| 4 | **`AGENTS.md`** (untracked) — the cloud-box Hubert orchestrator profile. | Keep+commit or remove — your call; harmless either way. |
| 5 | **6 live verifications** still need you (real account creation, the "ready" DM, the SR-1 write, etc.). | See checklist §B; do together. |

---

## 1. The system, as built

Three native ADK Discord bots in ONE process (`python -m forsch.adk_bridge.discord_main`), **hand-coded** — NOT generated from `agent_specs/agents.yaml`. All shell out to the `sr` CLI, which wraps the Ultra.cc media stack (`Jellyseerr → Radarr/Sonarr → Prowlarr → NZBGet/rTorrent → Jellyfin`).

| Bot | Role | Surface | Identity |
|---|---|---|---|
| **Huberto** | friend-facing cat — discovery, onboarding, requests, "where's my movie?" | DM-only | `1499544375204773969` |
| **screening_ops** | internal ops lead — stack health + diagnosis | team-social channel, **@mention-only** | companion-lead `1512599235910963371` |
| **curator** | SR-1 showrunner — guide/bumps/playlists/events + Gate B scheduling | `#screening-tv`, **optional** (runs only if `CURATOR_DISCORD_BOT_TOKEN` set) | TBD (3rd token) |

**Hard rules (enforced + tested):** never spoil · never fabricate · never leak credentials · invite-only.

**Two gates the project is graded on:**
- **Gate A** — invite → provision → verified login → request → **"it's ready" DM**. (Phases 4 + 5.)
- **Gate B** — a friend's pick on **SR-1** at a wall-clock time. (Phase 2 engine, Phase 6 owner.)

---

## 2. Per-phase review (commit · what shipped · the design call · status)

### Phase 1 — Graph swap · `5797337` (+ orphan cleanup `cded2f4`)
**Shipped:** retired the stale Factory `screening` agent; modeled Huberto + screening_ops + their real tools as native nodes in `capabilities.json` (merged at graph build, survives `forsch build`).
**Design call to review:** native nodes live in `capabilities.json`, deliberately outside the Factory regen path — the graph tells the truth without the Factory trying to regenerate hand-coded bots.
**Status:** ✅ done. (Hosted cockpit on Railway still reads the box's copy — regenerate + redeploy there to update it; noted in deploy.)

### Phase 2 — Gate B engine · `8788fd4` (sr CLI) + `0f7e11e` (tool)
**Shipped:** `sr tv schedule <title> --at <time>` — inserts a title onto SR-1 (Supabase `programs`) at a wall-clock time and **reflows** the rest (no gaps/overlaps); `--dry-run` writes nothing; `schedule_on_sr1` bot tool shells it.
**Design call:** atomicity via a unique `(channel_id, starts_at)` index + reflow; inserts beyond the schedule horizon are **rejected with guidance** (not auto-extended) for v1.
**Status:** ✅ coded + `node --check` clean. ⚠️ **the live SR-1 write is one of the 6 things to verify with you** (dry-run first).

### Phase 3 — Inter-bot delegation ("one unified bot") · `56943e5`
**Shipped:** diagnostics extracted to a shared `ops_diagnostics.py`; Huberto gained `check_my_request(title)` so "where's my movie?" returns the **real** pipeline status (downloading / cooldown / done) in his own voice — never "let me ask ops."
**Design call:** a **shared module**, not bot-to-bot calls (DRY, no event-loop coupling). To the friend it's one bot.
**Status:** ✅ done, imports clean.

### Phase 4 — Verified provisioning (managed outcome) · `50c154c` (bot) + `d71ec32` (sr CLI)
**Shipped:** after creating an account, `sr users verify` proves the friend can **(a)** authenticate, **(b)** see their isolated library, **(c)** request (Jellyseerr linked) — `provision_access` only returns success when all three pass, and is now idempotent (`already_exists` → steer to reset). DM-403 is caught and the login is queued for auto-delivery; Huberto never asks you to DM by hand. `sr diagnose provision --repair` fixes the half-failed Jellyseerr-link case.
**Design call:** "done" = the friend can actually use it, not "the API returned 200" — the managed-outcome mandate, enforced in code.
**Status:** ✅ unit-tested green. ⚠️ **real account creation is a live check.**

### Phase 5 — Proactive notifications (closes Gate A) · `6cbd45a`
**Shipped:** `request_watcher.py` polls each friend's requested titles; when one becomes watchable, Huberto fires exactly one outbound **"🎬 your movie's ready"** DM. `add_watched_request` is called automatically after `request_movie`. Idempotent across restarts (the `notified` flag persists).
**Design call:** single in-process watcher (dies with the bot, resumes on restart) — fine for v1; a separate poller is a later option.
**Status:** ✅ unit-tested green. ⚠️ **the outbound DM is a live check.**

### Phase 6 — Curator (3rd bot) · `9d9f48f`
**Shipped:** optional curator bot — `curator_persona.py` + `curator_tools.py` (tv now/guide/schedule/reprogram, bumps, playlists, events, `suggest_to_main`). Owns Gate B. Runs only if its token is set; otherwise the system runs unchanged on two bots.
**Design call:** **separate 3rd identity, optional-skip** — same pattern as ops; nothing breaks if the token isn't registered yet.
**Status:** ✅ builds (15 tools). ⚠️ **needs a 3rd Discord token registered before it can run.**

### Phase 7 — Security hardening · `105f6b2`
**Shipped:** `invite_friend_admin(caller_discord_id, name)` — **tool-level** admin gate (no longer persona-trust); ops is **@mention-only** in its channel (DMs unaffected); per-user **rate limits** (`rate_limit.py`); append-only **audit log** (`audit_log.py`, `data/audit.jsonl`) of every consequential action, password-free, admin-readable.
**Design call:** the caller id is an explicit tool param injected at agent boot (ADK tools can't see the caller otherwise) — the gate is enforced in the tool, not the prompt.
**Status:** ✅ unit-tested green.

### Phase 8 — Lifecycle · `18cb24c`
**Shipped:** reversible **suspend** + archived **offboard** (`sr users disable/enable`, never hard-delete by default); SR-1 **scheduling-conflict arbitration** (first requester wins the slot, second is offered an alternative); idempotent **recovery** when an account was made but the login DM failed (`resend_login_dm`, no duplicate account).
**Design call:** archive-first (the irreversible `sr users delete` is never the default path).
**Status:** ✅ unit-tested green.

### Phase 9 — Activation + branding · `cffa349` (+ `f4e25b6` sr CLI)
**Shipped:** `jellyfin_activation_status` (read-only — did they log in + watch?), a one-time gentle nudge after ~7 days inactive, and spoiler-safe text templates (`welcome-template.md`, `sr1-announcement-template.md`) + `announce_sr1_pick`.
**Design call:** templates, not hardcoded copy; activation is "logged in + watched," distinct from "account created."
**Status:** ✅ committed + green. (This is the phase the build harness mis-reported as "unknown" — a reporting crash, not a failure.)

### Phase 10 — Eval / quality gate · `507c194`
**Shipped:** a pytest regression suite for the native bots asserting the invariants — never-spoil, never-fabricate, never-leak-credentials, invite-only — since `forsch eval` can't reach native Discord bots. Static/mocked by default; the live-LLM spoiler check is opt-in (`TEST_LIVE_LLM=1`).
**Design call:** the unit gate is the merge/deploy gate; no live calls needed to pass it.
**Status:** ✅ **93 passed, 3 skipped, 0 failed.**

### Deploy-prep · `d8f1b2c`
**Shipped:** `deploy/` — Dockerfile + docker-compose + systemd unit + `.env.example` (names only) + `DEPLOY-RUNBOOK.md` + `REPO-SYNC.md`.
**Status:** ✅ files present; **not executed** (morning, with you).

---

## 3. Honest caveats (none block deploy)
- **Huberto is at 28 tools** — it builds and tests pass, but that's a lot for one agent's tool-selection. Worth a trim pass later.
- **3 full-suite test failures are env-only** (`gradio`, `pytest-asyncio` missing) on **legacy non-bot** code; the bot suites are clean.
- **Watcher + rate-limit are single-process** — correct for one `discord_main` process; revisit only if it scales out.
- **altHUB indexer VIP expired** — renew or drop in Prowlarr before relying on `sr stack`.

## 4. Dependency order (how it was built)
1 Graph → 2 Gate B engine → 3 Delegation → 4 Verified provisioning → 5 Notifications *(Gate A done)* → 6 Curator *(owns Gate B)* → 7 Security → 8 Lifecycle → 9 Activation/branding → 10 Eval gate → **Hetzner deploy (next)**.
