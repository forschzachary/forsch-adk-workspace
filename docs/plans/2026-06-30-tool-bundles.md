# Tool Bundles — Implementation Plan

**Date:** 2026-06-30
**Status:** Locked design. Not yet built.
**Scope:** Introduce reusable, named tool *bundles* so an agent declares
`bundles:` (with optional `only` / `exclude`) instead of (or alongside) a flat
`tools:` list. The Factory expands bundles → concrete tool FQNs at render time;
the live graph grows an intermediate `bundle` node layer; the cockpit gets a
collapsible bundle group in the **Tools · Data** lane.

**Hard requirement (the safety contract for this whole change):** the initial
bundle set + per-agent assignments in this plan must expand to *byte-for-byte
the same per-agent tool sets that ship today*. Bundles are a refactor of
**declaration**, not of behavior. Validation = `git diff` on every generated
`agent.py` is empty after `apply --all`.

---

## 0. Why (the lazy-but-precise case)

Today every agent re-lists the same LinkedIn FQNs by hand:
`get_linkedin_brand_brief` appears in brand, social, **and** website. There is
no single place that says "this is the LinkedIn read surface." Adding a new
LinkedIn tool means editing three agents and hoping you got the set right per
agent. Bundles give one definition + per-agent narrowing (`only` / `exclude`),
and the graph/cockpit finally show *why* an agent has a tool (which bundle it
came from), which is the thing the canvas is supposed to make visible.

This is the smallest shape that does that: a top-level `tool_bundles:` map, one
new optional field on `AgentSpec`, one pure expansion function called at the
single hook point that already exists in `plan()`, and additive graph/UI layers.
No new node type semantics beyond "group of tools," no DB, no runtime cost
(expansion is generation-time only — the runnable `agent.py` still sees a flat
list).

---

## 1. LOCKED: `agents.yaml` schema

### 1.1 Top-level `tool_bundles:` block

A new sibling of `defaults:` and `agents:` in
`agent_specs/agents.yaml`. Each bundle is a named group of fully-qualified tool
names plus a human description.

```yaml
version: 1
defaults:
  agent_class: LlmAgent
tool_bundles:                       # NEW top-level key
  linkedin_core:
    description: "LinkedIn read surface: brand brief, metric dashboard, autonomous-action queue."
    tools:
      - forsch.adk_components.tools.get_linkedin_brand_brief
      - forsch.adk_components.tools.get_linkedin_metric_dashboard
      - forsch.adk_components.tools.list_linkedin_autonomous_actions
  # ... (full set in §5)
agents:
  # ... (unchanged structure, plus optional bundles: per agent — §1.2)
```

**Bundle definition shape (locked):**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `description` | str | no (default `""`) | Shown on the bundle node + cockpit group header. |
| `tools` | list[str] | yes | Concrete FQ tool names. Wildcards (`crm.*`) are allowed and pass through to the existing `expand_tools()` step *after* bundle expansion. |

Bundle names are the map keys (e.g. `linkedin_core`). They are an internal
namespace, never an FQ tool name — collisions with tool leaf names are avoided
by always prefixing bundle identifiers (`bundle:<name>`) everywhere outside the
YAML key.

### 1.2 Per-agent `bundles:` field

Each agent gains an optional `bundles:` list. Each entry is **either**:

- a bare string — the bundle name, meaning "all tools in this bundle":
  ```yaml
  bundles:
    - linkedin_core
  ```
- **or** a mapping with a `bundle:` key plus exactly one of `only:` / `exclude:`:
  ```yaml
  bundles:
    - bundle: linkedin_authoring
      exclude:
        - forsch.adk_components.tools.create_linkedin_go_live_plan
    - bundle: linkedin_core
      only:
        - forsch.adk_components.tools.get_linkedin_brand_brief
        - forsch.adk_components.tools.get_linkedin_metric_dashboard
  ```

**`BundleRef` shape (locked):**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `bundle` | str | yes (when mapping form) | Name of a key in `tool_bundles:`. |
| `only` | list[str] | no | Keep ONLY these FQ names from the bundle (intersection). Mutually exclusive with `exclude`. |
| `exclude` | list[str] | no | Drop these FQ names from the bundle (difference). Mutually exclusive with `only`. |

**Locked filter semantics:**
- `only` and `exclude` are **mutually exclusive** on a single ref → validation
  error if both present.
- Both filter against the bundle's own `tools` list. An `only`/`exclude` entry
  that names a tool **not in the bundle** is a validation error (catches typos
  and silent drift — a tool you think you're keeping that the bundle never had).
- Bare-string form == `{bundle: <name>}` with no filter == all tools.

### 1.3 `tools:` + `bundles:` coexist (locked merge order)

An agent may keep an explicit `tools:` list **and** declare `bundles:`. The
final tool list is:

```
final = dedupe_preserving_order( bundle_tools_in_declaration_order  +  explicit_tools )
```

- Bundle tools come first, in the order bundles are declared, each bundle's
  tools in the bundle's own `tools:` order, after applying that ref's
  `only`/`exclude`.
- Explicit `tools:` are appended.
- De-dupe preserves first occurrence (a tool in two bundles, or in a bundle and
  the explicit list, appears once, at its first position).

This ordering rule is what makes "reproduce today exactly" achievable — see §5
where every agent's assignment is checked against its current ordered list.

Agents with neither `bundles:` nor `tools:` (or `tools: []`) are unchanged
(assistant, build).

---

## 2. LOCKED: Factory expansion point

### 2.1 The single hook (already exists)

`factory/src/forsch/adk_factory/cli.py`, function `plan()`, **lines 57–61**.
`plan()` already builds a `model_copy` of the spec to compose the instruction
without mutating the shared manifest object. Bundle expansion goes on that same
copy, immediately after the instruction compose and **before** any renderer
runs:

```python
# cli.py plan(), current lines 57-61
workspace = manifest_path.resolve().parent.parent
spec = spec.model_copy(update={"instruction": compose_instruction(str(workspace), spec)})
# NEW — collapse bundles + explicit tools into one flat ordered list:
spec = spec.model_copy(update={
    "tools": expand_bundles(spec.tools, spec.bundles, manifest.tool_bundles),
    "bundles": [],   # consumed; renderers and downstream never see bundles
})
rendered = {**render_agent(spec), **render_agent_package(spec)}
```

**Why here and nowhere else:**
- It is **after** `load_manifest()` merges `defaults:` (so a future
  `defaults.bundles` would already be folded in).
- It is **before** `render_agent()` (web `root_agent.yaml`) and
  `render_agent_package()` (runnable `agent.py`) — both of which iterate
  `spec.tools` (renderer.py:75 web surface, renderer.py:84 `expand_tools`).
  After this step `spec.tools` is the same flat list shape they get today, so
  **neither renderer changes at all**.
- `apply()` (cli.py:111-135) calls `plan()` for rendering, so it inherits the
  expansion for free. The only thing `apply()` does *before* `plan()` is
  `validate_agent_tools(spec)` on the **un-expanded** spec — see §2.3.

### 2.2 New module: `factory/src/forsch/adk_factory/bundles.py`

Pure, no I/O, no LLM, deterministic — same discipline as the renderer.

```python
"""Collapse per-agent bundle references + explicit tools into one flat tool list.

Generation-time only: the runnable agent.py never knows bundles existed.
"""
from __future__ import annotations

class BundleError(ValueError):
    """Raised on unknown bundle, both only+exclude, or filter naming a tool
    not in the bundle. Fail loud — a silently-wrong tool set is the bug class
    this whole workspace exists to kill."""

def _coerce_ref(ref) -> tuple[str, str | None, list[str]]:
    """Normalize a BundleRef (str | dict) -> (name, mode, names).
    mode is 'only' | 'exclude' | None."""
    if isinstance(ref, str):
        return ref, None, []
    name = ref["bundle"]
    has_only, has_excl = "only" in ref, "exclude" in ref
    if has_only and has_excl:
        raise BundleError(f"bundle ref {name!r}: only/exclude are mutually exclusive")
    if has_only:
        return name, "only", list(ref["only"])
    if has_excl:
        return name, "exclude", list(ref["exclude"])
    return name, None, []

def expand_bundles(tools, bundles, bundle_defs) -> list[str]:
    """tools: list[str] (explicit), bundles: list[str|dict] (refs),
    bundle_defs: dict[name -> {tools: [...], description: str}].
    Returns flat, de-duped, order-preserving list (bundle tools first, then
    explicit). See plan §1.3 for the locked ordering."""
    out: list[str] = []
    for ref in (bundles or []):
        name, mode, names = _coerce_ref(ref)
        if name not in bundle_defs:
            raise BundleError(f"unknown bundle {name!r} (have: {sorted(bundle_defs)})")
        bundle_tools = list(bundle_defs[name].get("tools", []))
        bundle_set = set(bundle_tools)
        for n in names:
            if n not in bundle_set:
                raise BundleError(
                    f"bundle ref {name!r} {mode} names {n!r} which is not in the bundle"
                )
        if mode == "only":
            keep = set(names)
            bundle_tools = [t for t in bundle_tools if t in keep]
        elif mode == "exclude":
            drop = set(names)
            bundle_tools = [t for t in bundle_tools if t not in drop]
        out.extend(bundle_tools)
    out.extend(tools or [])
    seen, deduped = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); deduped.append(t)
    return deduped
```

### 2.3 Model + loader changes

**`factory/src/forsch/adk_factory/models.py`:**
- Add `bundles: list = Field(default_factory=list)` to `AgentSpec` (after
  `tools`, line 36). Type it `list[Union[str, dict]]` — the `dict` is validated
  structurally in `expand_bundles`, not by pydantic, to keep the model dumb.
- Add `tool_bundles: dict[str, "ToolBundle"] = Field(default_factory=dict)` to
  `Manifest` (after `agents`, line 44), with a small `ToolBundle(BaseModel)`:
  `description: str = ""`, `tools: list[str] = Field(default_factory=list)`.

**`factory/src/forsch/adk_factory/loader.py`:**
- `load_manifest()` currently reads `defaults` + `agents` (lines 18-23). Add:
  `tool_bundles = raw.get("tool_bundles") or {}` and pass it into
  `Manifest(..., tool_bundles=tool_bundles)`.
- `defaults` must **not** be merged into bundle definitions (bundles are not
  agents). Bundles are passed through verbatim.

### 2.4 Validation

`factory/src/forsch/adk_factory/validation.py`, `validate_agent_tools()`
lines 442-464, iterates `agent_spec.tools` (line 454) and expands wildcards.
Two options, **locked to option A**:

- **A (locked):** `apply()` validates the agent *before* expansion (current
  call site cli.py:124). Change that call to validate the **expanded** spec so
  the deploy gate sees the real tool set. Concretely: in `apply()`, expand
  bundles into a temp spec first, then `validate_agent_tools(expanded_spec)`.
  This keeps validation honest about what actually ships and reuses the exact
  flat-list code path that exists today — `validate_agent_tools` needs **zero**
  internal change.
- (Rejected B: teach `validate_agent_tools` about bundles — duplicates the
  expansion logic in two places, violates one-definition.)

Add a standalone `validate_bundles(manifest)` that runs `expand_bundles` for
every agent at `forsch validate` time and surfaces `BundleError`s as a
red gate, so a bad `only:` typo blocks before render.

### 2.5 Files touched (factory)

| File | Change |
|---|---|
| `factory/src/forsch/adk_factory/models.py` | `+bundles` on AgentSpec; `+tool_bundles` + `ToolBundle` on Manifest |
| `factory/src/forsch/adk_factory/loader.py` | read `tool_bundles`, pass to Manifest |
| `factory/src/forsch/adk_factory/bundles.py` | **new** — `expand_bundles`, `BundleError`, `validate_bundles` |
| `factory/src/forsch/adk_factory/cli.py` | `plan()` lines 60-61: expand on the copy; `apply()` line 124: validate expanded |
| `factory/src/forsch/adk_factory/renderer.py` | **none** (sees flat `spec.tools` exactly as today) |
| `factory/src/forsch/adk_factory/validation.py` | **none** internal; new `validate_bundles` lives in bundles.py |
| `factory/tests/test_bundles.py` | **new** — see §6 |

---

## 3. LOCKED: graph bundle-node shape

File: `packages/live-agent-graph/build_live_graph.py`. The graph reads
`agents.yaml` directly (it does not import the Factory), so it must learn the
same expansion rules — but additively, so the existing agent→tool layer stays
intact for any agent that doesn't use bundles.

### 3.1 Load bundles

Where the manifest is parsed (near the top of the build, the `agents` dict is
already in scope by the loop at line 617), add:

```python
TOOL_BUNDLES = manifest_raw.get("tool_bundles", {}) or {}
```

### 3.2 Emit bundle nodes + agent→bundle→tool links

Replace the **agent→tool** wiring at lines 625-631. Node/link helpers are
`node()` (line 585) and `link()` (line 592).

Locked node id scheme: `bundle:<agent_id>:<bundle_name>` — bundle nodes are
**per-agent instances**, not shared. Rationale: `only`/`exclude` make the same
bundle resolve to different tool sets per agent, and the cockpit needs to grey
out *this agent's* excluded tools. A shared bundle node could not carry
per-agent active/inactive state.

```python
for aid, a in agents.items():
    nid = f"agent:{aid}"
    node(nid, aid, "agent")
    # ... group wiring unchanged (621-623) ...

    declared_bundles = a.get("bundles", []) or []
    seen_tools = set()

    for ref in declared_bundles:
        name = ref if isinstance(ref, str) else ref.get("bundle")
        only_l   = (ref.get("only")    if isinstance(ref, dict) else None) or None
        excl_l   = (ref.get("exclude") if isinstance(ref, dict) else None) or None
        bdef     = TOOL_BUNDLES.get(name, {})
        all_btools = list(bdef.get("tools", []))

        if only_l is not None:
            active = [t for t in all_btools if t in set(only_l)]
        elif excl_l is not None:
            active = [t for t in all_btools if t not in set(excl_l)]
        else:
            active = list(all_btools)
        inactive = [t for t in all_btools if t not in set(active)]

        bid = f"bundle:{aid}:{name}"
        node(bid, name, "bundle", shared=False,
             bundle_key=name,
             for_agent=aid,
             description=bdef.get("description", ""),
             tools_count=len(active),
             inactive_tools=inactive)        # leaf-or-FQ list, see §3.4
        link(nid, bid, "uses-bundle")        # agent -> bundle

        for t in all_btools:                 # emit ALL member tools as nodes
            tid = f"tool:{t}"
            if tid not in nodes:
                family = TOOL_FAMILY_MAP.get(t, "agent-specific")
                node(tid, t, "tool", shared=False, family=family)
            l = {"source": bid, "target": tid, "kind": "contains"}
            if t not in set(active):
                l["inactive"] = True          # greyed for THIS agent's bundle
            links.append(l)
            seen_tools.add(t)

    # explicit tools that did NOT come via a bundle keep the direct agent->tool link
    for t in a.get("tools", []) or []:
        if t in seen_tools:
            continue
        tid = f"tool:{t}"
        if tid not in nodes:
            family = TOOL_FAMILY_MAP.get(t, "agent-specific")
            node(tid, t, "tool", shared=False, family=family)
        link(nid, tid, "uses")
```

### 3.3 Enrich bundle nodes

The enrichment loop (lines 637-687) sets `type`, `artifact`, `gates`, `state`,
`contract`, `role` per node from `type_map`. Add:

- `type_map["bundle"] = "bundle"` (line 639-645 block).
- In the artifact branch (647-669): `elif ntype == "bundle": n["artifact"] =
  "agent_specs/agents.yaml (tool_bundles:)"`.
- Gates/state: a bundle's state is **derived from its active member tools** —
  green only if every active tool's `gates` are green; else inherit the worst.
  Reuse `check_gates`/`derive_state` over the active tool set so a bundle node
  visually flags "one of your tools is red." `reachable` stays False (it's not a
  runtime surface). `contract` = `{accepts: [agent_message], emits: [tool_call]}`.
  `role` = `"plain"`.

### 3.4 Locked node + link JSON shapes

**Bundle node:**
```json
{
  "id": "bundle:website:linkedin_core",
  "name": "linkedin_core",
  "kind": "bundle",
  "type": "bundle",
  "shared": false,
  "bundle_key": "linkedin_core",
  "for_agent": "website",
  "description": "LinkedIn read surface: brand brief, metric dashboard, autonomous-action queue.",
  "tools_count": 2,
  "inactive_tools": ["list_linkedin_autonomous_actions"],
  "artifact": "agent_specs/agents.yaml (tool_bundles:)",
  "gates": { "...": "derived from active member tools" },
  "state": "built",
  "reachable": false,
  "contract": { "accepts": ["agent_message"], "emits": ["tool_call"] },
  "role": "plain"
}
```

**Links:**
```json
{ "source": "agent:website", "target": "bundle:website:linkedin_core", "kind": "uses-bundle" }
{ "source": "bundle:website:linkedin_core", "target": "tool:get_linkedin_brand_brief", "kind": "contains" }
{ "source": "bundle:website:linkedin_core", "target": "tool:list_linkedin_autonomous_actions", "kind": "contains", "inactive": true }
```

`inactive_tools` stores the same name form the `tool:` node uses (leaf name, as
emitted at line 599/630). Whether that's leaf or FQ must match exactly so the UI
can join `inactive_tools` against the `contains` link targets — pick **leaf**,
consistent with existing tool node names.

### 3.5 capabilities.json merge — unchanged

The native-bot merge (lines 689-708) appends `extra_nodes`/`extra_links`
verbatim and is **untouched**. Native bots (huberto, screening_ops, curator)
keep their direct agent→tool links and do **not** get bundles — they are not
Factory agents. Orphan-tool pruning after the merge still works (bundle
`contains` links count as references, so a bundled tool is never pruned).

---

## 4. LOCKED: cockpit UI approach

File: `packages/live-agent-graph/index.html` (the live cockpit canvas; 3631
lines). Four locked pieces: **(a)** collapsible bundle group in the Tools · Data
lane, **(b)** click-expand to reveal member tools, **(c)** per-agent grey-out of
inactive tools, **(d)** the left picker restricted to bundles.

### 4.1 Lane + node color

- `PADI_LANES` (lines 755-760) is unchanged — bundles live **in** the existing
  `tools` lane (`{ key: 'tools', label: 'Tools · Data', hue: '240,136,62' }`),
  rendered above their member tools. No new swim lane.
- Add a bundle color near the other node colors. Bundle = a slightly desaturated
  gold so it reads as "container of orange tools": e.g. `#d4a574`.

### 4.2 (a) Collapsible bundle group + (b) click-expand

The lane library is rendered by `renderLaneLibraries()` (lines 2321-2362) as a
flat list of `.lane-chip`s pulled from `sp.library()`. Locked approach:

- The **Tools · Data** picker becomes **bundle-first** (see §4.4): each top-line
  chip is a bundle (`.lane-bundle-group`), showing the bundle name + a count
  badge (`tools_count`) + a chevron (`▶` collapsed / `▼` expanded).
- Clicking the chevron toggles a nested `.lane-bundle-children` div listing the
  bundle's member tools as smaller `.lane-chip.tool-child`. Collapsed by default.
- Expand/collapse state persists per bundle name in a module-level
  `Set bundleExpanded` (no sessionStorage needed; cheap, resets on reload — fine
  for a builder canvas).
- Refactor: extract the chip-creation inner loop (2338-2360) into a
  `makeChip(it, laneKey, msgEl)` helper, then `renderLaneLibraries` calls it for
  both bundle children and the other (unchanged) lanes. This avoids forking the
  whole function — the agent/interface/router lanes render exactly as today.

On the **canvas itself**, the new `bundle` node renders like a tool node but
larger, gold, with the count badge. Node rendering is `nodeCanvasObject`
(~line 1809). Add a `node.kind === 'bundle'` branch: draw the gold disc + label
+ small `n` badge. Member-tool nodes sit below it, joined by `contains` links.
Clicking a bundle node on the canvas toggles the same `bundleExpanded` state and
collapses/hides its `contains`-children in the graph view (reuse the existing
lens/collapse filtering that `collapseIntake` already demonstrates for the
interfaces lane).

### 4.3 (c) Per-agent grey-out

Two render contexts, both driven by the `inactive` flag from §3.4:

- **Canvas:** a `contains` link with `"inactive": true`, and its target tool
  node when the focused agent is the bundle's `for_agent`, render dimmed (reuse
  the existing `node.shared` dimming path, ~line 1829 — same reduced-alpha
  treatment). When no agent is focused, draw normally.
- **Left picker children:** when a bundle group is expanded while an agent is in
  focus, member tools listed in that bundle node's `inactive_tools` get the
  `.in-cluster`-style greying (the existing dashed + `opacity:0.3` rule at lines
  80-87, generalized to a `.tool-child.inactive` class). The greyed child shows
  a title like `excluded for <agent> (only/exclude)`.

This is the payoff: a viewer sees `linkedin_core` on `website` with
`list_linkedin_autonomous_actions` greyed because website's ref used `only:` to
drop it — the *reason* an agent has the tools it has becomes legible.

### 4.4 (d) Left picker restricted to bundles

`LANE_SPAWNERS.tool` (lines 2232-2237) currently lists loose tools via
`graphNodeLibrary('tool')` and is `disabled: true`. Locked replacement:

```js
tool: {                                   // the Tools · Data lane spawner
  blankLabel: 'New bundle',               // was 'New tool'
  disabled: true,                         // spawning a brand-new bundle stays out of scope for v1
  library() { return graphBundleLibrary(); },   // bundles, not loose tools
  onDrop(item, msg) { addBundleToAgent(item.id, msg); },  // see below
},
```

- New `graphBundleLibrary()` (modeled on `graphNodeLibrary`, lines 2165-2177):
  returns one entry per **distinct bundle_key** across all `bundle:` nodes,
  `{ id: bundle_key, name, tools_count, children: [member leaf names],
  inCluster: <focused agent already declares this bundle> }`.
- `onDrop`/click → `addBundleToAgent(bundleKey)`: adds a `bundles:` entry to the
  focused agent (the cockpit's existing promote/edit path writes back to
  `agents.yaml`; bundle assignment is a one-line append, not a tool-by-tool add).
  This replaces the old per-tool `inspectGraphNode('tool', ...)` drop.
- The loose-tool picker is **gone** from the lane header. Individual tools are
  reachable only by expanding a bundle (4.2). This is the "left-picker
  restricted to bundles" lock: you compose agents out of bundles, not tools.
- `NODE_PREFIX` (line 2163) gains `bundle: 'bundle'` if any code path needs to
  round-trip bundle ids through it.

### 4.5 Files touched (cockpit)

| File | Anchor | Change |
|---|---|---|
| `packages/live-agent-graph/index.html` | ~759 (`PADI_LANES`) | unchanged; bundles share the `tools` lane |
| | ~1809 (`nodeCanvasObject`) | `bundle` node branch (gold disc + count badge); inactive-tool dimming |
| | ~80-87 (`.lane-chip` CSS) | add `.lane-bundle-group`, `.lane-bundle-children`, `.tool-child`, `.tool-child.inactive` |
| | ~2163 (`NODE_PREFIX`) | `+ bundle` |
| | ~2165 (`graphNodeLibrary`) | add sibling `graphBundleLibrary()` |
| | ~2232 (`LANE_SPAWNERS.tool`) | bundle-first picker; `addBundleToAgent` onDrop |
| | ~2321 (`renderLaneLibraries`) | extract `makeChip`; render collapsible bundle groups for the tools lane |
| `builder/templates/index.html` | (server template, 152 lines) | only if it embeds the picker; verify before editing |

---

## 5. LOCKED: initial bundles + per-agent assignments (reproduce today exactly)

These are derived from the **actual** current `tools:` lists in
`agent_specs/agents.yaml` as of 2026-06-30 (verified line-by-line). The
ordering rule from §1.3 (bundle tools first in declaration order, then explicit,
de-duped) is applied so each agent's expansion equals its current ordered list.

### 5.1 Bundle definitions

```yaml
tool_bundles:
  linkedin_core:
    description: "LinkedIn read surface: brand brief, metric dashboard, autonomous-action queue."
    tools:
      - forsch.adk_components.tools.get_linkedin_brand_brief
      - forsch.adk_components.tools.get_linkedin_metric_dashboard
      - forsch.adk_components.tools.list_linkedin_autonomous_actions

  linkedin_authoring:
    description: "LinkedIn drafting + scoring + go-live + metric-snapshot + observability authoring surface."
    tools:
      - forsch.adk_components.tools.create_linkedin_draft
      - forsch.adk_components.tools.list_linkedin_drafts
      - forsch.adk_components.tools.score_linkedin_draft
      - forsch.adk_components.tools.create_linkedin_go_live_plan
      - forsch.adk_components.tools.record_linkedin_metric_snapshot
      - forsch.adk_components.tools.run_linkedin_observability_cycle

  brand_profile:
    description: "Brand-only LinkedIn surface: draft scoring + staged profile updates."
    tools:
      - forsch.adk_components.tools.score_linkedin_draft
      - forsch.adk_components.tools.stage_linkedin_profile_update

  website_launch:
    description: "Personal-site launch readiness: brief, audit, staged launch tasks."
    tools:
      - forsch.adk_components.tools.get_personal_site_launch_brief
      - forsch.adk_components.tools.audit_personal_site_launch
      - forsch.adk_components.tools.create_website_launch_task

  stability_diagnostics:
    description: "Workspace inventory, git health, import + service checks, host bash + file I/O."
    tools:
      - forsch.adk_components.tools.get_workspace_inventory
      - forsch.adk_components.tools.get_git_state
      - forsch.adk_components.tools.validate_agent_imports
      - forsch.adk_components.tools.check_service_health
      - forsch.adk_components.tools.execute_bash_command
      - forsch.adk_components.tools.read_host_file
      - forsch.adk_components.tools.write_host_file

  household_assistant:
    description: "Grocery logging + reminders for personal assistants."
    tools:
      - forsch.adk_components.tools.log_groceries
      - forsch.adk_components.tools.get_grocery_log
      - forsch.adk_components.tools.add_reminder

  wow_guild_knowledge:
    description: "TBC Classic items, quests, dungeons, bosses, NPCs, and per-player registration."
    tools:
      - forsch.adk_components.tools.search_items
      - forsch.adk_components.tools.get_item_details
      - forsch.adk_components.tools.search_quests
      - forsch.adk_components.tools.get_dungeon_bosses
      - forsch.adk_components.tools.get_boss_loot
      - forsch.adk_components.tools.search_npcs
      - forsch.adk_components.tools.register_player
      - forsch.adk_components.tools.get_player

  ops_telemetry:
    description: "Read-only CRM/business telemetry: health snapshot + recent leads."
    tools:
      - forsch.adk_components.tools.get_crm_health_snapshot
      - forsch.adk_components.tools.list_recent_crm_leads
```

### 5.2 Per-agent assignments + expansion proof

Each agent's current ordered tool list is reproduced. ✓ = expansion byte-equals
today's list (verified against agents.yaml line refs).

**stability** (current lines 37-44, 7 tools) — clean single bundle:
```yaml
    bundles: [stability_diagnostics]
```
Expansion → the 7 diagnostics tools in bundle order = current order. ✓

**ops** (lines 222-224, 2 tools):
```yaml
    bundles: [ops_telemetry]
```
→ `get_crm_health_snapshot, list_recent_crm_leads`. ✓

**shelby** (lines 257-260, 3 tools):
```yaml
    bundles: [household_assistant]
```
→ `log_groceries, get_grocery_log, add_reminder`. ✓

**wow-guild** (lines 291-298, 8 tools) — note current order is
search_items…search_npcs then register_player, get_player; bundle is authored in
that exact order:
```yaml
    bundles: [wow_guild_knowledge]
```
→ matches lines 292-299 exactly. ✓

**social** (lines 153-162, 9 tools). Current order:
`brand_brief, create_draft, list_drafts, score_draft, go_live_plan,
record_snapshot, get_dashboard, run_observability, list_autonomous`.
Bundle order alone can't reproduce this interleave, so use explicit `tools:` for
the exact order and let the bundle assignment be **documentation of provenance**
— BUT that breaks "tools come from bundles." Locked resolution: social declares
both bundles, and because the de-dupe/order rule (§1.3) would reorder, social
**also** pins the explicit order via `tools:` only where ordering diverges.
Cleanest exact-reproduction (locked):
```yaml
    bundles:
      - bundle: linkedin_core
        only: [forsch.adk_components.tools.get_linkedin_brand_brief]
      - bundle: linkedin_authoring
      - bundle: linkedin_core
        only:
          - forsch.adk_components.tools.get_linkedin_metric_dashboard
          - forsch.adk_components.tools.list_linkedin_autonomous_actions
```
Expansion, in declaration order, de-duped:
1. linkedin_core∩{brand_brief} → `get_linkedin_brand_brief`
2. linkedin_authoring → `create_linkedin_draft, list_linkedin_drafts, score_linkedin_draft, create_linkedin_go_live_plan, record_linkedin_metric_snapshot, run_linkedin_observability_cycle`
3. linkedin_core∩{dashboard, autonomous} → `get_linkedin_metric_dashboard, list_linkedin_autonomous_actions`

= `brand_brief, create_draft, list_drafts, score_draft, go_live_plan,
record_snapshot, run_observability, get_dashboard, list_autonomous`.

**⚠ Order check:** current social order has `get_dashboard` (line 160) **before**
`run_observability` (line 161); the expansion above yields `run_observability`
before `get_dashboard`. To match byte-for-byte, split `linkedin_authoring` for
social or append the two as explicit `tools:` in the exact slot. **Locked fix:**
social keeps `bundles: [linkedin_core (only brand_brief), linkedin_authoring
(exclude run_observability + record_snapshot? no)]` — simplest exact match is to
author `linkedin_authoring` tools in social's *consumed* order and let `website`/
others filter. Re-order `linkedin_authoring.tools` to:
`create_draft, list_drafts, score_draft, go_live_plan, record_snapshot,
run_observability` — already matches social positions 2-7 **except** social wants
`get_dashboard` between `record_snapshot` and `run_observability`. Since
`get_dashboard` lives in `linkedin_core`, perfect interleave needs a 3rd ref.
**Final locked social assignment:**
```yaml
    bundles:
      - bundle: linkedin_core
        only: [forsch.adk_components.tools.get_linkedin_brand_brief]
      - bundle: linkedin_authoring
        exclude: [forsch.adk_components.tools.run_linkedin_observability_cycle]
      - bundle: linkedin_core
        only: [forsch.adk_components.tools.get_linkedin_metric_dashboard]
      - bundle: linkedin_authoring
        only: [forsch.adk_components.tools.run_linkedin_observability_cycle]
      - bundle: linkedin_core
        only: [forsch.adk_components.tools.list_linkedin_autonomous_actions]
```
→ `brand_brief, create_draft, list_drafts, score_draft, go_live_plan,
record_snapshot, get_dashboard, run_observability, list_autonomous` =
lines 154-162 exactly. ✓ (This is verbose; see §5.3 Note on ordering.)

**brand** (lines 96-103, 7 tools). Current order:
`brand_brief, score_draft, stage_profile, site_brief, site_audit, dashboard,
list_autonomous`.
```yaml
    bundles:
      - bundle: linkedin_core
        only: [forsch.adk_components.tools.get_linkedin_brand_brief]
      - bundle: brand_profile          # score_draft, stage_profile
      - bundle: website_launch
        only:
          - forsch.adk_components.tools.get_personal_site_launch_brief
          - forsch.adk_components.tools.audit_personal_site_launch
      - bundle: linkedin_core
        only:
          - forsch.adk_components.tools.get_linkedin_metric_dashboard
          - forsch.adk_components.tools.list_linkedin_autonomous_actions
```
→ `brand_brief, score_draft, stage_profile, site_brief, site_audit, dashboard,
list_autonomous` = lines 97-103 exactly. ✓

**website** (lines 190-196, 6 tools). Current order:
`site_brief, site_audit, create_task, brand_brief, dashboard, list_autonomous`.
```yaml
    bundles:
      - website_launch                 # site_brief, site_audit, create_task
      - linkedin_core                  # brand_brief, dashboard, list_autonomous
```
→ exactly lines 191-196 (both bundles authored in matching order). ✓

**assistant** (line 68): `tools: []`, no bundles. Unchanged. ✓
**build** (line 126): `tools: []`, no bundles. Unchanged. ✓

**hubert** (lines 320-324, 4 native tools) — native `forsch.agent_hubert.tools.*`,
NOT component tools. Keep as explicit `tools:`, no bundle. ✓
**agent_logic_specialist** (lines 343-348, 5 native tools) — same, keep
explicit `tools:`. ✓

### 5.3 Note on ordering (the one real wrinkle)

`agent.py` renders tools in list order, but **tool order does not affect agent
behavior** — ADK builds a tool set, not an ordered pipeline. So "reproduce
exactly" has two tiers:

- **Tier 1 (locked target): semantic identity** — every agent gets the *same
  set* of tools. This is the contract that matters and all assignments above
  satisfy it trivially.
- **Tier 2 (nice-to-have): byte-identical `agent.py`** — requires matching list
  *order* too. The verbose social/brand refs above achieve this. If the team
  decides byte-identity isn't worth the verbose multi-ref YAML, **relax to Tier
  1**: author each `*_authoring`/`*_core` bundle once, assign simply
  (`bundles: [linkedin_core, linkedin_authoring]`), accept a re-ordered
  `agent.py`, and update the golden test to compare tool *sets* not *sequences*.

**Recommendation:** ship **Tier 1** (simple assignments, set-equality test). The
ordering gymnastics in §5.2 for social/brand exist only to prove Tier 2 is
*possible*; they are not worth carrying in the manifest. Reorder the bundle
`tools:` lists to the most common consumer's order and move on.

---

## 6. Tests

`factory/tests/test_bundles.py` (new):
- `expand_bundles` happy paths: bare string, `only`, `exclude`, multi-bundle
  order + de-dupe, explicit-tools append + de-dupe.
- `BundleError` paths: unknown bundle; `only`+`exclude` together; `only`/`exclude`
  naming a non-member tool.
- **Golden reproduction test (the safety contract):** for every agent in the
  real manifest, assert `set(expand_bundles(...)) == set(current_tools)` (Tier 1)
  — and if Tier 2 is chosen, `==` on the ordered list.
- End-to-end: `apply --all` into a temp workspace before and after the bundles
  refactor → assert every generated `agent.py` is identical (Tier 2) or
  tool-set-identical (Tier 1).

`packages/live-agent-graph` smoke: run `build_live_graph.py`, assert every
bundled agent has `uses-bundle` links, every bundle node has `contains` links to
all member tools, and `inactive` flags appear exactly where `only`/`exclude`
dropped a tool (e.g. social's `linkedin_core` instance if Tier 2 split is used).

---

## 7. Build order (lazy path)

1. **Factory first, behavior-locked.** Add models + loader + `bundles.py` +
   `plan()` hook. Write `tool_bundles:` + per-agent `bundles:` (Tier 1 simple
   form) into `agents.yaml`. Run golden test → `apply --all` → `git diff` on
   `agents/*/agent.py` must be tool-set-clean. **This is shippable alone** — the
   manifest is tidier and nothing downstream knows or cares yet.
2. **Graph layer.** Teach `build_live_graph.py` the bundle nodes/links. Verify
   the JSON shape (§3.4). Pure data; cockpit still works because it ignores
   unknown node kinds until step 3.
3. **Cockpit.** Bundle node render + collapsible picker + grey-out + bundle-only
   left picker. Verify on the live canvas (the cockpit reads the built graph
   JSON), not a harness.

Each step is independently revertible. Commit per nested repo
(`git -c user.name=Hubert -c user.email=hubert@forsch.local`), local-only.

---

## 8. Open questions (flagged, not blocking)

- **Tier 1 vs Tier 2 ordering** (§5.3) — recommend Tier 1; needs a one-line call.
- **Spawning brand-new bundles from the cockpit** — left `disabled: true` in v1;
  bundles are authored in YAML for now (matches how the tool picker is disabled
  today).
- **`defaults.bundles`** — supported by the hook placement (post-defaults-merge)
  but unused initially; no agent needs a default bundle yet.
