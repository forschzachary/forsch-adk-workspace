# ScreeningRoom — Morning Checklist

**Date:** 2026-06-30
**State:** 10/10 phases committed **locally** on both branches. **Nothing pushed, nothing deployed, no live side effects.**
**Branches:** forsch `feat/screeningroom-huberto` · screening-room `feat/sr-stack-diagnose`
**Re-verified this morning:** all bot modules import · `node --check scripts/sr` OK · 93 bot tests pass · agents build (Huberto 28 / ops 8 / curator 15).

Pair this with the as-built review: `2026-06-30-screeningroom-full-buildout.md`.

---

## 0. Decisions to make first (5 min)

| # | Decide | Recommendation | Who |
|---|---|---|---|
| 1 | ~~Gateway reachability~~ — **RESOLVED:** LiteLLM is on Hetzner; bots co-located = localhost | set `LITELLM_BASE_URL=http://127.0.0.1:<port>` at deploy | me |
| 2 | **Uncommitted SR web-app changes** (events/announce API, `discord.ts`) — out of scope, unverified | review → test → commit, **or** revert | Zach |
| 3 | **`agents.yaml` whitespace churn** (legacy leads only) | revert | me (on your ok) |
| 4 | **untracked `AGENTS.md`** (orchestrator profile) | keep+commit or remove | Zach |
| 5 | **commit the two plan docs** (currently untracked) | commit | me |

I can do 3 + 5 in one pass the moment you say go.

---

## A. Done + verified — no action needed

Each phase is one commit on `feat/screeningroom-huberto` (sr CLI commits on `feat/sr-stack-diagnose`). Re-verified by import + `node --check` + pytest.

| Phase | Commit | Verified |
|---|---|---|
| 1 Graph swap | `5797337` (+ orphan cleanup `cded2f4`) | modules import; native nodes persist across build |
| 2 Gate B engine | `0f7e11e` + `8788fd4` | `node --check` OK |
| 3 Delegation | `56943e5` | imports clean |
| 4 Verified provisioning | `50c154c` + `d71ec32` | `test_phase4` green |
| 5 Notifications | `6cbd45a` | `test_phase5` green |
| 6 Curator (optional 3rd bot) | `9d9f48f` | imports clean |
| 7 Security | `105f6b2` | `test_phase7` green |
| 8 Lifecycle | `18cb24c` | `test_phase8` green |
| 9 Activation + branding | `cffa349` + `f4e25b6` | suites green |
| 10 Eval gate | `507c194` | **93 passed / 3 skipped / 0 failed** |
| Deploy-prep | `d8f1b2c` | `deploy/` files present |

---

## B. Needs LIVE verification (do together) — 6 checks

Coded + unit-tested, but **never exercised** against real Discord / Jellyfin / SR-1 / the gateway. Run each and observe — don't assume.

1. **Bots connect** — `docker compose -f deploy/docker-compose.yml --env-file deploy/screeningroom.env up -d`, watch logs. PASS = each identity "online", no fail-closed SystemExit, no "no gateway"/"no tokens".
2. **Huberto DM** — DM him `whats on sr1`. PASS = live SR-1 slot (proves the whole read path).
3. **Ops mention** — team-social: `@screening_ops pipeline_health`. PASS = terse stack read-out, no "unreachable".
4. **Real account creation** *(Jellyfin write, invite-gated)* — invite a test id, provision it. PASS = real `sr-<hex>` account created **and** `sr users verify` passes all 3 checks; login delivered DM-only; non-invited ids refused. → **Gate A (part 1)**
5. **"Your movie's ready" DM** *(proactive)* — test friend requests a fast-landing title; confirm `request_watcher` fires exactly one DM. → **Gate A (part 2)**
6. **SR-1 write** *(Gate B)* — `sr tv schedule "<title>" --at <time> --dry-run` first (writes nothing), then live via the bot. PASS = pick airs at the slot, schedule reflows with no gaps/overlaps, concurrent inserts can't corrupt. → **Gate B**

---

## C. Hetzner deploy — steps

Authoritative runbook: `deploy/DEPLOY-RUNBOOK.md` · repo sync (rsync, no remote yet): `deploy/REPO-SYNC.md`

**0** secrets in hand → **1** provision box (Docker) → **2** sync both repos on their branches → **3** place secrets (`screeningroom.env` + `cli.json`, `chmod 600`, never committed) → **4** connectivity pre-checks (LiteLLM is box-local now — just confirm the `127.0.0.1` URL; check Ultra.cc stack + Discord reach) → **5** `node --check` + read-only `sr stack` → **6** `docker compose up -d` → **7** the §B live checks → **8** regenerate + publish the graph to the hosted cockpit.

**Secrets to bring (none in repo):** `LITELLM_BASE_URL` (= the box-local LiteLLM URL), `LITELLM_HERMES_KEY`, `HUBERTO_DISCORD_BOT_TOKEN`, `COMPANION_LEAD_DISCORD_BOT_TOKEN`, `SR_ADMIN_DISCORD_IDS=175984567176527873`, (optional) `CURATOR_DISCORD_BOT_TOKEN` + `CURATOR_EXPECTED_BOT_ID` + `TV_CHANNEL_ID`; the ~11-key `cli.json`.

**Carried risks:** altHUB VIP expired (renew/drop in Prowlarr); single-process watcher dies with the bot (resumes on restart). _(Gateway reachability is no longer a risk — LiteLLM is box-local on Hetzner.)_

---

## D. Known-incomplete (none block deploy)

- **Uncommitted SR web-app changes** (decision #2): `src/app/api/events/route.ts`, `src/lib/discord.ts`, new `src/app/api/events/announce/route.ts` — an SR-1→Discord announce path **beyond the verified scope**. Don't assume it works.
- **`agents.yaml` whitespace churn** (decision #3): legacy Factory leads only; bots aren't in agents.yaml.
- **3 full-suite test failures** = missing `gradio` / `pytest-asyncio` on legacy non-bot code; bot suites clean.
- **Nothing pushed** — local-only on both branches; deploy syncs via rsync.

---

## TL;DR
10/10 phases built, committed, verified green. Five quick decisions in §0 (the real one is gateway reachability). Six live checks in §B to run with me. Deploy by the runbook in §C. Two stray uncommitted bits (SR web-app changes; agents.yaml churn) — neither is in the verified scope, decide before committing.
