#!/usr/bin/env python3
"""Emit a per-cluster Live Agent Graph v2 manifest.

Reads from the cluster-tabs directory model:
  registry/agents/agents.yaml  — canonical agent definitions (single source of truth)
  shared/components.yaml       — tools, models, connections common to all clusters
  clusters/<name>/cluster.yaml — membership list (agent ids, references not copies)

Usage:
  python3 build_live_graph.py --cluster ops          # emit ops cluster manifest
  python3 build_live_graph.py --cluster ops > agent-graph-v2.json

Without --cluster, falls back to the legacy ADK workspace scan.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from workspace_resolver import workspace_root

SPIKE_DIR = Path(__file__).resolve().parent
ADK_WS = workspace_root() / "adk"  # real ADK workspace for filesystem gate checks

# ── Validation schemas (disk-first, CRM-second — gatekeeper before builder) ──

VALID_STATUSES = ("blank", "planning", "building", "stable", "archived")
DEFAULT_MAX_DELEGATION_DEPTH = 3  # depth 0..3 (human → agent → agent → agent → escalate)


class RoutingConfig(BaseModel):
    """Cluster-level routing rules. Lives under cluster.yaml `routing:` block."""
    max_delegation_depth: int = Field(default=DEFAULT_MAX_DELEGATION_DEPTH, ge=1, le=10)


class ClusterConfig(BaseModel):
    """Schema for clusters/<name>/cluster.yaml"""
    name: str
    description: str = ""
    members: list[str] = Field(default_factory=list, min_length=1)
    config: dict = Field(default_factory=dict)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)

    @field_validator("members")
    @classmethod
    def no_duplicates(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError(f"duplicate agent ids in members: {v}")
        return v


class ProjectMeta(BaseModel):
    """Schema for clusters/<name>/project.md front-matter"""
    goal: str = ""
    status: str = "blank"
    handoff_pct: int = Field(default=0, ge=0, le=100)
    data_connectors: list[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status '{v}' not in {VALID_STATUSES}")
        return v


class AgentDef(BaseModel):
    """Schema for one agent entry in registry/agents/agents.yaml"""
    description: str = ""
    discord_channels: list[str] = Field(default_factory=list)
    safety_level: str = "read_only"
    purpose: str = ""
    tools: list[str] = Field(default_factory=list)
    model: str = ""
    role: str = "plain"
    group: str | None = None


class AgentRegistry(BaseModel):
    """Schema for registry/agents/agents.yaml"""
    version: int = 1
    defaults: dict = Field(default_factory=dict)
    agents: dict[str, AgentDef] = Field(default_factory=dict)


class TaskDef(BaseModel):
    """Schema for a GP Task routed to an agent. Lives in clusters/<name>/tasks.yaml"""
    id: str
    title: str = ""
    agent_id: str
    cluster_id: str
    parent: str | None = None
    chain: list[str] = Field(default_factory=list)
    depth: int = Field(default=0, ge=0)

    @field_validator("chain")
    @classmethod
    def no_cycles(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError(f"cycle detected: duplicate agent in chain {v}")
        return v

    @field_validator("depth")
    @classmethod
    def matches_chain(cls, v: int, info) -> int:
        chain = info.data.get("chain", [])
        if chain and v != len(chain):
            raise ValueError(f"depth {v} does not match chain length {len(chain)}")
        return v


def validate_task_chain(task: TaskDef, cluster_members: list[str], max_depth: int) -> list[str]:
    """Validate a task's routing chain against cluster rules. Returns errors (empty = valid).

    Checks:
      1. agent_id is a member of the target cluster
      2. every agent in chain is a member of the target cluster
      3. depth does not exceed max_delegation_depth
      4. no cycles in chain (already caught by TaskDef validator, double-checked here)
    """
    errors: list[str] = []

    if task.agent_id not in cluster_members:
        errors.append(f"agent '{task.agent_id}' not in cluster members: {cluster_members}")

    for aid in task.chain:
        if aid not in cluster_members:
            errors.append(f"chain agent '{aid}' not in cluster members: {cluster_members}")

    if task.depth > max_depth:
        errors.append(
            f"depth {task.depth} exceeds max_delegation_depth {max_depth} — "
            f"only escalation to human allowed at this depth"
        )

    # Double-check no cycles (belt-and-suspenders with TaskDef validator)
    if len(task.chain) != len(set(task.chain)):
        errors.append(f"cycle detected in chain: {task.chain}")

    return errors


def validate_cluster(cluster_name: str) -> list[str]:
    """Validate a cluster's config files. Returns list of error messages (empty = valid).

    Checks:
      1. cluster.yaml exists and parses against ClusterConfig
      2. project.md exists with valid front-matter
      3. every member id exists in registry/agents/agents.yaml
      4. no duplicate agent ids across membership
    """
    errors: list[str] = []

    cluster_yaml = SPIKE_DIR / "clusters" / cluster_name / "cluster.yaml"
    project_md = SPIKE_DIR / "clusters" / cluster_name / "project.md"
    registry_yaml = SPIKE_DIR / "registry" / "agents" / "agents.yaml"

    # 1. cluster.yaml
    if not cluster_yaml.exists():
        errors.append(f"cluster.yaml missing: {cluster_yaml}")
    else:
        try:
            raw = yaml.safe_load(cluster_yaml.read_text()) or {}
            ClusterConfig.model_validate(raw)
        except ValidationError as e:
            errors.append(f"cluster.yaml invalid ({cluster_yaml}): {e}")
        except yaml.YAMLError as e:
            errors.append(f"cluster.yaml parse error ({cluster_yaml}): {e}")

    # 2. project.md
    if not project_md.exists():
        errors.append(f"project.md missing: {project_md}")
    else:
        try:
            text = project_md.read_text()
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    front = yaml.safe_load(parts[1]) or {}
                    ProjectMeta.model_validate(front)
                else:
                    errors.append(f"project.md has no closing --- front-matter delimiter: {project_md}")
            else:
                errors.append(f"project.md missing front-matter (no opening ---): {project_md}")
        except ValidationError as e:
            errors.append(f"project.md front-matter invalid ({project_md}): {e}")
        except yaml.YAMLError as e:
            errors.append(f"project.md front-matter parse error ({project_md}): {e}")

    # 3. cross-file: every member must exist in registry
    if registry_yaml.exists():
        try:
            reg_raw = yaml.safe_load(registry_yaml.read_text()) or {}
            reg = AgentRegistry.model_validate(reg_raw)
            if cluster_yaml.exists():
                try:
                    cluster_raw = yaml.safe_load(cluster_yaml.read_text()) or {}
                    member_ids = cluster_raw.get("members", [])
                    for mid in member_ids:
                        if mid not in reg.agents:
                            errors.append(f"agent '{mid}' in cluster '{cluster_name}' not found in registry ({registry_yaml})")
                except yaml.YAMLError:
                    pass  # already caught above
        except ValidationError as e:
            errors.append(f"registry invalid ({registry_yaml}): {e}")
        except yaml.YAMLError as e:
            errors.append(f"registry parse error ({registry_yaml}): {e}")
    else:
        errors.append(f"registry missing: {registry_yaml}")

    # 4. task chain validation (if tasks.yaml exists)
    tasks_yaml = SPIKE_DIR / "clusters" / cluster_name / "tasks.yaml"
    if tasks_yaml.exists():
        try:
            tasks_raw = yaml.safe_load(tasks_yaml.read_text()) or {}
            task_list = tasks_raw.get("tasks", [])
            if cluster_yaml.exists():
                try:
                    cluster_raw = yaml.safe_load(cluster_yaml.read_text()) or {}
                    member_ids = cluster_raw.get("members", [])
                    routing = cluster_raw.get("routing", {})
                    max_depth = routing.get("max_delegation_depth", DEFAULT_MAX_DELEGATION_DEPTH)
                    for t in task_list:
                        try:
                            task = TaskDef.model_validate(t)
                            chain_errors = validate_task_chain(task, member_ids, max_depth)
                            errors.extend(chain_errors)
                        except ValidationError as e:
                            errors.append(f"task '{t.get('id', '?')}' invalid ({tasks_yaml}): {e}")
                except yaml.YAMLError:
                    pass  # already caught above
        except yaml.YAMLError as e:
            errors.append(f"tasks.yaml parse error ({tasks_yaml}): {e}")

    return errors


# ── CLI ──

parser = argparse.ArgumentParser(description="Build per-cluster agent graph manifest")
parser.add_argument("--cluster", help="Cluster name (reads clusters/<name>/cluster.yaml)")
parser.add_argument("--validate", action="store_true", help="Validate cluster configs only (no manifest output)")
args = parser.parse_args()

# ── Validation gate (disk-first — fail loud before anything touches the graph) ──

if args.cluster:
    errors = validate_cluster(args.cluster)
    if errors:
        print(f"VALIDATION FAILED for cluster '{args.cluster}':", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        sys.exit(1)
    if args.validate:
        print(f"Cluster '{args.cluster}' — all checks passed.")
        sys.exit(0)

# ── Load data sources ──

if args.cluster:
    # Cluster-tabs model
    registry_yaml = SPIKE_DIR / "registry" / "agents" / "agents.yaml"
    shared_yaml = SPIKE_DIR / "shared" / "components.yaml"
    cluster_yaml = SPIKE_DIR / "clusters" / args.cluster / "cluster.yaml"

    if not cluster_yaml.exists():
        print(f"ERROR: cluster '{args.cluster}' not found at {cluster_yaml}", file=sys.stderr)
        sys.exit(1)

    registry = (yaml.safe_load(registry_yaml.read_text()) or {}).get("agents", {}) if registry_yaml.exists() else {}
    shared = yaml.safe_load(shared_yaml.read_text()) if shared_yaml.exists() else {}
    cluster_def = yaml.safe_load(cluster_yaml.read_text()) or {}
    member_ids = cluster_def.get("members", [])
    cluster_config = cluster_def.get("config", {})

    # Build the working agent set: only registry agents that are cluster members
    agents = {aid: registry[aid] for aid in member_ids if aid in registry}

    # Shared tool/model/connection lists
    SHARED_TOOLS = set(shared.get("tools", []))
    SHARED_MODELS = set(shared.get("models", []))
    CONNECTIONS = shared.get("connections", {})
    TOOL_CONN = shared.get("tool_connections", {})
else:
    # Legacy mode: read from ADK workspace
    agents_yaml = ADK_WS / "agent_specs" / "agents.yaml"
    agents = (yaml.safe_load(agents_yaml.read_text()) or {}).get("agents", {}) if agents_yaml.exists() else {}
    SHARED_TOOLS = set()
    SHARED_MODELS = set()
    CONNECTIONS = {
        "github": "GitHub (OAuth)",
        "resend": "Resend (email)",
        "cloudflare-global": "Cloudflare (global)",
        "frappe-crm": "Frappe CRM (ff-ops-prod)",
    }
    TOOL_CONN = {
        "get_crm_health_snapshot": "frappe-crm",
        "list_recent_crm_leads": "frappe-crm",
    }

# ── Filesystem paths for gate checks (always point at real ADK workspace) ──

components_dir = ADK_WS / "components" / "src" / "forsch" / "adk_components" / "tools"
bridge_compose = ADK_WS / "bridge" / "compose.yaml"

# ── State detection helpers ──

def agent_artifact_exists(aid: str) -> bool:
    agent_py = ADK_WS / "agents" / aid / "src" / "forsch" / f"agent_{aid}" / "agent.py"
    return agent_py.exists()

def agent_on_bridge(aid: str) -> bool:
    if not bridge_compose.exists():
        return False
    return f"agents/{aid}/src" in bridge_compose.read_text()

def tool_exists(tool_name: str) -> bool:
    if not components_dir.exists():
        return False
    for f in components_dir.glob("*.py"):
        try:
            if f"def {tool_name}" in f.read_text():
                return True
        except PermissionError:
            continue
    return False

def tool_has_tests(tool_name: str) -> bool:
    test_dir = ADK_WS / "components" / "tests"
    if not test_dir.exists():
        return False
    for tf in test_dir.glob("test_*.py"):
        if tool_name in tf.read_text():
            return True
    return False

def model_responds(model_name: str) -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-S", "-m", "5", "http://127.0.0.1:4000/v1/models"],
            capture_output=True, text=True
        )
        return r.returncode == 0 and model_name in r.stdout
    except Exception:
        return False

def authsome_healthy() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-S", "-m", "3", "http://127.0.0.1:7998/health"],
            capture_output=True, text=True
        )
        return r.returncode == 0 and '"status":"ok"' in r.stdout
    except Exception:
        return False

def bridge_healthy() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-S", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}",
             "http://127.0.0.1:8800"],
            capture_output=True, text=True
        )
        return r.returncode == 0 and r.stdout.strip().isdigit()
    except Exception:
        return False

def roundtrip_live(agent_id: str) -> bool:
    cache_file = SPIKE_DIR / ".roundtrip_cache.json"
    try:
        if cache_file.exists():
            cache = json.loads(cache_file.read_text())
            return cache.get(agent_id, {}).get("success", False)
    except Exception:
        pass
    return False

# ── Gate checkers ──

def check_gates(node_type: str, node_id: str, aid: str | None = None) -> dict:
    gates = {"L0": False, "L1": False, "L2": False, "L3": False}

    if node_type == "agent":
        if aid and agent_artifact_exists(aid):
            agent_py = ADK_WS / "agents" / aid / "src" / "forsch" / f"agent_{aid}" / "agent.py"
            try:
                compile(agent_py.read_text(), str(agent_py), "exec")
                gates["L0"] = True
            except SyntaxError:
                pass
        if aid and aid in agents and agents[aid].get("tools"):
            gates["L1"] = True
        if aid and agent_on_bridge(aid):
            gates["L2"] = True
        if aid and roundtrip_live(aid):
            gates["L3"] = True
        elif bridge_healthy():
            gates["L3"] = True

    elif node_type == "tool":
        tool_name = node_id.replace("tool:", "")
        if tool_exists(tool_name):
            gates["L0"] = True
        if tool_has_tests(tool_name):
            gates["L1"] = True
        if gates["L1"]:
            gates["L2"] = True

    elif node_type == "intake":
        gates["L0"] = True
        gates["L1"] = True

    elif node_type == "router":
        gates["L0"] = True
        gates["L1"] = True
        if bridge_healthy():
            gates["L2"] = True
            gates["L3"] = True

    elif node_type == "database":
        gates["L0"] = True
        gates["L1"] = True
        if authsome_healthy():
            gates["L2"] = True

    elif node_type == "ui":
        gates["L0"] = True
        gates["L1"] = True
        if bridge_healthy():
            gates["L2"] = True

    return gates

def derive_state(node_type: str, gates: dict) -> str:
    required = {
        "agent": 4, "router": 4,
        "tool": 3, "ui": 3, "database": 3,
        "intake": 2,
    }
    needed = required.get(node_type, 2)
    cleared = sum(1 for v in gates.values() if v)
    if cleared == 0:
        return "blank"
    elif cleared < needed:
        return "building"
    elif cleared == needed:
        return "built"
    else:
        return "live"

def derive_contract(node_type: str, aid: str | None = None) -> dict:
    if node_type == "agent":
        tools = agents.get(aid, {}).get("tools", []) if aid else []
        channels = agents.get(aid, {}).get("discord_channels", []) if aid else []
        return {
            "accepts": [f"message:{c}" for c in channels] + ["instruction"],
            "emits": ["response", "tool_call"] + [f"tool:{t}" for t in tools],
        }
    elif node_type == "tool":
        return {"accepts": ["tool_call"], "emits": ["tool_result"]}
    elif node_type == "intake":
        return {"accepts": ["external_message"], "emits": ["routed_message"]}
    elif node_type == "router":
        return {"accepts": ["routed_message"], "emits": ["agent_message"]}
    elif node_type == "database":
        return {"accepts": ["query"], "emits": ["data"]}
    elif node_type == "ui":
        return {"accepts": ["user_input"], "emits": ["display"]}
    return {"accepts": [], "emits": []}

# ── Build graph ──

nodes: dict = {}
links: list = []

def node(nid, name, kind, shared=False, **kw):
    entry = {"id": nid, "name": name, "kind": kind, "shared": shared, **kw}
    if nid in nodes:
        nodes[nid].update(entry)
    else:
        nodes[nid] = entry

def link(s, t, kind):
    links.append({"source": s, "target": t, "kind": kind})

# ── Shared layer: tools, models, connections (flagged shared:true) ──

for tname in SHARED_TOOLS:
    node(f"tool:{tname}", tname, "tool", shared=True)
for mname in SHARED_MODELS:
    node(f"model:{mname}", mname, "logic", shared=True)

node("authsome", "authsome (broker)", "database", shared=True)
for cid, cname in CONNECTIONS.items():
    node(f"cred:{cid}", cname, "database", shared=True)
    link("authsome", f"cred:{cid}", "brokers")
for tool_leaf, conn in TOOL_CONN.items():
    if f"tool:{tool_leaf}" in nodes:
        link(f"tool:{tool_leaf}", f"cred:{conn}", "authenticates-via")

# Bridge UI (shared across all clusters)
node("ui:bridge", "Chainlit Bridge", "ui", shared=True)
node("ui:cockpit", "Builder Cockpit", "ui", shared=True)

# ── Cluster members: agents + their deps ──

for aid, a in agents.items():
    nid = f"agent:{aid}"
    node(nid, aid, "agent")

    if (g := a.get("group")):
        node(f"group:{g}", g, "router")
        link(nid, f"group:{g}", "wears")

    for t in a.get("tools", []) or []:
        # Tool may be in shared layer OR cluster-specific (not shared)
        tid = f"tool:{t}"
        if tid not in nodes:
            node(tid, t, "tool", shared=False)
        link(nid, tid, "uses")

    for c in a.get("discord_channels", []) or []:
        node(f"chan:{c}", c, "intake")
        link(nid, f"chan:{c}", "listens")

# ── Enrich with state/artifact/contract/gates/role ──

type_map = {
    "agent": "agent", "tool": "tool",
    "intake": "intake", "router": "router", "database": "database",
    "ui": "ui", "group": "router", "channel": "intake",
    "credential": "database", "broker": "database",
    "capability": "capability", "logic": "logic",
}

for n in list(nodes.values()):
    nid = n["id"]
    ntype = n["kind"]
    n["type"] = type_map.get(ntype, ntype)

    # Artifact
    if ntype == "agent":
        aid = nid.replace("agent:", "")
        n["artifact"] = f"agents/{aid}/src/forsch/agent_{aid}/agent.py"
        n["model"] = agents.get(aid, {}).get("model", "nvidia-deepseek-v4-flash") if aid else "nvidia-deepseek-v4-flash"
    elif ntype == "tool":
        tname = nid.replace("tool:", "")
        n["artifact"] = f"components/src/forsch/adk_components/tools/*.py (def {tname})"
    elif ntype in ("intake", "channel"):
        n["artifact"] = "Discord channel config"
    elif ntype in ("router", "group"):
        n["artifact"] = "agents.yaml group field"
    elif ntype in ("database", "credential", "broker"):
        n["artifact"] = "authsome vault"
    elif ntype == "ui":
        n["artifact"] = "bridge/compose.yaml" if "bridge" in nid else "builder/pyproject.toml"
    elif ntype == "logic":
        n["artifact"] = "LiteLLM config"

    # Gates
    aid = nid.replace("agent:", "") if ntype == "agent" else None
    n["gates"] = check_gates(n["type"], nid, aid)

    # State
    n["state"] = derive_state(n["type"], n["gates"])
    n["reachable"] = bridge_healthy() if n["type"] in ("agent", "router", "ui") else False

    # Contract
    n["contract"] = derive_contract(n["type"], aid)

    # Role
    if ntype == "agent":
        aid = nid.replace("agent:", "")
        n["role"] = agents.get(aid, {}).get("role", "plain") if aid else "plain"
    else:
        n["role"] = "plain"

# ── Merge capabilities (rail dependencies) ──

cap_file = SPIKE_DIR / "capabilities.json"
extra_nodes: list = []
extra_links: list = []
if cap_file.exists():
    try:
        cap_data = json.loads(cap_file.read_text())
        extra_nodes = cap_data.get("nodes", [])
        extra_links = cap_data.get("links", [])
    except Exception:
        pass

all_nodes = list(nodes.values()) + extra_nodes
all_links = links + extra_links

# ── Prune orphan shared tools (shared tools not linked to any cluster agent) ──

# Find tools that have a direct link to/from an agent node
agent_linked_tools = set()
for l in all_links:
    s = l["source"] if isinstance(l["source"], str) else l["source"].get("id", "")
    t = l["target"] if isinstance(l["target"], str) else l["target"].get("id", "")
    if s.startswith("agent:") and t.startswith("tool:"):
        agent_linked_tools.add(t)
    if t.startswith("agent:") and s.startswith("tool:"):
        agent_linked_tools.add(s)

# Remove shared tool nodes that no cluster agent uses
# Also remove their non-agent links (tool -> cred/cap links become orphans)
pruned_tool_ids = set()
all_nodes = [n for n in all_nodes if not (
    n.get("shared") and n.get("type") == "tool" and n["id"] not in agent_linked_tools
) or (pruned_tool_ids.add(n["id"]) and False)]

# Clean up links that referenced pruned tools
all_links = [l for l in all_links
    if (l["source"] if isinstance(l["source"], str) else l["source"].get("id","")) not in pruned_tool_ids
    and (l["target"] if isinstance(l["target"], str) else l["target"].get("id","")) not in pruned_tool_ids
]

# Recount
output_node_count = len(all_nodes)

# ── Emit ──

output = {
    "version": 2,
    "cluster": args.cluster or "legacy",
    "nodes": all_nodes,
    "links": all_links,
    "node_count": len(all_nodes),
    "link_count": len(all_links),
    "meta": {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": f"registry/agents/agents.yaml + shared/components.yaml + clusters/{args.cluster}/cluster.yaml" if args.cluster else "agents.yaml + filesystem scan + capabilities.json",
    },
}

print(json.dumps(output, indent=2))
