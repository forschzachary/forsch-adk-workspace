---
goal: "Personal assistant for Shelby — track groceries over time, spot trends, manage reminders with honest read-back receipts, and ingest grocery-receipt emails from a sender whitelist."
status: building
handoff_pct: 20
data_connectors: []
---
# Shelby

Personal agent cluster for Shelby. v1 focus: groceries, grocery receipt email, and reminders.

## Agents
- **shelby** — personal grocery + reminders assistant (gpt-5.5, local_write)

## Tools
- `log_groceries` — append grocery items to running log
- `get_grocery_log` — read back grocery history for trend reasoning
- `add_reminder` — record reminder locally with honest receipt (not yet synced to iPhone)
- `add_grocery_email_sender` — add a trusted sender to the grocery-receipt whitelist
- `remove_grocery_email_sender` — drop a sender from the whitelist
- `list_grocery_email_senders` — show the current whitelist
- `is_grocery_email_sender_allowed` — check whether a sender is trusted
- `log_grocery_email_receipt` — log groceries extracted from a whitelisted receipt email

## Companion iOS module
- `ShelbyRemindersCore` (Swift, EventKit) — synced to box at `_ios-shelby-reminders/ShelbyRemindersCore/`. iPhone-side sync layer for reminders (in-memory + EventKit implementations + command handler + tests).
