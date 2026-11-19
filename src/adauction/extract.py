"""Extract step: stream the raw Criteo TSV in chunks and check its shape.

The full file is 16.5M rows (2.4 GB uncompressed), so it is never loaded into
memory at once. Each chunk is validated and handed to the loader.
"""

from __future__ import annotations

import gzip
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

CAT_COLUMNS = [f"cat{i}" for i in range(1, 10)]

# Column order as documented by Criteo AI Lab.
RAW_COLUMNS = [
    "timestamp",
    "uid",
    "campaign",
    "conversion",
    "conversion_timestamp",
    "conversion_id",
    "attribution",
    "click",
    "click_pos",
    "click_nb",
    "cost",
    "cpo",
    "time_since_last_click",
    *CAT_COLUMNS,
]

FLOAT_COLUMNS = ["cost", "cpo"]
INT_COLUMNS = [c for c in RAW_COLUMNS if c not in FLOAT_COLUMNS]


class SchemaError(ValueError):
    """Raised when the source file does not match the expected layout."""


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def read_header(path: str | Path) -> list[str]:
    with _open_text(Path(path)) as f:
        return f.readline().rstrip("\n").split("\t")


def validate_header(columns: list[str]) -> None:
    missing = [c for c in RAW_COLUMNS if c not in columns]
    extra = [c for c in columns if c not in RAW_COLUMNS]
    if missing or extra:
        raise SchemaError(f"unexpected columns: missing={missing} extra={extra}")


def validate_chunk(chunk: pd.DataFrame) -> None:
    """Fail fast on problems that would make the load meaningless."""
    key_nulls = chunk[["timestamp", "uid", "campaign"]].isna().sum()
    if key_nulls.any():
        raise SchemaError(f"null keys in source chunk: {key_nulls[key_nulls > 0].to_dict()}")


def iter_chunks(path: str | Path, chunksize: int = 500_000) -> Iterator[pd.DataFrame]:
    """Yield typed DataFrame chunks of the raw file, in file order."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    validate_header(read_header(path))
    dtypes = {c: "int64" for c in INT_COLUMNS} | {c: "float64" for c in FLOAT_COLUMNS}
    reader = pd.read_csv(path, sep="\t", dtype=dtypes, chunksize=chunksize)
    for chunk in reader:
        validate_chunk(chunk)
        yield chunk[RAW_COLUMNS]
