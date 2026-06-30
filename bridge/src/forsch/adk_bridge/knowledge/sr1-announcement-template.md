# "Now showing on SR-1" announcement template

When a friend's own pick goes up on SR-1, announce it — that's their "i belong here" badge. Text
only (no images). **Spoiler-safe**: mood and vibe, never plot, never a twist, never an ending. For TV
use `S##E##`, never the episode title. Year/runtime only if you actually know them — omit cleanly if
not (never guess, never write "unknown").

Use `announce_sr1_pick(title, friend_name, year, runtime)` to render this filled — don't hand-type
the copy. Then post it in your own warm voice.

## Template

> 🎬 now showing on SR-1: **{title}**{year_paren}{runtime_suffix}
> {friend_name}'s pick — pull up a seat, everyone.

Where:
- `{year_paren}` → ` ({year})` if a year is known, else empty.
- `{runtime_suffix}` → ` · {runtime}` if a runtime is known, else empty.

## Examples
- both known: `🎬 now showing on SR-1: **The Thing** (1982) · 1h 49m`
- title only: `🎬 now showing on SR-1: **The Thing**`

## Rules
- Never include plot, characters, deaths, twists, or the ending — not even a hint.
- Mood/vibe phrasing is fine ("a cozy one", "buckle up"); specifics about what happens are not.
- Only `{title}` is required; everything else is optional and omitted gracefully when missing.
