"""Tests for the builder metadata parser (Phase 1 TDD, step 1).

The parser turns two metadata sources into one ``ParsedMetadata`` model:
  * Python module-docstring YAML frontmatter (tool wrappers, clients).
  * Agent-spec human fields from ``agent_specs/agents.yaml``.

It must warn-not-crash on malformed input and tolerate files with no metadata.
"""

from forsch.adk_builder.metadata import (
    parse_python_metadata,
    parse_yaml_agent_metadata,
)


# --- Python docstring frontmatter -------------------------------------------

PY_WITH_FRONTMATTER = '''\
"""
---
display_name: Workspace Inventory
description: Scans the ADK workspace and returns a structured inventory.
doc_link: docs/STABILITY_GOVERNOR_RUNBOOK.md
owner: stability
risk: read_only
kind: tool_wrapper
---
"""


def get_workspace_inventory():
    return {}
'''

PY_PLAIN_DOCSTRING = '''\
"""Just a normal module docstring with no frontmatter."""


def f():
    return 1
'''

PY_NO_DOCSTRING = "def f():\n    return 1\n"

PY_MALFORMED_FRONTMATTER = '''\
"""
---
display_name: Broken
description: "unterminated
    : : not: valid: yaml
---
"""
'''


def test_valid_python_docstring_frontmatter_parses_into_metadata():
    result = parse_python_metadata(PY_WITH_FRONTMATTER, path="components/inventory.py")

    assert result.present is True
    assert result.warnings == []
    assert result.path == "components/inventory.py"
    md = result.metadata
    assert md.display_name == "Workspace Inventory"
    assert md.description.startswith("Scans the ADK workspace")
    assert md.doc_link == "docs/STABILITY_GOVERNOR_RUNBOOK.md"
    assert md.owner == "stability"
    assert md.risk == "read_only"
    assert md.kind == "tool_wrapper"


def test_python_plain_docstring_returns_empty_metadata_no_crash():
    result = parse_python_metadata(PY_PLAIN_DOCSTRING, path="x.py")

    assert result.present is False
    assert result.metadata.display_name is None
    assert result.warnings == []  # absence of metadata is not a warning


def test_python_without_any_docstring_returns_empty_no_crash():
    result = parse_python_metadata(PY_NO_DOCSTRING, path="x.py")

    assert result.present is False
    assert result.metadata.display_name is None
    assert result.warnings == []


def test_malformed_python_frontmatter_warns_does_not_raise():
    result = parse_python_metadata(PY_MALFORMED_FRONTMATTER, path="bad.py")

    assert result.warnings, "malformed frontmatter must produce a warning"
    assert any("bad.py" in w for w in result.warnings)
    # tolerant: still returns a model, never raises
    assert result.metadata.display_name is None


# --- YAML agent-spec human fields -------------------------------------------


def test_yaml_agent_spec_display_fields_parse_into_metadata():
    spec = {
        "display_name": "Stability Governor",
        "description": "Audits the ADK workspace and reports evidence-backed findings.",
        "doc_link": "docs/STABILITY_GOVERNOR_AGENT_DESIGN.md",
        "safety_level": "read_only",
    }
    result = parse_yaml_agent_metadata(spec, agent_id="stability", path="agent_specs/agents.yaml")

    assert result.warnings == []
    md = result.metadata
    assert md.display_name == "Stability Governor"
    assert md.description.startswith("Audits")
    assert md.doc_link == "docs/STABILITY_GOVERNOR_AGENT_DESIGN.md"
    assert md.risk == "read_only"  # safety_level maps onto risk


def test_yaml_agent_spec_real_shape_purpose_maps_to_description():
    # The real agent_specs/agents.yaml uses `purpose` + `safety_level`, no display_name.
    spec = {
        "package": "forsch.agent_stability.agent",
        "attr": "root_agent",
        "safety_level": "read_only",
        "purpose": "Audit the workspace without changing source.",
    }
    result = parse_yaml_agent_metadata(spec, agent_id="stability", path="agent_specs/agents.yaml")

    md = result.metadata
    assert md.description.startswith("Audit the workspace")  # purpose -> description fallback
    assert md.risk == "read_only"
    # display_name absent -> a warning, but description was recovered from purpose
    assert any("display_name" in w for w in result.warnings)


def test_yaml_agent_spec_without_human_fields_warns_not_raises():
    spec = {"package": "forsch.agent_ops.agent", "attr": "agent"}
    result = parse_yaml_agent_metadata(spec, agent_id="ops", path="agent_specs/agents.yaml")

    assert result.warnings, "missing human metadata must warn"
    assert any("ops" in w for w in result.warnings)
    assert result.metadata.display_name is None  # never raises
