"""shelby_agent — Shelby's personal assistant (groceries + reminders + receipts).

---
keywords: [groceries, reminders, household, personal, receipts, whitelist, shopping, apple-reminders]
intention: "Saves you from rebuilding a personal-assistant that tracks groceries and reminders honestly. Pre-built with receipt-gated reminders and email-receipt whitelist."
function: "Shelby agent: groceries + reminders + grocery-email whitelist via OAuth + iPhone Reminders sync."
depends_on: [jsonl_store, whitelist, receipt_tool, oauth_client]
used_by: []
example: "/apps/shelby/users/<u>/sessions  then /run with newMessage"
---
"""
from __future__ import annotations

import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from forsch.adk_components.tools import (
    add_grocery_email_sender,
    add_reminder,
    get_grocery_log,
    is_grocery_email_sender_allowed,
    list_grocery_email_senders,
    log_grocery_email_receipt,
    log_groceries,
    remove_grocery_email_sender,
)

_LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
_LITELLM_API_KEY = (
    os.environ.get("ADK_LITELLM_KEY_SHELBY")
    or os.environ.get("LITELLM_HERMES_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or os.environ.get("LITELLM_API_KEY")
)
_LITELLM_MODEL = "openai/gpt-5.5"

shelby_model = LiteLlm(
    model=_LITELLM_MODEL, api_base=_LITELLM_BASE_URL, api_key=_LITELLM_API_KEY,
)

root_agent = Agent(
    name="shelby_agent",
    model=shelby_model,
    description="Shelby's personal grocery, reminders, and trusted receipt assistant.",
    instruction="You are Shelby's personal assistant. Warm, concise, practical.\n\nv1 focus: groceries, grocery receipt email, and reminders.\n- Track groceries; log items Shelby shares or pastes.\n- Grocery email is whitelist-only. Add trusted senders when asked. Never log from untrusted senders.\n- Spot trends from the log; never invent numbers.\n- Reminders: read back receipt (title, list, due). Tell her it's saved locally, not yet synced to iPhone.\n\nBe lazy and precise.",
    tools=[
        log_groceries, get_grocery_log, add_reminder,
        add_grocery_email_sender, remove_grocery_email_sender,
        list_grocery_email_senders, is_grocery_email_sender_allowed,
        log_grocery_email_receipt,
    ],
)

agent = root_agent
