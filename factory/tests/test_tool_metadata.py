"""Tests for tool_metadata: @tool decorator, ToolRegistry, wildcard expansion.

Runs under pytest (the project's configured runner).
"""

import re
import pytest
from forsch.adk_factory.tool_metadata import (
    tool,
    ToolRegistry,
    ToolMeta,
    DESTRUCTIVE_DENYLIST,
)


def _clear_registry():
    from forsch.adk_factory import tool_metadata
    tool_metadata._REGISTRY.clear()


# ── decorator ───────────────────────────────────────────────────────────────

def test_decorator_registers_tool():
    _clear_registry()

    @tool(family="railway", safety="read_only", client="railway", auth="railway")
    def check_health(project_id: str) -> dict:
        """Check Railway project health."""
        return {"status": "ok"}

    tools = ToolRegistry.all_tools()
    assert len(tools) == 1
    meta = list(tools.values())[0]
    assert meta.family == "railway"
    assert meta.safety == "read_only"
    assert meta.client == "railway"
    assert meta.auth == "railway"
    assert meta.description == "Check Railway project health."
    assert "check_health" in meta.name
    assert "project_id" in meta.signature


def test_decorator_defaults():
    _clear_registry()

    @tool(family="crm")
    def get_leads() -> list:
        return []

    meta = list(ToolRegistry.all_tools().values())[0]
    assert meta.safety == "read_only"
    assert meta.client == ""
    assert meta.auth == ""


def test_decorator_preserves_function():
    _clear_registry()

    @tool(family="test")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5
    assert add.__name__ == "add"


def test_decorator_destructive_tier():
    _clear_registry()

    @tool(family="ops", safety="destructive", client="bash", auth="host")
    def run_command(cmd: str) -> str:
        """Execute a shell command."""
        return cmd

    meta = list(ToolRegistry.all_tools().values())[0]
    assert meta.safety == "destructive"


# ── registry queries ────────────────────────────────────────────────────────

def test_by_family():
    _clear_registry()

    @tool(family="railway")
    def a(): pass

    @tool(family="railway")
    def b(): pass

    @tool(family="crm")
    def c(): pass

    assert len(ToolRegistry.by_family("railway")) == 2
    assert len(ToolRegistry.by_family("crm")) == 1
    assert len(ToolRegistry.by_family("unknown")) == 0


def test_by_safety():
    _clear_registry()

    @tool(family="a", safety="read_only")
    def ro(): pass

    @tool(family="b", safety="local_write")
    def lw(): pass

    @tool(family="c", safety="destructive")
    def d(): pass

    assert len(ToolRegistry.by_safety("read_only")) == 1
    assert len(ToolRegistry.by_safety("local_write")) == 1
    assert len(ToolRegistry.by_safety("destructive")) == 1


# ── wildcard expansion ──────────────────────────────────────────────────────

def test_expand_wildcard_literal():
    _clear_registry()
    result = ToolRegistry.expand_wildcard("forsch.tools.railway.check_health")
    assert result == ["forsch.tools.railway.check_health"]


def test_expand_wildcard_family():
    _clear_registry()

    @tool(family="railway")
    def check_health(): pass

    @tool(family="railway")
    def deploy(): pass

    result = ToolRegistry.expand_wildcard("railway.*")
    assert len(result) == 2
    assert any("check_health" in r for r in result)
    assert any("deploy" in r for r in result)


def test_expand_wildcard_unknown_family():
    _clear_registry()
    result = ToolRegistry.expand_wildcard("nonexistent.*")
    assert result == []


def test_expand_wildcard_empty_registry():
    _clear_registry()
    result = ToolRegistry.expand_wildcard("anything.*")
    assert result == []


# ── families ────────────────────────────────────────────────────────────────

def test_families_structure():
    _clear_registry()

    @tool(family="railway", safety="read_only", client="railway", auth="railway")
    def check_health(): pass

    @tool(family="railway", safety="read_only", client="railway", auth="railway")
    def list_projects(): pass

    @tool(family="crm", safety="read_only", client="frappe", auth="frappe")
    def get_leads(): pass

    families = ToolRegistry.families()
    assert set(families.keys()) == {"railway", "crm"}
    assert families["railway"]["safety"] == "read_only"
    assert len(families["railway"]["tools"]) == 2
    assert families["railway"]["clients"] == ["railway"]
    assert families["railway"]["auths"] == ["railway"]
    assert families["crm"]["clients"] == ["frappe"]


# ── families.yaml generation ────────────────────────────────────────────────

def test_generate_families_yaml():
    _clear_registry()
    pytest.importorskip("yaml")

    @tool(family="railway", safety="read_only", client="railway", auth="railway")
    def check_health(): pass

    yaml_str = ToolRegistry.generate_families_yaml()
    assert "version: 1" in yaml_str
    assert "families:" in yaml_str
    assert "railway:" in yaml_str
    assert "safety: read_only" in yaml_str
    assert "check_health" in yaml_str


def test_generate_families_yaml_empty():
    _clear_registry()
    pytest.importorskip("yaml")

    yaml_str = ToolRegistry.generate_families_yaml()
    assert "version: 1" in yaml_str
    assert "families: {}" in yaml_str


# ── denylist ────────────────────────────────────────────────────────────────

def test_denylist_not_empty():
    assert len(DESTRUCTIVE_DENYLIST) > 0


def test_denylist_patterns_are_valid_regex():
    for pattern in DESTRUCTIVE_DENYLIST:
        re.compile(pattern)


def test_denylist_catches_rm_rf():
    pattern = DESTRUCTIVE_DENYLIST[0]
    assert re.search(pattern, "rm -rf /tmp/foo")


def test_denylist_catches_fork_bomb():
    pattern = [p for p in DESTRUCTIVE_DENYLIST if "{" in p][0]
    assert re.search(pattern, ":(){ :|:& };:")


# ── denylist bypass hardening ───────────────────────────────────────────────

def test_denylist_catches_rm_fr():
    """rm -fr (flags reversed) must be caught."""
    assert any(re.search(p, "rm -fr /etc") for p in DESTRUCTIVE_DENYLIST), \
        "rm -fr bypassed the denylist"


def test_denylist_catches_rm_split_flags():
    """rm -r -f (flags split) must be caught."""
    assert any(re.search(p, "rm -r -f /etc") for p in DESTRUCTIVE_DENYLIST), \
        "rm -r -f bypassed the denylist"


def test_denylist_catches_rm_long_flags():
    """rm --recursive --force (long flags) must be caught."""
    assert any(re.search(p, "rm --recursive --force /etc") for p in DESTRUCTIVE_DENYLIST), \
        "rm --recursive --force bypassed the denylist"


def test_denylist_catches_git_clean_reordered():
    """git clean -xfd (flags reordered) must be caught."""
    assert any(re.search(p, "git clean -xfd") for p in DESTRUCTIVE_DENYLIST), \
        "git clean -xfd bypassed the denylist"


def test_denylist_catches_chmod_reordered():
    """chmod 777 -R / (flags reordered) must be caught."""
    assert any(re.search(p, "chmod 777 -R /") for p in DESTRUCTIVE_DENYLIST), \
        "chmod 777 -R / bypassed the denylist"


# ── ToolMeta dataclass ──────────────────────────────────────────────────────

def test_toolmeta_defaults():
    meta = ToolMeta(name="test.func", family="test")
    assert meta.safety == "read_only"
    assert meta.client == ""
    assert meta.auth == ""
    assert meta.description == ""
    assert meta.signature == ""
    assert meta.source_file == ""
    assert meta.registered_at


# ── discover_and_register ───────────────────────────────────────────────────

def test_discover_empty_list():
    _clear_registry()
    count = ToolRegistry.discover_and_register([])
    assert count == 0


def test_discover_nonexistent_package():
    _clear_registry()
    count = ToolRegistry.discover_and_register(["nonexistent.package.foo"])
    assert count == 0
