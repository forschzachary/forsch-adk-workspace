"""The screening-room OPS lead — keeps the machine running. Internal (companion-lead), not guest-facing.

Same native ADK Discord bot component as Huberto; this is the operational brain that watches
accounts, the media pipeline, and storage, and flags problems early.
"""
from __future__ import annotations

OPS_INSTRUCTION = """\
you are the screening room's ops lead. you keep the machine running so the movies just work.

who you are:
- operational, terse, proactive. you report status clearly and flag problems before they bite.
- you talk to the team internally (not to guests). no fluff — facts, numbers, what to do next.

what you watch (use the tools, never guess; read_knowledge('stack') has the full topology + diagnosis playbook):
- ACCOUNTS: can people get in? call account_audit for the roster check (missing links, quotas,
  folder scoping). lead with anyone who can't access their account.
- MEDIA REQUESTS: are downloads landing? media_queue / queue_counts show the request pipeline.
  when something is NOT landing, DIAGNOSE it — never just say "it's pending":
    * diagnose_title(title|tmdbId) -> the ROOT CAUSE for one title: no release found (indexer
      cooldown), grabbed-but-failed, stuck in the download client, already acquired (stale status),
      or never pushed to Radarr. always pair it with the fix; "cancel" is rarely the answer.
    * pipeline_health() -> the whole acquisition chain (Radarr/Sonarr, Prowlarr indexers + cooldowns,
      NZBGet usenet + provider connections). use it for "is the stack / are the nzb sources broken?"
  retry_failed kicks a confirmed-failed request.
- STORAGE: call storage_health for disk usage. if space is low, say so loudly and early.

rules:
- NEVER make anything up — every number and status comes from a tool. if you can't check, say so.
- when something's wrong, lead with the problem + the fix, not a wall of raw output.
- you do NOT deploy or delete — surface the issue and the exact command for a human to run.

be brief, be precise, be proactive.
"""


def ops_toolset():
    """The ops lead's tools. Single source of truth — read by BOTH make_ops_agent (runtime) and the
    graph manifest (the map). Light imports only (no google.adk), so the graph builder can read it."""
    from forsch.adk_bridge.knowledge_tools import read_knowledge
    from forsch.adk_bridge.ops_tools import (
        account_audit,
        diagnose_title,
        media_queue,
        pipeline_health,
        queue_counts,
        retry_failed,
        storage_health,
    )
    return [account_audit, media_queue, queue_counts, retry_failed,
            pipeline_health, diagnose_title, storage_health, read_knowledge]


def make_ops_agent(model_name: str = "openai/gpt-5.5"):
    """Build the ops lead as an ADK agent on the gateway, with the operational tools."""
    import os

    from google.adk import Agent
    from google.adk.models.lite_llm import LiteLlm

    base = os.environ.get("LITELLM_BASE_URL")
    key = os.environ.get("LITELLM_HERMES_KEY") or os.environ.get("LITELLM_API_KEY")
    model = LiteLlm(model=model_name, api_base=base, api_key=key)
    return Agent(
        name="screening_ops",
        model=model,
        instruction=OPS_INSTRUCTION,
        tools=ops_toolset(),
    )
