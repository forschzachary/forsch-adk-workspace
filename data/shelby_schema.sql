CREATE TABLE IF NOT EXISTS groceries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    store TEXT,
    date TEXT NOT NULL,
    category TEXT,
    note TEXT,
    logged_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    list_name TEXT DEFAULT 'Reminders',
    due TEXT,
    note TEXT,
    synced INTEGER DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    assignee TEXT,
    cadence_days INTEGER,
    last_done TEXT,
    due TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);
