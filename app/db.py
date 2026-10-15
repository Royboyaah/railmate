"""SQLite access layer: schema, connections and small helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

TIMETABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stations (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    state       TEXT,
    zone        TEXT,
    lat         REAL,
    lon         REAL,
    train_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trains (
    number         TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL,
    zone           TEXT,
    origin         TEXT NOT NULL,
    destination    TEXT NOT NULL,
    distance_km    REAL NOT NULL,
    duration_min   INTEGER NOT NULL,
    classes        TEXT NOT NULL,
    runs_on        INTEGER NOT NULL DEFAULT 127,
    runs_on_known  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stops (
    train_number TEXT NOT NULL REFERENCES trains(number) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    station_code TEXT NOT NULL REFERENCES stations(code),
    arr_min      INTEGER,
    dep_min      INTEGER,
    km           REAL NOT NULL,
    PRIMARY KEY (train_number, seq)
);
CREATE INDEX IF NOT EXISTS idx_stops_station ON stops(station_code);
"""

# User data lives in a SEPARATE database so rebuilding the timetable never touches accounts.
USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trips (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_code    TEXT NOT NULL,
    to_code      TEXT NOT NULL,
    travel_date  TEXT NOT NULL,
    travel_class TEXT NOT NULL,
    passengers   INTEGER NOT NULL,
    legs_json    TEXT NOT NULL,
    fare_total   INTEGER NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path, schema: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with session(db_path) as conn:
        conn.executescript(schema)


def get_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
