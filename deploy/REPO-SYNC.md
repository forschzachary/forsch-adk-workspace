# Repo Sync — what goes to the Hetzner box, what never leaves the laptop

Two repos run the bots. This is the exact split: tracked code that must reach the box, and
the secrets that must NOT (they go out-of-band and are gitignored everywhere).

> **Commits are local-only on the laptop today** (no GitHub push path for these branches).
> So "sync" is either: (a) push the branches to a private remote and `git clone` on the box,
> or (b) `rsync` the trees. Both are covered below. Either way, **secrets travel separately.**

---

## Repo A — forsch-adk-workspace  (branch `feat/screeningroom-huberto`)

### MUST be committed + synced (tracked code)
- `bridge/src/forsch/adk_bridge/*.py` — the bot code:
  `discord_main.py`, `discord_bot.py`, `discord_identity.py`, `cat_persona.py`,
  `ops_persona.py`, `curator_persona.py`, `screening_room_tools.py`, `ops_tools.py`,
  `ops_diagnostics.py`, `curator_tools.py`, `friend_memory.py`, `onboarding_tools.py`,
  `knowledge_tools.py`, `audit_log.py`, `rate_limit.py`, `request_watcher.py`.
- `bridge/src/forsch/adk_bridge/knowledge/*.md` — the distilled stack/onboarding/site knowledge.
- `packages/adk-components/src/**` — resolved on PYTHONPATH by the bots.
- `bridge/pyproject.toml`, `bridge/bridge_config.yaml` — dep + config source of truth.
- **`deploy/`** (this directory) — `Dockerfile`, `docker-compose.yml`, the `.service` unit,
  `screeningroom.env.example`, `cli.json.example`, `DEPLOY-RUNBOOK.md`, `REPO-SYNC.md`.
- `packages/live-agent-graph/**` — needed to regenerate + publish `agent-graph-v2.json`.

### MUST NOT be committed / synced via git (gitignored — go out-of-band)
- `deploy/screeningroom.env` — Discord tokens + LiteLLM key. (gitignore rule added; only the
  `.example` is tracked.)
- `.adk-local.env` — the laptop's local bot env (already gitignored).
- `data/friends/*.json` — per-friend records / profiles. (`data/` runtime data; never track.)
- `data/audit.jsonl` — audit log.
- `.forsch/discord_sessions.db` — ADK SQLite sessions (gitignored: `.forsch/`, `*.db`).
- Any `*.db` / `*.sqlite*`.

> On the box these runtime files are CREATED fresh under the mounted workspace
> (`/workspace/data/`, `/workspace/.forsch/`). Do not copy the laptop's friend records unless
> migrating real members — if so, `rsync` `data/friends/` separately and deliberately.

---

## Repo B — screening-room  (branch `feat/sr-stack-diagnose`)

### MUST be committed + synced
- `scripts/sr` — the zero-dep Node CLI the bots shell out to (the only runtime-critical file
  for the bots). Verify with `node --check scripts/sr` before syncing.
- `src/lib/tv-programmer.ts`, `src/app/api/tv/**`, `src/lib/admin-auth.ts`,
  `src/lib/supabase-server.ts` — only if the SR Next app is also (re)deployed from this box;
  the bots themselves need only `scripts/sr`.
- `package.json` / `package-lock.json` — for the Next app build, not for the `sr` CLI (it has
  zero deps).

### MUST NOT be committed / synced via git (gitignored)
- `.env*` (incl. `.env.local`) — Supabase + SR app secrets. (gitignored already.)
- `deploy-vercel.sh` — plaintext secrets (gitignored already).
- `node_modules/`, `.next/`, `.vercel/`, `.mimocode/`.
- **`~/.config/screening-room/cli.json`** — this is NOT in the repo at all; it lives in the
  user config dir. On the box it goes to `/opt/screeningroom/secrets/cli.json` and is mounted
  read-only into the container. Only `deploy/cli.json.example` (in repo A) is tracked.

---

## Secrets — the out-of-band checklist (carry to the box, never git)

| Secret | Lands at (box) | Source | In any repo? |
|---|---|---|---|
| Discord bot tokens + LiteLLM key | `deploy/screeningroom.env` | Zach's ledger | No (`.example` only) |
| sr CLI creds (11 keys) | `secrets/cli.json` | Zach's ledger / `~/.config/screening-room/cli.json` | No (`.example` only) |

`chmod 600` both on the box. Never echo a token to a log or a Discord channel. The audit log
(`data/audit.jsonl`) and all bot logging are designed to be password-free — keep it that way.

---

## Sync mechanics

**Option A — git (preferred once a private remote exists):**
```bash
# laptop:
git -C ~/Dev/forsch-adk-workspace push <private-remote> feat/screeningroom-huberto
git -C ~/Dev/screening-room       push <private-remote> feat/sr-stack-diagnose
# box: clone both (see DEPLOY-RUNBOOK.md §2).
```

**Option B — rsync (no remote; excludes secrets + junk):**
```bash
rsync -av --filter=':- .gitignore' \
  --exclude '.git' --exclude 'node_modules' --exclude '.next' \
  ~/Dev/forsch-adk-workspace/  root@<box>:/opt/screeningroom/forsch-adk-workspace/
rsync -av --filter=':- .gitignore' \
  --exclude '.git' --exclude 'node_modules' --exclude '.next' \
  ~/Dev/screening-room/        root@<box>:/opt/screeningroom/screening-room/
# secrets go SEPARATELY, by hand:
scp ~/.config/screening-room/cli.json root@<box>:/opt/screeningroom/secrets/cli.json
# (then fill deploy/screeningroom.env on the box from the .example)
```
`--filter=':- .gitignore'` makes rsync honor each repo's gitignore, so `.env*`, `data/`,
`.forsch/`, `node_modules/` etc. are skipped automatically — but always eyeball the dry-run
(`rsync -n`) first.

---

## Ongoing updates (after first deploy)
- **Code change** to an already-wired bot → `git pull` (or rsync) + `docker compose -f deploy/docker-compose.yml restart screeningroom-bots`. No rebuild.
- **New Python/Node dependency** → `git pull` + `... build` + `... up -d`.
- **`screeningroom.env` change** → `... up -d` (recreate; env loads at container create, NOT on restart).
