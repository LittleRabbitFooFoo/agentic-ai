"""Creates the logging SQLite database (prompts, conversations) fresh.

Separate file from the STATS19 data DB. Re-runnable: uses CREATE TABLE IF
NOT EXISTS, safe to run against an existing logging.db without wiping it.
"""

import sqlite3

LOGGING_DB_PATH = "logging.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_label TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id),
    timestamp TEXT NOT NULL
);
"""


def init_logging_db(path: str = LOGGING_DB_PATH) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_logging_db()
    print(f"Logging DB ready at {LOGGING_DB_PATH}")
