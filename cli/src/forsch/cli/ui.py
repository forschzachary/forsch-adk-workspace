"""Shared rich UI for the forsch CLI — a clean terminal feel (markdown, spinners, tables).

Kept tiny and dependency-light: one shared Console + a few render helpers. The amber
accent matches the Forsch cockpit theme.
"""
from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

ACCENT = "#f5a623"  # Forsch amber
console = Console()


def banner() -> None:
    console.print()
    console.print(Text("  Forsch Factory ", style=f"bold {ACCENT}") + Text("operator", style="bold"))
    console.print(
        Text("  build · wire · ask about ADK   ", style="dim")
        + Text("exit", style="dim italic")
        + Text(" to quit", style="dim")
    )
    console.print()


def fmt_args(args: dict | None) -> str:
    if not args:
        return ""
    s = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return s if len(s) <= 80 else s[:77] + "…"


def tool_call_line(name: str, args: dict | None) -> Text:
    return (
        Text("  ⏺ ", style=ACCENT)
        + Text(name, style="bold")
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
