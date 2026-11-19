import gzip
import sqlite3

import pandas as pd
import pytest

from adauction import pipeline
from adauction.extract import RAW_COLUMNS, SchemaError, iter_chunks, validate_header

from .conftest import BASE_ROWS, DAY


def test_header_must_match_documented_columns():
    validate_header(RAW_COLUMNS)
    with pytest.raises(SchemaError):
        validate_header(RAW_COLUMNS[:-1])
    with pytest.raises(SchemaError):
        validate_header([*RAW_COLUMNS, "surprise"])


def test_chunks_preserve_every_row(source_file):
    chunks = list(iter_chunks(source_file, chunksize=3))
    assert [len(c) for c in chunks] == [3, 3, 1]
    assert sum(len(c) for c in chunks) == len(BASE_ROWS)


def test_sentinels_become_null(warehouse):
    conn = sqlite3.connect(warehouse)
    nulls = conn.execute(
        "SELECT COUNT(*) FROM fact_impression WHERE conversion = 0 AND conversion_id IS NULL"
    ).fetchone()[0]
    assert nulls == 4
    assert conn.execute(
        "SELECT COUNT(*) FROM fact_impression WHERE conversion_id = -1 OR conversion_ts = -1"
    ).fetchone()[0] == 0


def test_day_and_hour_are_derived(warehouse):
    conn = sqlite3.connect(warehouse)
    rows = conn.execute(
        "SELECT ts, day_key, hour_of_day FROM fact_impression ORDER BY impression_id"
    ).fetchall()
    for ts, day, hour in rows:
        assert day == ts // DAY
        assert hour == (ts % DAY) // 3600


def test_dimensions(warehouse):
    conn = sqlite3.connect(warehouse)
    assert conn.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM dim_campaign").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM dim_user").fetchone()[0] == 3
    user1 = conn.execute(
        "SELECT impressions, campaigns FROM dim_user WHERE user_id = 1"
    ).fetchone()
    assert user1 == (3, 1)


def test_last_click_credit(warehouse):
    conn = sqlite3.connect(warehouse)
    rows = conn.execute(
        "SELECT impression_id, is_last_click, credited FROM fact_impression"
        " WHERE is_last_click = 1 ORDER BY impression_id"
    ).fetchall()
    # row 2 is the last click of an unattributed conversion, row 3 of an attributed one
    assert rows == [(2, 1, 0), (3, 1, 1)]


def test_impression_number_counts_per_user_and_campaign(warehouse):
    conn = sqlite3.connect(warehouse)
    numbers = [r[0] for r in conn.execute(
        "SELECT impression_number FROM fact_impression ORDER BY impression_id")]
    assert numbers == [1, 1, 1, 2, 3, 1, 2]


def test_conversion_journeys(warehouse):
    conn = sqlite3.connect(warehouse)
    df = pd.read_sql("SELECT * FROM fact_conversion ORDER BY conversion_id", conn)
    assert df["conversion_id"].tolist() == [500, 501]
    journey = df.iloc[0]
    assert journey["clicks_in_data"] == 2
    assert journey["clicks_total"] == 2
    assert journey["attributed"] == 1
    assert journey["journey_cost"] == pytest.approx(1.5)
    assert journey["last_click_ts"] == 18_000
    assert journey["hours_to_convert"] == pytest.approx((DAY + 3_700 - 18_000) / 3600)


def test_rerun_is_idempotent(tmp_path, source_file):
    db_path = tmp_path / "w.db"
    first = pipeline.run(source_file, db_path)
    second = pipeline.run(source_file, db_path)
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM fact_impression").fetchone()[0] == len(BASE_ROWS)
    runs = conn.execute("SELECT run_id, status FROM pipeline_runs ORDER BY run_id").fetchall()
    assert runs == [(first.run_id, "success"), (second.run_id, "success")]
    assert first.rows_loaded == second.rows_loaded == len(BASE_ROWS)


def test_staging_is_dropped_unless_kept(tmp_path, source_file):
    db_path = tmp_path / "w.db"
    pipeline.run(source_file, db_path)
    tables = {r[0] for r in sqlite3.connect(db_path).execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "stg_impressions" not in tables
    pipeline.run(source_file, db_path, keep_staging=True)
    tables = {r[0] for r in sqlite3.connect(db_path).execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "stg_impressions" in tables


def test_bad_header_is_logged_as_failed(tmp_path):
    bad = tmp_path / "bad.tsv.gz"
    with gzip.open(bad, "wt") as f:
        f.write("not\ta\tvalid\theader\n")
    with pytest.raises(SchemaError):
        pipeline.run(bad, tmp_path / "w.db")
    status = sqlite3.connect(tmp_path / "w.db").execute(
        "SELECT status FROM pipeline_runs").fetchone()[0]
    assert status == "failed"
