# ADK Builder directory note

Purpose: sidecar builder cockpit for the Forsch ADK workspace. Phase 1 is read-only: collect metadata, explain agent/component wiring, and render a human-friendly dashboard. Phase 2 may add guarded edit actions after tests and safety gates exist.

Structure:

- `pyproject.toml` - local package and test dependencies.
- `src/forsch/adk_builder/` - builder package code.
- `templates/` - dashboard templates.
- `tests/` - TDD tests for metadata parsing, collection, rendering, and later guarded actions.

Current organization rule: this package must inspect canonical ADK workspace files without importing or mutating runtime agents during Phase 1. Writes belong only in Phase 2 guarded actions.
