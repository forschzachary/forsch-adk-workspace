# Git Discipline

This workspace is intentionally split across several GitHub repositories. Do not leave important work local-only.

## Canonical repositories

| Local path | GitHub repo | Ownership |
| --- | --- | --- |
| `/opt/data/workspace/adk` | `forschzachary/forsch-adk-workspace` | Workspace docs, manifests, ADK Web wrappers, cross-agent runbooks |
| `/opt/data/workspace/adk/components` | `forschzachary/forsch-adk-components` | Shared Python package for reusable ADK tools, clients, models, and tests |
| `/opt/data/workspace/adk/agents/stability` | `forschzachary/forsch-agent-stability` | Read-only Stability Governor ADK agent package |
| `/opt/data/workspace/adk/bridge` | `forschzachary/forsch-adk-bridge` | Discord-to-ADK bridge runtime package and route config |

The other agent repos under `agents/` are separate package repos. Do not fold their changes into the workspace repo.

## Before editing

Run these from the repo you plan to touch:

```bash
git status -sb
git remote -v
git branch --show-current
git log --oneline -3
```

If you are in `/opt/data/workspace/adk`, remember it is the orchestration repo. Nested repos are intentionally ignored there.

## Where changes belong

- Shared reusable tool/client/model code: `components/`.
- Agent instructions, agent-specific tools, tests, evals: `agents/<name>/`.
- Discord ingress/routing/session code: `bridge/`.
- Cross-agent docs, manifests, ADK Web wrappers: workspace root, `agent_specs/`, `docs/`, `web_agents/`.
- Runtime state, session DBs, caches, venvs: nowhere in Git.

## Do not track

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.venv/
.env
.DS_Store
*.db
*.sqlite
*.sqlite3
**/.adk/
```

Before committing, verify:

```bash
git ls-files | grep -E '(__pycache__|\.pytest_cache|\.venv|\.adk|\.db$|\.sqlite|\.sqlite3)' || echo clean
```

## Commit and push standard

1. Stage only files owned by the current repo.
2. Run the smallest relevant tests.
3. Confirm no generated/session files are tracked.
4. Commit with a clear conventional message.
5. Push to GitHub. If work is not pushed, it is not durable.

On Cloud Hubert, use Authsome for GitHub operations when plain `gh` or `git push` lacks credentials:

```bash
AUTHSOME_BASE_URL=http://127.0.0.1:7998 authsome run -- gh repo view forschzachary/<repo>
AUTHSOME_BASE_URL=http://127.0.0.1:7998 authsome run -- git push
```

## Current known state

- `forsch-adk-components` has an open PR for Stability Governor inspection tools: https://github.com/forschzachary/forsch-adk-components/pull/1
- `forsch-agent-stability`, `forsch-adk-bridge`, and `forsch-adk-workspace` have initial `main` commits pushed.
- `adk-bridge` runs as a durable Docker service using `/opt/data/workspace/adk/bridge`.

## Handoff rule

If a future agent creates a new package, wrapper, config, or doc set, it must either:

- commit and push it to the owning GitHub repo, or
- write an explicit note in `docs/OPEN-QUESTIONS.md` explaining why it is intentionally local-only.

Default assumption: local-only is unsafe.
