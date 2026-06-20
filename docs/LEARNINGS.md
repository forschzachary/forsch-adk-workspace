# Learnings

Durable observations from the ADK workspace cleanup. Keep this file factual and reusable; do not record ephemeral task progress.

## Source ownership

- Local-only ADK work is unsafe by default. Important packages, docs, bridge configs, and wrappers need a GitHub home.
- Split by ownership, not by convenience: shared code in `components`, agent packages in `agents/<name>`, Discord ingress in `bridge`, cross-agent docs/manifests/wrappers in the workspace repo.
- A workspace repo with nested package repos needs aggressive `.gitignore` rules so it does not accidentally absorb package source or runtime state.

## Verification

- A clean `git status -sb` in the workspace root does not prove nested repos are clean. Check each owning repo explicitly.
- GitHub visibility is the durability check. Use `gh repo view`, `gh api .../contents`, and `git status -sb` after pushing.
- `gh repo create --source . --push` can create the GitHub repo but fail the git push when raw Git credentials are missing. Recover with `authsome run -- git push -u origin main`.

## Runtime

- The durable `adk-bridge` container proves process survival, not agent-response health. Logs must also be checked for ADK model failures.
- Missing or misrouted model credentials can surface as GoogleLLM/Gemini API-key errors even when the intended route is LiteLLM.

## Testing

- Recreated venvs can accidentally target the active Hermes venv if `VIRTUAL_ENV` is set. When installing into a project venv with `uv`, pass `--python ./.venv/bin/python` and clear `VIRTUAL_ENV` if needed.
- Bridge tests need both bridge source and local agent/component source on `PYTHONPATH` unless the packages are installed into the bridge venv.

## Safety

- Generated/session files to guard against: `.venv`, `.pytest_cache`, `__pycache__`, `.adk`, SQLite DBs, and `.env`.
- Stability inspection tools that may be exposed to an LLM must constrain paths, URLs, and import targets. Read-only does not automatically mean safe.
