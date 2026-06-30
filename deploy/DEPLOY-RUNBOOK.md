# ScreeningRoom — Hetzner Deploy Runbook

Run this **with Zach**, top to bottom, on a fresh Hetzner box. It stands up the two (or
three) native ADK Discord bots — Huberto (friend DMs) + screening_ops (team-social) +
optional curator — as one persistent Docker service. The bots shell out to the zero-dep
`sr` CLI to drive the Ultra.cc media stack.

> **Decision:** Docker + docker-compose (not a bare venv). The image bakes Python + Node
> deps; the forsch.* code is *mounted*, so `git pull` + restart ships new code without a
> rebuild. systemd is offered only as a boot-time wrapper around the same compose stack
> (`deploy/screeningroom-bots.service`).

> **Nothing here pushes to GitHub or mutates a live Discord/Jellyfin/SR-1 state until the
> final smoke test, which is gated and observed.** Stop at any failing pre-check.

---

## 0. Inputs to have in hand before you start

- Hetzner box: IP, root (or sudo) SSH access.
- Secrets (Zach brings these — none live in the repo):
  - **Bot env** (→ `deploy/screeningroom.env`): `LITELLM_BASE_URL`, `LITELLM_HERMES_KEY`,
    `HUBERTO_DISCORD_BOT_TOKEN`, `COMPANION_LEAD_DISCORD_BOT_TOKEN`, and (optional, Phase 6)
    `CURATOR_DISCORD_BOT_TOKEN` + `CURATOR_EXPECTED_BOT_ID`. Public ids/defaults
    (`HUBERTO_EXPECTED_BOT_ID`, `COMPANION_LEAD_EXPECTED_BOT_ID`, `OPS_CHANNEL_ID`,
    `SR_ADMIN_DISCORD_IDS`) are pre-filled in `screeningroom.env.example`.
  - **sr CLI creds** (→ `secrets/cli.json`, 11 keys): `SR_URL`, `SR_ADMIN_TOKEN`,
    `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `JELLYSEERR_URL`, `JELLYSEERR_API_KEY`,
    `PROWLARR_URL`, `PROWLARR_API_KEY`, `NZBGET_URL`, `NZBGET_USER`, `NZBGET_PASS`.
    (Heads-up: the altHUB indexer VIP was expired — renew or drop it in Prowlarr.)
- Both repo branches: forsch `feat/screeningroom-huberto`, screening-room `feat/sr-stack-diagnose`.

A working layout on the box (used throughout):
```
/opt/screeningroom/
├── forsch-adk-workspace/      # this repo (feat/screeningroom-huberto)
├── screening-room/            # the sr CLI + Next app (feat/sr-stack-diagnose)
└── secrets/
    └── cli.json               # sr CLI creds (gitignored, chmod 600)
```

---

## 1. Provision the box

```bash
ssh root@<HETZNER_IP>

# Base packages + Docker Engine + compose plugin.
apt-get update && apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version && docker compose version    # both must print
```
*(On Ubuntu, swap `debian` → `ubuntu` in the two URLs.)*

---

## 2. Sync both repos

Clone both onto the box on their feature branches. Use HTTPS+token or a deploy key Zach
provides; this runbook does not embed credentials.

```bash
mkdir -p /opt/screeningroom/secrets && cd /opt/screeningroom

git clone --branch feat/screeningroom-huberto <forsch-adk-workspace remote> forsch-adk-workspace
git clone --branch feat/sr-stack-diagnose      <screening-room remote>      screening-room

# Confirm branches:
git -C forsch-adk-workspace rev-parse --abbrev-ref HEAD   # feat/screeningroom-huberto
git -C screening-room       rev-parse --abbrev-ref HEAD   # feat/sr-stack-diagnose
```

> If a remote isn't set up yet (commits are local-only on the laptop), `rsync` the two trees
> instead — see **REPO-SYNC.md** for exactly what to send and what to leave behind.

---

## 3. Place secrets (NEVER committed)

```bash
cd /opt/screeningroom/forsch-adk-workspace

# Bot env:
cp deploy/screeningroom.env.example deploy/screeningroom.env
# Fill LITELLM_* + the two (or three) Discord tokens. Public ids are pre-filled.
nano deploy/screeningroom.env
chmod 600 deploy/screeningroom.env

# Point compose at the absolute host paths (uncomment + edit the bottom block of the env file):
#   FORSCH_WORKSPACE=/opt/screeningroom/forsch-adk-workspace
#   SCREENING_ROOM_REPO=/opt/screeningroom/screening-room
#   SR_CLI_CONFIG=/opt/screeningroom/secrets/cli.json

# sr CLI creds:
cp deploy/cli.json.example /opt/screeningroom/secrets/cli.json
nano /opt/screeningroom/secrets/cli.json       # fill all 11 keys
chmod 600 /opt/screeningroom/secrets/cli.json
```

---

## 4. Connectivity pre-checks (from the box — do this BEFORE starting)

These are the morning's real risk. Run each; every one must succeed.

```bash
# Discord API (bots can't connect otherwise):
curl -sI https://discord.com/api/v10/gateway | head -1            # expect 200

# LiteLLM gateway — THE LIKELIEST BLOCKER. Use the real LITELLM_BASE_URL.
# If it's a private/localhost-only gateway, this is where you find out; if so,
# switch docker-compose.yml to `network_mode: host` + a 127.0.0.1 base url.
source deploy/screeningroom.env
curl -sI "${LITELLM_BASE_URL%/}/models" -H "Authorization: Bearer ${LITELLM_HERMES_KEY}" | head -1

# Ultra.cc media stack + SR app (reachable for the sr CLI):
curl -sI https://forschzachary.manitoba.usbx.me/ | head -1
curl -sI "$(grep -oE '"SR_URL"[^,]*' /opt/screeningroom/secrets/cli.json | cut -d'"' -f4)" | head -1
```

---

## 5. sr CLI sanity (no live mutation)

```bash
cd /opt/screeningroom/screening-room
node --version                 # must be >= 20 if running bare; in-container Node is baked in
node --check scripts/sr        # syntax OK, exit 0
# Read-only stack health (uses cli.json; no writes):
HOME=/opt/screeningroom node scripts/sr stack   # or `sr help` if creds aren't placed yet
```

---

## 6. Build + start the bots

```bash
cd /opt/screeningroom/forsch-adk-workspace

# Build the image (deps only; one-time + on dep changes):
docker compose -f deploy/docker-compose.yml --env-file deploy/screeningroom.env build

# Start:
docker compose -f deploy/docker-compose.yml --env-file deploy/screeningroom.env up -d

# Watch boot:
docker compose -f deploy/docker-compose.yml logs -f screeningroom-bots
```

Expected log lines:
- `starting N Discord bot(s): huberto_cat, screening_ops[, screening_curator]`
- per-bot identity confirmation (the fail-closed bot-id guard) — **no** SystemExit.
- no `no gateway configured` and no `no bot tokens` errors.

**Optional — boot on reboot via systemd** (wraps this same compose):
```bash
# Edit WorkingDirectory in the unit to /opt/screeningroom/forsch-adk-workspace first.
sudo cp deploy/screeningroom-bots.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now screeningroom-bots
```

---

## 7. Verify (gated live checks — observe each)

1. **Bots connected:** logs show each identity online; `docker ps` shows
   `screeningroom-bots` healthy and `restart: unless-stopped`.
2. **Huberto answers a DM:** DM Huberto `whats on sr1` → he replies with the live SR-1
   slot (proves gateway + sr CLI + Jellyfin reach).
3. **Ops answers a mention:** in the team-social channel, `@screening_ops pipeline_health`
   → terse stack health (proves Prowlarr/NZBGet/Servarr reach).
4. **sr stack reachable:** `docker compose exec screeningroom-bots node /screening-room/scripts/sr stack`
   → no "unreachable" lines.
5. **Persistence across restart:**
   ```bash
   docker compose -f deploy/docker-compose.yml restart screeningroom-bots
   ls /opt/screeningroom/forsch-adk-workspace/data/friends/      # records intact
   ls /opt/screeningroom/forsch-adk-workspace/.forsch/discord_sessions.db   # session db intact
   ```
   Friend records + the session DB survive (they live in the bind-mounted workspace, not
   the container layer).

---

## 8. Publish the graph (after Phase 1 lands)

The hosted cockpit reads `agent-graph-v2.json` from disk and won't auto-update. After the
graph swap merges:
```bash
cd /opt/screeningroom/forsch-adk-workspace
python3 packages/live-agent-graph/build_live_graph.py --all > packages/live-agent-graph/agent-graph-v2.json
# then redeploy / re-pull the cockpit host (Railway) so it serves the fresh file.
```

---

## Rollback

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/screeningroom.env down   # stop bots
git -C /opt/screeningroom/forsch-adk-workspace checkout <previous-good-sha>             # revert code
docker compose -f deploy/docker-compose.yml --env-file deploy/screeningroom.env up -d   # restart
```
Friend data + sessions are untouched by a code rollback (separate from the code tree only
by path, both under the mounted workspace — they persist).

---

## Known risks (carry into the session)

- **LiteLLM gateway unreachable from Hetzner (HIGH).** Step 4 is the gate. If private, use
  `network_mode: host` + a localhost base url, or open egress with Zach.
- **Expiring creds.** Verify `sr stack` works from the box (step 5) before going live;
  altHUB VIP was expired.
- **Single-process watcher** (proactive "your movie's ready" DM) dies with the bot — fine
  for v1; a separate poller is a later option.
- **`network_mode: host` vs bridge.** Default compose uses the bridge network; flip to host
  only if the gateway is localhost-only on the box.
