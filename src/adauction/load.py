"""Load step: bulk insert raw chunks into the SQLite staging table.

The staging table keeps the source exactly as delivered (including the -1
sentinel values) so every downstream table can be traced back to it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

import pandas as pd

from .extract import RAW_COLUMNS

_INSERT_SQL = (
    f"INSERT INTO stg_impressions (source_row, {', '.join(RAW_COLUMNS)}) "
    f"VALUES ({', '.join(['?'] * (len(RAW_COLUMNS) + 1))})"
)


def load_staging(conn: sqlite3.Connection, chunks: Iterable[pd.DataFrame]) -> int:
    """Insert every chunk into stg_impressions. Returns the number of rows loaded."""
    loaded = 0
    for chunk in chunks:
        rows = chunk.itertuples(index=False, name=None)
        conn.executemany(
            _INSERT_SQL,
            ((loaded + i, *row) for i, row in enumerate(rows)),
        )
        loaded += len(chunk)
    conn.commit()
    return loaded
