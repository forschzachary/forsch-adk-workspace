#!/usr/bin/env python3
"""Seed per-agent LiteLLM keys for the ADK bridge (idempotent).

Each ADK lead authenticates to LiteLLM with its OWN virtual key, so usage /
spend / latency / fallback-rate is attributed per agent (LiteLLM "Keys" view,
alias ``adk-<id>``). The key VALUES live in ``bridge.env`` (gitignored secrets)
as ``ADK_LITELLM_KEY_<ID>``; the generated agent packages read them with a
fallback to the shared ``LITELLM_HERMES_KEY`` chain — so a missing key never
breaks an agent.

Run on deploy AFTER litellm is healthy and BEFORE the bridge is (re)created, so
the ``docker compose up -d`` picks up the new env. A fresh box has an empty
litellm DB + a bridge.env without these vars → this creates 6 keys and appends
them. Anything already in bridge.env is left untouched (safe every deploy).

Env: LITELLM_MASTER_KEY (else it docker-execs the litellm container);
optional BRIDGE_ENV path, LITELLM_BASE.

NOTE: bridge.env is shared with the chat surface — this only APPENDS its own
ADK_LITELLM_KEY_* lines; it never rewrites other keys.
"""
import json
import os
import pathlib
import subprocess
import urllib.request

AGENTS = ["stability", "ops", "build", "assistant", "brand", "social"]
BASE = os.environ.get("LITELLM_BASE", "http://127.0.0.1:4000")
ENVP = pathlib.Path(os.environ.get("BRIDGE_ENV", "/root/.hermes/workspace/adk/bridge/bridge.env"))


def _master_key() -> str:
    k = os.environ.get("LITELLM_MASTER_KEY")
    if k:
        return k
    return subprocess.check_output(
        ["docker", "exec", "litellm", "sh", "-lc", "echo $LITELLM_MASTER_KEY"]
    ).decode().strip()


def _generate(mk: str, alias: str, agent_id: str) -> str:
    body = {
        "key_alias": alias,
        "models": ["all-proxy-models"],
        "metadata": {"tags": ["agent:" + agent_id], "app": "adk-bridge"},
    }
    req = urllib.request.Request(
        BASE + "/key/generate", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + mk, "Content-Type": "application/json"}, method="POST",
    )
    return json.load(urllib.request.urlopen(req, timeout=30))["key"]


def main() -> None:
    mk = _master_key()
    lines = ENVP.read_text().splitlines() if ENVP.exists() else []
    have = {l.split("=", 1)[0] for l in lines if "=" in l}
    added = 0
    for a in AGENTS:
        var = "ADK_LITELLM_KEY_" + a.upper()
        if var in have:
            print(f"  {a}: {var} present — skip")
            continue
        key = _generate(mk, "adk-" + a, a)
        lines.append(f"{var}={key}")
        added += 1
        print(f"  {a}: created adk-{a} (key -> {var} in bridge.env)")
    if added:
        ENVP.write_text("\n".join(lines) + "\n")
    print(f"seed-keys: +{added} key(s) created, {len(AGENTS) - added} already present")


if __name__ == "__main__":
    main()
