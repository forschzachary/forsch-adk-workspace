# Live Agent Graph / PADI Control Surface Handoff

Date: 2026-06-26
Repo: `/Users/zacharyforsch/Dev/live-agent-graph`
Origin: `https://github.com/forschzachary/live-agent-graph.git`
Live box: `root@100.120.21.13:/root/.hermes/workspace/adk/live-agent-graph`
Live URL: `https://graph.forschfrontiers.com`

## Current State

- Local `main` is clean and matches `origin/main`.
- Live Hetzner checkout is clean at `ee091a2`.
- Latest deployed commit: `ee091a2 Keep PADI shelf nodes pinned`.
- No live service restart was needed after pull; the deployed surface serves static `index.html` from the repo.
- Local preview is normally run with:

```bash
GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898
```

Then review:

```text
http://127.0.0.1:8898/?review=1782501510163#cluster=shelby
http://127.0.0.1:8898/?review=1782501510163#cluster=client-acme
```

## What Just Shipped

The PADI lane control surface went through several iterations. The final accepted direction is:

- PADI shelf controls are real ForceGraph nodes, not static DOM overlays.
- They live in graph coordinates under their lane title.
- They should not use a packing algorithm.
- They should not visually scale or resize with zoom.
- If a user drags one, it snaps back to its assigned slot.
- The compact pill shelf should remain organized to the left under the lane label.

The most recent fix in `ee091a2` added:

- `snapPadiControlNode(node)` in `index.html`.
- ForceGraph `.onNodeDrag(...)` and `.onNodeDragEnd(...)` hooks for `padiControl` nodes only.
- A wrapped `.legend-note` class so the right-panel helper text stays visible.

Verification performed before shipping:

- `python3 -m pytest -q` -> `4 passed`.
- Local in-app browser screenshot showed the PADI shelf still graph-native and compact.
- Manual drag check: dragging a shelf pill returned it to the same assigned slot.
- Live box fast-forwarded to `ee091a2`.
- Public HTML confirmed to include `snapPadiControlNode`, `onNodeDrag`, and `legend-note`.

## Design Rule To Preserve

Do not convert the PADI shelf controls back into screen-fixed UI.

The user explicitly wants them to feel like part of the force graph:

- use graph coordinates,
- pin them under the lane title,
- keep their visual size readable,
- and make them return to their assigned coordinates if moved.

The accepted behavior is not "static UI that ignores graph movement." It is "graph nodes with fixed slot coordinates and screen-stable drawing metrics."

## Code Map

Primary file: `index.html`

Important regions:

- PADI constants: `PADI_CONTROL_*`, `PADI_LIBRARY_*`, `PADI_NODE_Y_OFFSET`.
- Zoom-neutral control spacing:
  - `padiControlScale()`
  - `padiControlLayoutUnits(px)`
- Shelf slotting:
  - `layoutPadiControlShelf(laneIndex, controls)`
  - uses fixed columns/rows, not packing.
- Shelf snapback:
  - `snapPadiControlNode(node)`
  - ForceGraph drag hooks call this for `padiControl` nodes.
- PADI layout:
  - `layoutPadi()`
  - keeps normal nodes lane-targeted and shelf controls fixed.
- PADI drawing:
  - `padiControlRect(node, scale)`
  - `drawPadiControlNode(...)`
  - divides dimensions/font by current graph scale so controls remain readable.
- Right panel helper note:
  - CSS `.legend-note`
  - markup under the Agent status legend.

Do not reintroduce these older/static-anchor ideas:

- `padiShelfAnchors`
- `capturePadiShelfAnchors`
- `invalidatePadiShelfAnchors`
- `padiScreenToGraph`
- viewport-static/screen-anchor shelf placement
- a dynamic packing algorithm for the agent pills

## Auth / API Notes

`serve.py` protects mutating endpoints with `X-Graph-Secret`.

Key behavior:

- `GRAPH_SERVER_SECRET` is the server-side secret.
- Local preview should set `GRAPH_SERVER_SECRET=localtestsecret`.
- Browser unlock stores the secret in `sessionStorage`.
- Mutating calls use `mutationHeaders()` / `graphSecretHeaders()`.
- `/chat-token` also requires the graph secret.

Relevant shipped endpoints/functions:

- `/new-cluster`
- `/save-agent`
- `/wire`
- `/chat-token`
- `/chat`
- `ensureGraphSecret()`
- `fetchChatToken()`

## Deploy Procedure

After local commit:

```bash
git push origin main
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 \
  'cd /root/.hermes/workspace/adk/live-agent-graph && git pull --ff-only && git rev-parse --short HEAD && git status -sb'
```

Public marker check:

```bash
curl -fsSL https://graph.forschfrontiers.com/index.html \
  | rg -n "snapPadiControlNode|legend-note|onNodeDrag"
```

Expected after this handoff:

```text
ee091a2
## main...origin/main
```

## Open Threads

1. Hubert chat needs user testing.
   - UI button exists in the right panel.
   - `/chat-token` and `/chat` are wired through graph secret auth.
   - The user wants to test this next.

2. Shelby assistant work is likely next.
   - Current browser tab is on `#cluster=shelby`.
   - User said they want to work on Shelby's assistant and possibly build tools locally.

3. Repeatable PADI control components.
   - The agent shelf format is now close enough.
   - Next useful work is to apply the same graph-native, fixed-slot control pattern to other lane libraries/tools without changing the accepted interaction model.

4. Auth is still conceptually tangled.
   - The current state is functional, but the iframe/Frappe/standalone auth story still wants a cleanup pass.
   - Be careful not to weaken `X-Graph-Secret` on mutation/chat endpoints.

## Quick Commands

Local health:

```bash
git status -sb
python3 -m pytest -q
```

Live health:

```bash
ssh -i ~/.ssh/zachfleet_vps root@100.120.21.13 \
  'cd /root/.hermes/workspace/adk/live-agent-graph && git rev-parse --short HEAD && git status -sb'
```

Review locally:

```bash
GRAPH_SERVER_SECRET=localtestsecret python3 serve.py 8898
open "http://127.0.0.1:8898/?review=1782501510163#cluster=shelby"
```

