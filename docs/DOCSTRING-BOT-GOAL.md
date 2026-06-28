# Documentation Bot — Goal

A careful documentation bot that adds docstrings to Python functions and classes across our repos. Tiny, safe, reversible steps only.

## TARGETS (work ONLY inside these dirs, top to bottom; .py files only)

- `~/Dev/forsch_frontiers/forsch_frontiers`
- `~/Dev/frappe-crm-deploy/scripts`
- `~/Dev/cloud/cloud-deploy`
- `~/Dev/Hubert/hermes-overlay`
- `~/Dev/Hubert/assets`
- *(add more OUR-code dirs here as you confirm them)*

## NEVER open a file whose path contains ANY of these (upstream / generated / junk)

- `node_modules`
- `.venv`
- `venv`
- `__pycache__`
- `/apps/frappe/`
- `/apps/crm/`
- `/apps/gameplan/`
- `/agents/`
- `/web_agents/`
- `migrations`
- `patches`
- `/archive/`
- `.min.`
- `dist/`
- `build/`
- `secrets`
- `.env`
- `.key`
- `.sops`

## HARD RULES (never break)

1. **One function/class per run.** Exactly one commit per run. `.py` files only.
2. **ONLY add a docstring.** Never change code, logic, names, imports, blank lines, or any other file. The diff must be added docstring lines only.
3. **Never delete anything.** Never run: `push`, `reset`, `rebase`, `merge`, `clean`, checkout of a branch other than `gemma/docstrings`, or any command with `-f`/`--force`. Allowed git ONLY: `status`, `rev-parse`, `checkout -B gemma/docstrings`, `checkout -- <file>`, `add <file>`, `commit -m "..."`, `diff`.
4. **The docstring must be ACCURATE** — describe only what the code actually does (Google style: summary; then `Args:`/`Returns:`/`Raises:` if relevant). If you can't tell exactly what it does, SKIP and pick another.

## STEPS EACH RUN

1. Go down TARGETS in order; pick the first dir that contains a `.py` file with a function/class that has NO docstring (first body line is not `"""..."""`). Skip any path matching the NEVER list. If none anywhere, print `ALL DONE` and STOP.
2. `cd` to the git repo root for that file. Run: `git rev-parse --abbrev-ref HEAD`. If it is not `gemma/docstrings`, run: `git checkout -B gemma/docstrings`
3. Insert one accurate docstring under the signature line, matching body indentation. Change nothing else.
4. Run: `python -m py_compile <file>`. On error: `git checkout -- <file>`, print `SKIP <file>: compile failed`, STOP.
5. Run: `git diff --stat` — confirm exactly ONE file changed and ONLY lines added. If not, run: `git checkout -- .`, print `SKIP: unexpected diff`, STOP.
6. `git add <file> && git commit -m "docs: add docstring to <name> in <file>"`
7. Print `DONE <name> in <file> [<repo>]` and STOP.

**Do not push.** A human reviews and merges each repo's `gemma/docstrings` branch later.
