# AppleRemindersSync

`AppleRemindersSync` is a new, minimal Swift package that provides phone-local
Apple Reminders domain models and service logic for Shelby. It is intentionally
backend-only so it can be wrapped later by a compact iOS app module.

## What it contains

- Domain models for reminders (`ShelbyReminderList`, `ShelbyReminderItem`, etc.)
- A small service protocol (`ShelbyReminderServiceProtocol`)
- Live `EventKit` implementation (`ShelbyEventKitReminderService`) for on-device
  Reminders read/write
- In-memory implementation (`ShelbyInMemoryReminderService`) for tests and previews
- Command adapter (`ShelbyReminderCommandHandler`) that turns structured commands
  into structured command results
- Unit tests (`swift test`) for core behavior

## What it does not contain

- No HermesMobile reuse
- No bridge to Zach’s Mac
- No server-side Reminder storage or sync layer
- No polished consumer UI, Gradio layer, Mac bridge, remindctl, or grocery bridge

## Build notes

- Platform target: `iOS`
- EventKit surface is guarded with `#if canImport(EventKit)` so CLI/test builds on
  non-Apple platforms can still run the in-memory command flow.
