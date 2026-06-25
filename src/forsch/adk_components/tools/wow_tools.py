"""ADK tool functions for WoW TBC guild knowledge — items, quests, dungeons, bosses, loot, NPCs, and player registry.

All tools are read-only against tbc_data.sqlite (TrinityCore TBC dump). The player registry
is an in-memory store for now; Phase 2 moves it to SQLite for persistence across restarts.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# ── database path ──────────────────────────────────────────────────────────
# Resolved at import time. Falls back to a sensible default if FORSCH_ADK_WORKSPACE is unset.
def _db_path() -> Path:
    ws = Path(__import__("os").environ.get("FORSCH_ADK_WORKSPACE", "/workspace"))
    return ws / "data" / "tbc_data.sqlite"


def _connect() -> sqlite3.Connection:
    """Open a read-only connection to the TBC database."""
    db = _db_path()
    if not db.exists():
        raise FileNotFoundError(f"TBC database not found at {db}. Run the data import first.")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── player registry (in-memory, Phase 1) ──────────────────────────────────

_player_registry: dict[str, dict[str, Any]] = {}


def register_player(discord_id: str, name: str, level: int, class_name: str, spec: str = "") -> dict[str, Any]:
    """Register a player's character for personalized answers.

    Args:
        discord_id: Discord user ID (e.g. '123456789')
        name: Character name
        level: Character level (1-70)
        class_name: Class (e.g. 'shaman', 'mage', 'warrior')
        spec: Talent specialization (e.g. 'resto', 'frost', 'protection')
    """
    _player_registry[discord_id] = {
        "name": name,
        "level": level,
        "class": class_name.lower(),
        "spec": spec.lower() if spec else "",
    }
    return {"status": "registered", "player": _player_registry[discord_id]}


def get_player(discord_id: str) -> dict[str, Any] | None:
    """Look up a registered player by Discord ID."""
    return _player_registry.get(discord_id)


# ── item tools ─────────────────────────────────────────────────────────────

def search_items(
    query: str = "",
    slot: str = "",
    class_restriction: str = "",
    min_level: int = 0,
    max_level: int = 70,
    quality: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search for items by name, slot, class, level range, and quality.

    Args:
        query: Text search against item name (FTS5).
        slot: Equipment slot filter (e.g. 'head', 'chest', 'main hand').
        class_restriction: Class filter (e.g. 'shaman', 'mage').
        min_level: Minimum required level.
        max_level: Maximum required level.
        quality: Item quality (e.g. 'rare', 'epic').
        limit: Max results to return.
    """
    conn = _connect()
    clauses = []
    params: list[Any] = []

    if query:
        clauses.append("items.name MATCH ?")
        params.append(query)
    if slot:
        clauses.append("LOWER(items.slot) = ?")
        params.append(slot.lower())
    if class_restriction:
        clauses.append("LOWER(items.class) = ?")
        params.append(class_restriction.lower())
    if min_level:
        clauses.append("items.required_level >= ?")
        params.append(min_level)
    if max_level < 70:
        clauses.append("items.required_level <= ?")
        params.append(max_level)
    if quality:
        clauses.append("LOWER(items.quality) = ?")
        params.append(quality.lower())

    where = " AND ".join(clauses) if clauses else "1=1"
    sql = f"SELECT name, item_id, slot, required_level, quality FROM items WHERE {where} LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_item_details(item_id: int) -> dict[str, Any]:
    """Get full item stats plus all drop sources with drop chances.

    Args:
        item_id: The item's entry ID from TrinityCore.
    """
    conn = _connect()

    item = conn.execute(
        "SELECT * FROM items WHERE item_id = ?", (item_id,)
    ).fetchone()
    if not item:
        conn.close()
        return {"error": f"Item {item_id} not found"}

    drops = conn.execute(
        """SELECT c.name AS creature_name, c.creature_id, l.chance, l.min_count, l.max_count
           FROM loot l
           JOIN creatures c ON c.creature_id = l.creature_id
           WHERE l.item_id = ?
           ORDER BY l.chance DESC""",
        (item_id,),
    ).fetchall()

    conn.close()
    return {
        "item": dict(item),
        "drop_sources": [dict(d) for d in drops],
    }


# ── quest tools ────────────────────────────────────────────────────────────

def search_quests(
    query: str = "",
    zone: str = "",
    min_level: int = 0,
    max_level: int = 70,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search for quests by name, zone, and level range.

    Args:
        query: Text search against quest title (FTS5).
        zone: Zone name filter.
        min_level: Minimum quest level.
        max_level: Maximum quest level.
        limit: Max results to return.
    """
    conn = _connect()
    clauses = []
    params: list[Any] = []

    if query:
        clauses.append("quests.title MATCH ?")
        params.append(query)
    if zone:
        clauses.append("LOWER(quests.zone) = ?")
        params.append(zone.lower())
    if min_level:
        clauses.append("quests.level >= ?")
        params.append(min_level)
    if max_level < 70:
        clauses.append("quests.level <= ?")
        params.append(max_level)

    where = " AND ".join(clauses) if clauses else "1=1"
    sql = f"SELECT quest_id, title, level, zone, min_level FROM quests WHERE {where} LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── dungeon / boss tools ───────────────────────────────────────────────────

def get_dungeon_bosses(dungeon_name: str) -> list[dict[str, Any]]:
    """List all bosses in a dungeon with their levels.

    Args:
        dungeon_name: Dungeon name (e.g. 'Karazhan', 'The Shattered Halls').
    """
    conn = _connect()
    rows = conn.execute(
        """SELECT c.name, c.creature_id, c.min_level, c.max_level, c.type
           FROM creatures c
           JOIN dungeon_creatures dc ON dc.creature_id = c.creature_id
           JOIN dungeons d ON d.dungeon_id = dc.dungeon_id
           WHERE LOWER(d.name) = LOWER(?)
           AND c.type = 'boss'
           ORDER BY c.name""",
        (dungeon_name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_boss_loot(boss_name: str) -> list[dict[str, Any]]:
    """Get the full loot table for a boss with drop chances.

    Args:
        boss_name: Boss name (e.g. 'Grand Warlock Nethekurse').
    """
    conn = _connect()
    rows = conn.execute(
        """SELECT i.name AS item_name, i.item_id, i.slot, i.quality,
                  l.chance, l.min_count, l.max_count
           FROM loot l
           JOIN items i ON i.item_id = l.item_id
           JOIN creatures c ON c.creature_id = l.creature_id
           WHERE LOWER(c.name) = LOWER(?)
           ORDER BY l.chance DESC""",
        (boss_name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── NPC tools ──────────────────────────────────────────────────────────────

def search_npcs(
    query: str = "",
    zone: str = "",
    npc_type: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search for NPCs by name, zone, and type.

    Args:
        query: Text search against NPC name (FTS5).
        zone: Zone name filter.
        npc_type: NPC type (e.g. 'vendor', 'trainer', 'quest giver').
        limit: Max results to return.
    """
    conn = _connect()
    clauses = []
    params: list[Any] = []

    if query:
        clauses.append("creatures.name MATCH ?")
        params.append(query)
    if zone:
        clauses.append("LOWER(creatures.zone) = ?")
        params.append(zone.lower())
    if npc_type:
        clauses.append("LOWER(creatures.type) = ?")
        params.append(npc_type.lower())

    where = " AND ".join(clauses) if clauses else "1=1"
    sql = f"SELECT name, creature_id, min_level, max_level, type, zone FROM creatures WHERE {where} LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
