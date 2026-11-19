"""Shared fixtures: a tiny hand-built source file whose answers are known."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from adauction import pipeline
from adauction.extract import RAW_COLUMNS

DAY = 86_400
CATS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

# timestamp, uid, campaign, conversion, conversion_timestamp, conversion_id,
# attribution, click, click_pos, click_nb, cost, cpo, time_since_last_click
BASE_ROWS = [
    # user 1 sees campaign 10 three times, clicks twice, converts (attributed)
    (100, 1, 10, 1, DAY + 3_700, 500, 1, 1, 0, 2, 0.50, 20.0, -1),
    (200, 2, 10, 0, -1, -1, 0, 0, -1, -1, 0.20, 20.0, -1),
    (300, 2, 20, 1, 50_000, 501, 0, 0, -1, -1, 0.40, 8.0, -1),
    (18_000, 1, 10, 1, DAY + 3_700, 500, 1, 1, 1, 2, 1.00, 20.0, 17_900),
    (DAY + 100, 1, 10, 1, DAY + 3_700, 500, 1, 0, -1, -1, 0.25, 20.0, 68_500),
    # user 3: a click without a conversion, then a plain impression
    (2 * DAY + 10, 3, 20, 0, -1, -1, 0, 1, -1, -1, 0.30, 8.0, -1),
    (2 * DAY + 20, 3, 20, 0, -1, -1, 0, 0, -1, -1, 0.10, 8.0, 10),
]


def write_source(path: Path, rows: list[tuple]) -> Path:
    lines = ["\t".join(RAW_COLUMNS)]
    for row in rows:
        lines.append("\t".join(str(v) for v in (*row, *CATS)))
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    return write_source(tmp_path / "source.tsv.gz", BASE_ROWS)


@pytest.fixture
def warehouse(tmp_path: Path, source_file: Path) -> Path:
    db_path = tmp_path / "warehouse.db"
    pipeline.run(source_file, db_path, chunksize=3)
    return db_path
