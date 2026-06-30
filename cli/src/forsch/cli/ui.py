"""Shared rich UI for the forsch CLI — a clean terminal feel (markdown, spinners, tables).

Kept tiny and dependency-light: one shared Console + a few render helpers. The amber
accent matches the Forsch cockpit theme.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager

from rich.console import Console
from rich.table import Table
from rich.text import Text

ACCENT = "#f5a623"  # Forsch amber
COSMIC = "#9d8be0"  # twinkle violet (the spacey chat theme)
# true-black background so the starfield reads "spacey" on any terminal theme
console = Console(style="on #000000")


def banner() -> None:
    console.print()
    console.print("   [#6b5fc7]✦[/]    [#3a4a63]·[/]      [#3a6f8a]⋆[/]         [#9d8be0]✧[/]       [#3a4a63]·[/]       [#5dd6ff]✦[/]     [#3a4a63]⋆[/]")
    console.print("     [#3a4a63]·[/]      [bold #b8a0ff]Forsch Factory[/] [bold #5dd6ff]operator[/]       [#6b5fc7]✦[/]      [#3a4a63]·[/]")
    console.print("   [#9d8be0]✧[/]    [dim]build · wire · ask about ADK[/]   [dim italic]· exit to quit[/]    [#3a6f8a]⋆[/]   [#f5a623]✦[/]")
    console.print("     [#3a4a63]·[/]       [#5dd6ff]⋆[/]        [#6b5fc7]✦[/]        [#3a4a63]·[/]       [#9d8be0]✧[/]      [#3a4a63]·[/]")
    console.print()


def fmt_args(args: dict | None) -> str:
    if not args:
        return ""
    s = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return s if len(s) <= 80 else s[:77] + "…"


def tool_call_line(name: str, args: dict | None) -> Text:
    return (
        Text("  ✦ ", style=COSMIC)
        + Text(name, style="bold #b8a0ff")
        + Text(f"({fmt_args(args)})", style="dim")
    )


def tool_table(catalog: list[dict], family_filter: str | None = None) -> Table:
    t = Table(show_header=True, header_style=f"bold {ACCENT}", border_style="grey37", box=None, pad_edge=False)
    t.add_column("tool", style="cyan", no_wrap=True)
    t.add_column("family", style="dim")
    t.add_column("kind", no_wrap=True)
    t.add_column("description", style="white")
    for tool in catalog:
        if family_filter and family_filter.lower() not in tool["family"].lower():
            continue
        kind = Text(tool["kind"], style="green" if tool["kind"] == "read" else ACCENT)
        t.add_row(tool["name"], tool["family"], kind, tool["desc"])
    return t


def check(label: str, ok: bool, detail: str = "") -> Text:
    mark = Text("✓", style="green") if ok else Text("✗", style="red dim")
    return (
        Text("  ")
        + mark
        + Text(f"  {label:<30}", style="" if ok else "dim")
        + Text(detail, style="dim")
    )


@contextmanager
def black_terminal():
    """Paint the WHOLE terminal window true-black for the duration, then restore.

    Uses OSC 11 to set the terminal's default background (so margins and empty rows go black
    too, not just the text), and OSC 111 to reset on exit. No-op on terminals that ignore
    OSC 11; the Console's `on #000000` style still blacks out the rendered area there.
    """
    def _emit(seq: str) -> None:
        try:
            sys.stdout.write(seq)
            sys.stdout.flush()
        except Exception:
            pass

    _emit("\033]11;#000000\a")
    try:
        yield
    finally:
        _emit("\033]111\a")
