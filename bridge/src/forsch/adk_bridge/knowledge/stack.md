# Screening Room Stack — ops reference

The acquisition pipeline the ops lead watches. Everything runs on the Ultra.cc seedbox
(`forschzachary.manitoba.usbx.me/<app>`), reachable with the keys in `~/.config/screening-room/cli.json`.

## The pipeline
```
Jellyseerr → Radarr (movies) / Sonarr (tv) → Prowlarr → NZBGet (usenet) / rTorrent (torrent) → Jellyfin
                                               ↳ indexers: NZBGeek, NZBPlanet (usenet) · Nyaa, TPB, AnimeTosho (torrent)
                                                           usenet providers (in NZBGet): Frugal, Eweka
```
- **Jellyseerr** — requests + approvals; also the resolver for Radarr/Sonarr connection details.
- **Radarr/Sonarr** — orchestrate the search → grab → import. They fail *because* something below them did.
- **Prowlarr** — the indexer control plane. Auto-disables failing indexers on 24h cooldowns; 4+ in
  cooldown makes searches return nothing. Expired indexer VIP (e.g. altHUB) silently kills a source.
- **NZBGet** — usenet download client (JSON-RPC). News-server "active" count = provider connections.
- **Jellyfin** — playback + accounts.

## How to diagnose (use the tools, never guess)
- `pipeline_health()` (= `sr stack`) — health of every layer: Servarr warnings, Prowlarr indexer
  cooldowns / VIP / health errors, NZBGet provider connections. Answers "is the stack / are the NZB
  sources broken?"
- `diagnose_title(title|tmdbId)` (= `sr diagnose`) — root cause for one title:
  - **no release ever grabbed** → search came back empty (often Prowlarr cooldown / dead indexer).
  - **grabbed but failed** → bad release or download client; a re-search tries another.
  - **in the download client** → stalled/erroring; check the queue line.
  - **already has a file** → acquired; if not visible it's an import/library gap, and Jellyseerr's
    "processing" status is just stale (NOT a reason to cancel).
  - **no entry in Radarr/Sonarr** → Jellyseerr never pushed it; re-approve or `sr queue sync`.

## Posture
Lead with the problem + the exact fix, never a raw dump. You diagnose and recommend; you don't deploy
or delete. "Cancel it" is rarely the right answer — find out *why* first.
