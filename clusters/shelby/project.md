---
goal: "Personal assistant for Shelby — track groceries over time, spot trends, manage reminders with honest read-back receipts."
status: building
handoff_pct: 20
data_connectors: []
---
# Shelby

Personal agent cluster for Shelby. v1 focus: groceries and reminders.

## Agents
- **shelby** — personal grocery + reminders assistant (gpt-5.5, local_write)

## Tools
- `log_groceries` — append grocery items to running log
- `get_grocery_log` — read back grocery history for trend reasoning
- `add_reminder` — record reminder locally with honest receipt (not yet synced to iPhone)
