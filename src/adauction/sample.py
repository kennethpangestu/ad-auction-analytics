"""Create a small, real sample of the dataset for tests and CI.

Sampling is by user rather than by row, so every sampled user keeps their
full history and conversion journeys stay intact.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pandas as pd

from .extract import RAW_COLUMNS, iter_chunks

_HASH_MOD = 10_000


def in_sample(uids: pd.Series, rate: float) -> pd.Series:
    """Deterministic user-level sampling: a user is either fully in or fully out."""
    buckets = pd.util.hash_pandas_object(uids, index=False).to_numpy() % _HASH_MOD
    return pd.Series(buckets < int(rate * _HASH_MOD), index=uids.index)


def write_user_sample(source: str | Path, out: str | Path, rate: float = 0.01) -> int:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    # mtime=0 keeps the gzip bytes identical across runs, so git sees no change.
    with open(out, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(("\t".join(RAW_COLUMNS) + "\n").encode())
        for chunk in iter_chunks(source):
            keep = chunk[in_sample(chunk["uid"], rate)]
            gz.write(keep.to_csv(sep="\t", header=False, index=False).encode())
            written += len(keep)
    return written
