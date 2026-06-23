# D5: Architectural writeup — Paperclip reborn vs Hermes orchestrator front-end

**Date:** 2026-06-23  
**Status:** Complete

## The question

Does the Live Agent Graph want to be Paperclip reborn, or the front end for the Hermes team-lead/orchestrator architecture?

## What Paperclip was

Paperclip (Nous Research, 2024-2025) was an AI agent orchestration system built around a visual graph. Its core principles:

- **Code is canonical.** The graph was a projection over a manifest. Hand-editing a file and the graph noticing were the same event.
- **Honest projection.** A lying map was worse than no map. The graph reflected actual state, not aspirational state.
- **Read-only reflection.** Paperclip displayed the system. It didn't change it. Agents were authored elsewhere; the graph was documentation.

Paperclip was killed by its own ambition — the sync mechanism was fragile, the manifest format was hand-maintained, and the gap between "what the graph shows" and "what's actually running" kept growing.

## What we built in this spike

1. **Code→graph projection** (`build_live_graph.py`): scans `agents.yaml` + filesystem, auto-detects state (blank/building/built/live/error), evaluates quality gates (L0-L3), derives contracts from type + tools. 37 nodes, 37 links, zero hand-editing of the manifest.

2. **Graph→code write path** (`spawn_agent.py`): creates a real agent on disk from a graph interaction — package dir, web wrapper, agents.yaml entry, graph rebuild. State progression proven: blank → building (L0) → building (L1+L2) → built (L3).

3. **Live pulse** (`/pulse` endpoint + directional particles): polls bridge/authsome/LiteLLM health every 3 seconds, colors active edges green, animates particles on live traffic paths. 19 active edges, 20 live nodes right now.

4. **Lens switching**: same dataset, four views — all nodes, tier (by type), lineage (click an agent to see its dependency tree), live only (dim everything not passing traffic).

## The architectural fork

| Dimension | Paperclip path | Orchestrator path | What we built |
|-----------|---------------|-------------------|---------------|
| Code→graph | Read-only projection | Read-only projection | ✅ Both |
| Graph→code | Not supported | Spawn, wire, configure | ✅ Spawn proven |
| State detection | Manual | Auto-detected from live checks | ✅ Auto-detected |
| Quality gates | None | Per-type gate ladder (L0-L3) | ✅ Implemented |
| Builder agents | None | Domain specialists that graduate into orchestrators | Schema defined, not built |
| Live traffic | None | Directional particles on active edges | ✅ Working |
| Lens switching | None | Tier/lineage/live views | ✅ Working |

## Verdict: Paperclip's spiritual successor with hands

The Live Agent Graph is **not** Paperclip reborn. It inherits Paperclip's core principle — "code is canonical, graph is honest projection" — but adds the write path that Paperclip never had. It's Paperclip's spiritual successor, with hands.

The trajectory is toward the **Hermes orchestrator front-end**. Here's why:

1. **The spawn path changes the category.** A graph that can create agents is not a documentation tool — it's a control surface. Paperclip was a mirror; this is a cockpit.

2. **The gate ladder is an orchestrator concept.** L0→L3 per-type quality gates aren't about display — they're about managing agent lifecycle. "This agent is building, it needs a tool to reach L1" is an operator's concern, not a documentarian's.

3. **Builder agents complete the loop.** The schema defines `builder` as a node type with `role: plain → builder → orchestrator`. A builder agent standing on a slice can see the whole graph but only puts hands on its focused slice. That's team-lead architecture — domain specialists with scoped authority.

4. **The live pulse is a traffic monitor.** Directional particles on active edges is free infrastructure observability. You can see which agents are actually passing messages without checking logs.

## What it would take to go full orchestrator front-end

The spike proved the atom (code↔graph sync works). The molecule would be:

- **Builder agents that are real nodes.** The `builder` type exists in the schema but no builder agent has been spawned. A router-builder that can spawn agents off itself, a tooling-builder that can add tools to agents, a UI-builder that can wire web entrypoints.
- **Contract-checked wiring.** Dragging an edge between two nodes should validate that the source's `emits` matches the target's `accepts`. The schema has the data; the interaction isn't built.
- **Slice-scoped AI sidecar.** Click a slice, get a chat panel scoped to that slice's builder agent. "Add a CRM health check tool to the ops agent" → builder validates contract, edits agents.yaml, regenerates.
- **Graduation path.** `role: plain → builder → orchestrator`. An agent that consistently clears L3 and has builder capabilities can graduate to orchestrator — it can spawn and manage other agents.

## What would keep it as "pretty read-only diagram"

If the write path proves too fragile in practice (spawn creates files but the bridge needs manual restarts, agents.yaml edits conflict with factory regeneration, gate checks drift from reality), then the honest move is to cap it at D2: a live read-only projection that stays honest to code. That's still valuable — it's Paperclip done right, with auto-detected state instead of hand-maintained manifests.

But the spike didn't hit those failure modes. The write path worked. The gate checks stayed honest. The pulse reflected live state. The kill criteria weren't triggered.

## Recommendation

**Build toward the orchestrator front-end, one slice at a time.** The atom is proven. Don't build all builder agents at once — pick one slice (e.g., the ops agent + its CRM tools), make it builder-capable, prove the full loop (see→spawn→wire→graduate) on that slice, then expand.

The graph is already live at `http://127.0.0.1:8888` on the cloud box. It's not a static diagram. It's a projection that can write back. That's the threshold Paperclip never crossed.
