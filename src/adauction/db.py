"""SQLite helpers: connections and running .sql files from the sql/ folder."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # Bulk-load settings. The warehouse is rebuilt from source on every run,
    # so durability during the load is not needed.
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -512000")  # about 500 MB
    return conn


def run_sql_file(conn: sqlite3.Connection, path: Path) -> None:
    conn.executescript(path.read_text(encoding="utf-8"))
    conn.commit()


def run_sql_folder(conn: sqlite3.Connection, folder: str) -> list[str]:
    """Run every .sql file in sql/<folder>/ in name order. Returns the files run."""
    files = sorted((SQL_DIR / folder).glob("*.sql"))
    for path in files:
        run_sql_file(conn, path)
    return [p.name for p in files]


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    return conn.execute(sql, params).fetchone()[0]
