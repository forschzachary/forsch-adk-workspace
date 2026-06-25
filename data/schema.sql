-- TrinityCore TBC database schema — the subset we need for the guild bot.
-- Run this against an empty SQLite database to create the tables,
-- then import TrinityCore TBC dump data into them.

-- Items: every equippable item, weapon, consumable, trade good
CREATE TABLE IF NOT EXISTS items (
    item_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    slot        TEXT,           -- head, neck, shoulder, chest, waist, legs, feet, wrist, hands,
                                -- finger, trinket, back, main hand, off hand, ranged, tabard, shirt
    class       TEXT,           -- warrior, paladin, hunter, rogue, priest, shaman, mage, warlock, druid
    subclass    TEXT,           -- cloth, leather, mail, plate, etc.
    quality     TEXT,           -- poor, common, uncommon, rare, epic, legendary
    required_level INTEGER,
    item_level  INTEGER,
    stats       TEXT,           -- JSON blob: {"stamina": 30, "intellect": 25, "spell_crit": 14, ...}
    armor       INTEGER,
    dps         REAL,
    speed       REAL,
    phase       INTEGER         -- 1-5 for TBC content phases
);

-- Creatures: every NPC, mob, boss
CREATE TABLE IF NOT EXISTS creatures (
    creature_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    min_level   INTEGER,
    max_level   INTEGER,
    type        TEXT,           -- beast, humanoid, demon, undead, elemental, dragonkin, boss, vendor, trainer, quest giver
    faction     TEXT,           -- alliance, horde, neutral
    zone        TEXT,           -- Hellfire Peninsula, Zangarmarsh, Nagrand, etc.
    map         INTEGER         -- instance/dungeon map ID
);

-- Loot: what creatures drop
CREATE TABLE IF NOT EXISTS loot (
    creature_id INTEGER NOT NULL,
    item_id     INTEGER NOT NULL,
    chance      REAL,           -- drop chance as percentage (e.g. 12.5)
    min_count   INTEGER DEFAULT 1,
    max_count   INTEGER DEFAULT 1,
    PRIMARY KEY (creature_id, item_id),
    FOREIGN KEY (creature_id) REFERENCES creatures(creature_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);

-- Quests
CREATE TABLE IF NOT EXISTS quests (
    quest_id    INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    level       INTEGER,
    min_level   INTEGER,
    zone        TEXT,
    objectives  TEXT,           -- JSON blob: [{"type": "kill", "target": "Fel Orc", "count": 10}, ...]
    rewards     TEXT,           -- JSON blob: [{"item_id": 12345, "name": "Seer's Ring"}, ...]
    chain_id    INTEGER,        -- quest chain identifier (for attunement chains, etc.)
    chain_step  INTEGER,        -- position in chain (1, 2, 3, ...)
    next_quest  INTEGER         -- quest_id of the next quest in the chain
);

-- Dungeons: instance metadata
CREATE TABLE IF NOT EXISTS dungeons (
    dungeon_id  INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,  -- Karazhan, The Shattered Halls, etc.
    map_id      INTEGER,        -- TrinityCore map ID
    min_level   INTEGER,
    max_level   INTEGER,
    players     INTEGER,        -- 5, 10, 25, 40
    heroic      INTEGER DEFAULT 0  -- 0 = normal, 1 = heroic available
);

-- Dungeon creatures: which creatures appear in which dungeon
CREATE TABLE IF NOT EXISTS dungeon_creatures (
    dungeon_id  INTEGER NOT NULL,
    creature_id INTEGER NOT NULL,
    PRIMARY KEY (dungeon_id, creature_id),
    FOREIGN KEY (dungeon_id) REFERENCES dungeons(dungeon_id),
    FOREIGN KEY (creature_id) REFERENCES creatures(creature_id)
);

-- Player registry: persisted across restarts (Phase 2)
CREATE TABLE IF NOT EXISTS players (
    discord_id  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    level       INTEGER NOT NULL,
    class       TEXT NOT NULL,
    spec        TEXT DEFAULT '',
    registered_at TEXT DEFAULT (datetime('now'))
);

-- FTS5 indexes for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(name, content=items, content_rowid=item_id);
CREATE VIRTUAL TABLE IF NOT EXISTS creatures_fts USING fts5(name, content=creatures, content_rowid=creature_id);
CREATE VIRTUAL TABLE IF NOT EXISTS quests_fts USING fts5(title, content=quests, content_rowid=quest_id);
