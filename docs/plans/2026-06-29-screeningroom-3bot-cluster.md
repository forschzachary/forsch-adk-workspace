# ScreeningRoom — 3-bot cluster (detailed goal, for review)

> **Status:** plan for review — nothing built yet. Grounded in a 4-front codebase research pass
> (current screening bot, tool-library gaps, ADK memory + ScreeningRoom auth, bridge routing).
> **Served through the Discord bot** (the `bridge`) — all three bots are Discord surfaces.

## The shape

ScreeningRoom goes from **one bot** to a **3-bot cluster**, with the main bot as the router. All
three are served through the existing Discord bridge (channel/mention routing), and a new
inter-bot delegation layer lets them hand off and suggest to each other.

| Bot | id | Discord home | Biggest lift | Done = |
|---|---|---|---|---|
| **Main / friend** | `screening` | `#screening-room` | personality, 1:1 social, routing | a friend is **logged in** + the bot **stored memory** for them |
| **Ops** | `screening-ops` | `#screening-ops` | sheer volume of "things to do" | accounts accessible · media requests fulfilled · webhooks healthy · storage managed · media tagged |
| **Curator / events** | `screening-curator` | `#screening-tv` | successful events, TV traffic, engagement | events start on time · lineup curated · people watch/engage |

## What exists vs what must be built (the honest grounding)

**Exists today:**
- `screening` agent = a single-user TMDB **discovery engine** (7 tools, all *placeholder* TMDB
  calls), writing to **one global unscoped JSONL store** (`data/screening_store.jsonl`) — no
  identity, no per-user scoping, no memory, no onboarding, no routing. (`screening_tools.py`)
- **Real auth already exists** in the ScreeningRoom Next.js app: Jellyfin-backed
  `POST /api/auth/login` + `GET /api/auth/session` (HttpOnly `sr_session` cookie). So "logged in"
  is a real, callable check — we do **not** build auth, we *call* it.
- ADK ships memory services (`InMemoryMemoryService` dev / `VertexAiMemoryBankService` prod) with
  per-`(app_name, user_id)` scoping and `add_memory` / `search_memory`.
- The **bridge already serves agents to Discord**: `gateway/router.py` resolves
  channel/@mention → agent; **one `Runner` per agent**; `bridge_config.yaml` maps channels→agents.
- Ops already has real box tools: `execute_bash_command`, `read_host_file`, `write_host_file`,
  `check_service_health`.

**Must be built:** per-user memory + onboarding (friend), media-fulfillment / webhook / storage /
tagging tools (ops), event-scheduler / TV-guide / lineup / bumps / surveys (curator), and an
**inter-bot delegation layer** in the bridge (today there is *no* cross-agent handoff).

---

## Bot 1 — `screening` (main / friend-facing)

**Identity:** warm, knows you, opinionated about film, 1:1. The face of ScreeningRoom and the
**router**: it talks to friends and delegates operational/event work to the other two bots.

**Onboarding (this defines "done"):**
1. On first contact, call `check_login(user)` → `GET /api/auth/session` with the user's
   `sr_session` cookie. `401` → reply with the login link and stop. `200` → capture the Jellyfin
   `user_id`.
2. Persist continuity: `session.state["user:logged_in"]=true`, `["user:jellyfin_id"]=<id>`.
3. Store at least one **friend memory** for that user (their name + a fact), keyed by Jellyfin id.
4. **Success check (machine-verifiable):** `user:logged_in == true` **AND** ≥1 stored memory for
   that `user_id`. (This is exactly an eval/`/goal` success check.)

**Tools to build:** `check_login(user)` (wraps `/api/auth/session`), `remember_friend(user_id,
fact, tags)`, `recall_friend(user_id, query)`, `get_user_state(user_id)`; and **re-scope the
existing movie tools per-user** (today they're global). Plus the delegation tool (below).

**Memory backend — decision point (see Open decisions):** recommend a **custom per-user store
(SQLite keyed by Jellyfin `user_id`)** exposed through the ADK memory interface — it persists
across restarts and stays self-hosted (no Vertex; `InMemoryMemoryService` doesn't persist).

**Channels:** `#screening-room`. **Safety:** `local_write`.

---

## Bot 2 — `screening-ops`

**Identity:** terse, proactive operator. Biggest "to-do" lift. Each success metric maps to a tool:

| Success metric (yours) | Tool(s) to build | Notes |
|---|---|---|
| People can get in / access accounts | `account_status(user)` → `/api/auth/session` + Jellyfin user policy | calls the real auth; surfaces who's locked out |
| Media-request success (all sources used + called) | `request_media`, `call_media_source`, `log_fulfillment(all_sources_used, per_source_result)`, `get_request_status` | the audit trail is the metric |
| Webhooks/callbacks load properly | `receive_callback`, `get_webhook_events`, `webhook_health` | inbound event log |
| Storage/space + proactive issues | `check_disk_usage(path)`, `alert_storage(threshold)`, `storage_history` | surfaces to `#screening-ops` before it's a problem |
| All media properly tagged | `tag_media`, `search_tags`, `get_media_audit(untagged)` | flags untagged media |

**Tools that exist:** `execute_bash_command`, `read/write_host_file`, `check_service_health`.
**Channels:** `#screening-ops`. **Safety:** `local_write` (it acts on the box).

---

## Bot 3 — `screening-curator` (events / TV)

**Identity:** the showrunner. **Mostly autonomous** — curates the bumps/TV lineup on its own.
**Signature capability:** when someone **books an event for a time**, it schedules it on the TV and
**recalibrates the guide/timings so that title starts at the booked time** (shifting the
surrounding lineup). It also **suggests** ideas to the main bot ("MTV hour — only music videos,
start at 6/7/8/9?").

**Tools to build:** `create_screening_event(title, start_time, ...)`, **`recalibrate_guide(target_title,
start_at)`** (the hard one — shift the lineup so a title hits a wall-clock start), `build_tv_guide`,
`rank_lineup` / `generate_lineup`, `make_bump` / `render_bump`, `create_survey` / `post_survey` /
`collect_votes`, `suggest_to_main(idea)` (via the delegation/suggestion channel).

**Key dependency (decision):** what *is* the "TV"? The box runs **Jellyfin** (per the auth finding) —
the guide is likely Jellyfin Live TV / scheduled playback, but confirm (Jellyfin vs Plex vs
Kaleidescape vs a custom player). `recalibrate_guide` is only as real as that backend.

**Channels:** `#screening-tv` (+ posts surveys into `#screening-room` *via* the main bot).
**Safety:** `local_write`.

---

## Inter-bot routing + Discord serving (the "served through the Discord bot" part)

**Today:** the bridge routes Discord → one agent by channel/@mention; agents are independent (one
`Runner` each); **no cross-agent handoff exists.** So we add a thin delegation layer:

1. **`cluster.yaml` roles:** `members: [{name: screening, role: main}, {name: screening-ops,
   role: delegated}, {name: screening-curator, role: delegated}]` + a `delegation` block.
2. **`bridge_config.yaml`:** map `#screening-room`→screening, `#screening-ops`→screening-ops,
   `#screening-tv`→screening-curator, and declare who may delegate to whom.
3. **`DelegationRouter`** (new, in the bridge): `delegate_to_agent(target, context)` runs the
   target agent under a derived session and returns its reply; `suggest_to_main(suggestion)`
   queues a curator suggestion into the main bot's next turn.
4. **`delegate_to_agent` tool** on the main bot (main → ops/curator) and **`suggest_to_main`** on
   the curator. The main bot's instruction learns: operational question → ops; event/TV → curator.

**Delegation UX (decision):** synchronous ("one sec, asking ops…" then the answer) vs async (the
delegate posts separately). Recommend synchronous for v1 (simplest, in-channel).

---

## Files this touches

- **Manifest** (`agent_specs/agents.yaml`): new `screening-ops` + `screening-curator` blocks;
  update `screening` (identity + memory/onboarding/delegation tools, per-user scoping).
- **Cluster** (`clusters/ScreeningRoom/cluster.yaml`): 3 members + roles + delegation config.
- **Bridge** (`bridge_config.yaml` + new `delegation.py` + HTTP endpoints).
- **New tool modules** (`packages/adk-components/.../tools/`): `screeningroom_auth.py`,
  `friend_memory.py`, `media_fulfillment.py`, `webhook_handler.py`, `storage_monitor.py`,
  `media_tags.py`, `event_scheduler.py`, `tv_guide.py`, `lineup_curator.py`, `bumps_engine.py`,
  `survey_tool.py`, `delegation.py`.

## Phased build (the scaffold order)

- **Phase 0 — scaffold (review this first):** add the two agent shells (`screening-ops`,
  `screening-curator`) to the manifest, set cluster roles, wire all three into `bridge_config.yaml`
  with their channels. Result: three runnable Discord bots with *placeholder* tools — the skeleton
  you can see and poke.
- **Phase 1 — friend memory + onboarding** (the success-defining piece): `check_login` +
  per-user memory + the onboarding flow + per-user movie scoping. Eval: onboarding completes.
- **Phase 2 — ops tools:** the five tool modules mapped to the success metrics above.
- **Phase 3 — curator:** event scheduler + `recalibrate_guide` + surveys/suggestions.
- **Phase 4 — delegation layer:** `DelegationRouter` + tools, so main ↔ ops/curator and
  curator → main work through the bridge.
- **Phase 5 — evals:** an eval set per bot (dogfood the flywheel); each phase can be a `/goal` run.

## Evals (success metrics → eval sets)

- **friend:** an onboarding turn ends with `user:logged_in` + a stored memory; a returning friend
  is recalled by name.
- **ops:** media-request success rate; a storage alert fires over threshold; untagged media is flagged.
- **curator:** an event scheduled for T starts at T; a survey is posted and votes collected.

## Open decisions for you (the review)

1. **Memory backend:** custom per-user **SQLite keyed by Jellyfin id** (recommended, self-hosted,
   persistent) vs ADK `VertexAiMemoryBankService` (cloud — against the no-Vertex grain).
2. **TV backend:** what drives the "TV" guide — Jellyfin Live TV, Plex, Kaleidescape, custom? This
   gates `recalibrate_guide`.
3. **Names + channels:** `screening-ops` / `screening-curator`; `#screening-ops` / `#screening-tv`.
4. **Delegation UX:** synchronous in-channel vs async separate posts.
5. **v1 scope:** recommend **Phase 0 (scaffold) + Phase 1 (friend onboarding/memory)** first, since
   onboarding is what defines "done" for the friend bot.

---

# v2 — grounded in research (this supersedes the assumptions above)

A second research pass (the real media stack + the existing companions/cat/memory systems to
leverage) changed three things. All credentials referenced by name only; tokens live in gitignored
env, never committed.

## The TV/media backend is real — and it's the heart of it

**SR-1** (`~/Dev/screening-room`, canonical HEAD `0a7db6b`) is an **always-on linear TV channel
anchored to wall-clock time** — tune in at 8:14, you're 14 min into what's airing, same for everyone.
- **Programmer** (`src/lib/tv-programmer.ts`): deterministic, genre-blocked shuffle + bumps/idents,
  extends a 24h horizon; Supabase tables `channels` / `programs` / `pool_items`. Renderers: Jellyfin
  (direct/HLS), YouTube (seek-to-offset), ident cards. API: `/api/tv/now|guide|program|pool|stream`.
- **Media stack:** request → **Jellyseerr** → **Radarr/Sonarr** → **Ultra.cc** seedbox → **Jellyfin**
  library. App routes: `POST /api/request`, `GET /api/incoming` (lifecycle: requested→searching→
  downloading→importing). Auth: `GET /api/auth/session` (Jellyfin).
- **Two facts that shape the curator:** (a) there is **no wall-clock recalibration today** — the
  programmer assigns `starts_at` monotonically and never shifts the lineup, so "make this start at the
  booked time" is a **new capability**; (b) the **LM "companion bridge" to the programmer was severed
  2026-06-24** (v1 is deterministic-only) — the curator bot effectively **reconnects** that bridge.
- ⇒ The bots' media/TV/auth tools are **thin clients over the screening-room HTTP API** (the stack is
  already wired there); we don't re-implement Jellyseerr/Radarr/Jellyfin.

## Architecture pivot: serve through the **companions** system, not a new forsch bridge

The companions system (`~/Dev/Hubert/companions`, **canonical**, git 2026-06-26) already has ~80% of
what these social bots need — so we **reuse it** rather than rebuild on the forsch bridge:
- **Discord serving:** `discord.py` (`router.py`), **multi-bot** (one `Client` per token — already
  runs Huberto + a mirror token, so adding the cat + companion-lead is the established pattern).
- **DM:** `proactive_queue.py` (`configure_bot_token`, `_open_dm` via REST `/users/@me/channels`,
  `_send_dm_with_retry`) + reactive `on_message`.
- **Slash `/commands`:** `slash_commands/commands.py` (`setup_slash_commands`, auth, guild+global sync)
  — this is your prior `/commands` work.
- **Identity guard:** `discord_identity.py` (`verify_identity`, fail-closed vs the expected bot id).
- **Per-user memory:** `workspace/people/{label}.json` + `memory/{label}/MEMORY.md`
  (`## Relationship` / `## Compiled facts`), injected by `build_friend_context()` (pure Python, no
  Hubert imports — directly portable), + per-user history (`relay_core.py`). Skip the offline email
  indexer (`~/Projects/hubert-memory`, stale, not a repo).

⇒ The three ScreeningRoom bots run as **companion bot identities**: **Huberto** (cat, person-facing,
DM + `/commands`) and **companion-lead** (internal — ops + curator — posting to the HubertAi
team-social channel `1511377396668825662`). **Forsch stays the meta-layer** — the `/goal` engine can
drive the curator's autonomous curation, and factory tools wrap the screening-room API.

## The cat (Huberto, person-facing)

Leverage **cat-companion** (`~/Dev/cat-companion`, canonical, git 2026-06-29) `server/prompt.js`:
lowercase, playful, curious/silly/sneaky, **family-first**, proper spelling. Adapt for Discord DMs +
the Movie-Club social context (recommend titles, remember friends, coordinate watching).
- **Unified-bot loader (your cat-themed "thinking"):** `scratching the post…` / `paws on the post…` /
  `sniffing the air…` / `cleaning whiskers…` + a 🐾 reaction. The load message *is* the personality;
  it never says "asking ops."
- Aesthetic: cat-companion's `.impeccable.md` palette (pink `#ffd6e8` / ink) for embeds.
- Note: in cat-companion's world "Hubert" is the child's orange tabby; **our** Huberto is the lead cat.

## Onboarding (grounded)

`check_login` → screening-room `GET /api/auth/session` (Jellyfin). `401` → DM the login link.
Store a per-friend `MEMORY.md` (reuse the companions schema), keyed Discord `user_id` → Jellyfin user.
**Success = logged in + ≥1 stored fact** (machine-checkable).

## Revised Phase 0 (where it scaffolds)

In the **companions** system: register the **cat** bot (Huberto token) and **companion-lead** bot as
new `Client` identities, reusing `router` / `proactive_queue` / `slash_commands` / `discord_identity`;
tokens into `companions/.env` (gitignored); register the cat's `/commands`; companion-lead posts to the
team-social channel. Add a small **screening-room API client** (auth/request/incoming/tv) as the bots'
tools. Result: Huberto (cat) live in DMs with `/commands`; companion-lead live internally.

## The one decision for you

**Serve through the companions system** (recommended — all the Discord/DM/slash/memory/cat infra and
your tokens are already there) **vs.** rebuild them as forsch ADK agents on the forsch bridge (much
more work, less leverage). I recommend **companions-served**. Confirm and Phase 0 scaffolds there.

---

# v3 — decided architecture + the TV is already a CLI

**Architecture decided (Zach):** NOT the Hermes companions runtime. Build a **first-class, native
ADK Discord bot component in forsch** (DM + slash-commands + persona + per-user memory), *porting the
good patterns* from `~/Dev/Hubert/companions` (`router.py`, `proactive_queue.py`, `slash_commands/`,
the `MEMORY.md` schema, `build_friend_context()`) and re-doing them in ADK. Huberto / companion-lead
are just the bot identities this forsch component runs. This Discord-bot component is itself a reusable
factory deliverable.

## The TV (and the whole SR stack) is ALREADY a first-class CLI: `sr`

`~/Dev/screening-room/scripts/sr` (zero-dep Node, `docs/CLI.md`) was built *"so Huberto can run
everything by shelling out."* It wraps the entire stack via the deployed app's API routes
(`Authorization: Bearer $SR_ADMIN_TOKEN`; config `~/.config/screening-room/cli.json`):

- **TV:** `sr tv now | guide`, `sr tv reprogram [--companion <label>]`, `sr bumps add|list|rm`,
  `sr playlist <name> add|list|rm`
- **Media:** `sr search`, `sr preflight`, `sr request`, `sr requests`, `sr queue [active|approve|
  decline|retry|sync]`
- **Accounts:** `sr users create|provision|passwd|delete`, `sr profiles audit`
- **Events:** `sr events create --starts <time> | announce | cancel` (Discord movie-nights)

⇒ **We do NOT rebuild media/TV/account tools.** The forsch agents' tools are thin wrappers that
**shell out to `sr`** (exactly its design intent). The `sr` CLI is the tool layer; the forsch agents
are the brains; the forsch Discord component is the serving layer.

## TV data model (`src/lib/tv-types.ts`)

- `Program { id, channel_id, starts_at(ISO), duration_s, kind: feature|bump, source:
  jellyfin|youtube|ident, ref, title, meta{posterUrl, year, seriesName, block, copy} }`
- `PoolItem { id, list: "bumps"|"playlist:<name>", source, ref, title, duration_s, meta }`
- `NowPayload { channel, current: Program&{offset_s}|null, next, server_now }`

## The roadmap already points at these bots (`HANDOFF.md` "Needs Backend / Phase 3")

> "LM-backed chat V2 (**new router, not the Huberto companion bridge**)" · "Queue admin panel for
> SR-1" · "Proactive Discord outreach for movie-night scheduling."

The **forsch curator/ops bots ARE that "new router"** — the companion bridge was deliberately severed
(`b2d2003 sever: complete companion removal`); forsch is the intended replacement, LM-assisted on top
of the deterministic programmer.

## The one genuinely-new TV capability

"**Book a title to start at a wall-clock time on SR-1**" does NOT exist. Today: `sr events --starts`
makes a *Discord RSVP event* (not playback); `sr tv reprogram` only *extends* the schedule
monotonically. The curator's signature feature = a new `sr tv schedule <title> --at <time>` + a
programmer change to **insert a Program at `starts_at` and reflow the surrounding lineup**. This is
the curator's flagship build (and the reconnection of LM programming the handoff anticipates).

## Revised build (much smaller than v1/v2)

1. **forsch Discord bot component** (native ADK): DM + slash-commands + persona + memory, ported from
   companions. Runs Huberto (cat) + companion-lead identities. *This is the reusable factory win.*
2. **`sr`-backed agent tools** (curator/ops/friend): wrap `sr tv/queue/request/users/events/...` —
   small shell-out tools, not new integrations.
3. **`sr tv schedule --at` + programmer reflow** — the one new TV capability (curator flagship).
4. **Cat friend bot:** persona (cat-companion) + onboarding (`/api/auth/session`) + per-user memory
   (companions `MEMORY.md` pattern, re-done in ADK).
