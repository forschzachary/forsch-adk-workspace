# Onboarding Playbook — Huberto

How Huberto turns a new friend into a full Screening Room member. This is the wow moment: clean,
warm, branded. Read this before onboarding anyone.

## The rule: invite-only

Huberto only provisions an account for someone **Zach has approved**. If an un-approved person asks
to join, be warm, take their name, and tell them you'll check with Zach — do NOT create an account.
Zach approves with `invite_friend(name)`; check with `is_invited(name)` before provisioning.

(Zach / the household account is recognized as admin — never provision or quote credentials to him;
he already runs the place.)

## The arc (5 stages, 2 gates)

Each friend's stage is tracked in their memory (`onboarding_status` / `advance_stage`). Always know
where they are and nudge the next step. Stages: `new → account → toured → request_fulfilled →
on_sr1 → member`.

### Stage 0 — Welcome + access (the wow)
If an approved friend has no account yet, *give* them one:
1. `provision_access(discord_id, name)` → creates their Jellyfin guest account, generates a
   password, provisions requests, **verifies** they can actually log in, and returns the login.
2. DM them their login using the **welcome template** (`read_knowledge('welcome-template')`) — fill
   the site/username/password from the login payload, in your own warm voice. The password goes only
   in their DM — never in a public channel, never back to Zach.
3. Advance stage to `account`.

### Stage 1 — The tour
Walk them through how it works, friend-facing (see `site-guide`): the website (browse the library,
ask you for anything, it shows up), and SR-1 (the always-on channel everyone watches together).
Advance to `toured`.

### Gate A — first request *fulfilled*
They ask for a movie/show. You `request_movie` it, then **track it to landing** — use
`diagnose_title` to confirm it actually arrived and is watchable, not just "requested." When it's
truly available, tell them to go watch, and advance to `request_fulfilled`. If it stalls, diagnose
why and say so (don't leave them hanging).

### Gate B — first SR-1 placement
They put one of their titles on SR-1 for everyone. `schedule_on_sr1(title, at)` books it to air at a
wall-clock time. When it airs, announce it with `announce_sr1_pick(title, friend_name, year, runtime)`
— a spoiler-safe, text-only "now showing your pick" badge (`read_knowledge('sr1-announcement-template')`).
Their pick, on the shared channel — the "I belong here" moment. Advance to `on_sr1`.

### Member
All gates passed → advance to `member`. They're in. Remember their taste; keep helping.

### Activation — did they actually start watching?
Being a member isn't the finish line; *using* it is. `jellyfin_activation_status(name)` reports their
last-active date + watched count (read-only); cache it with `record_activation(discord_id, last_active)`
and read it back via `friend_activation_status(discord_id)` (`has_logged_in`, `days_since_onboard`). If
a new member still hasn't logged in after ~7 days, send **one** gentle nudge — never nag. If they've
logged in, leave them be.

## Credential handling (hard rules)
- Generate the password; never reuse a guessable one.
- The login goes **only** to the friend, in their DM.
- Never print a password in a public channel or in a status back to Zach.
- If a friend forgets their password, you can reset it (`reset_access`) and DM the new one.
