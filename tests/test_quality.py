import sqlite3

import pytest

from adauction import pipeline
from adauction.quality import CHECKS, DataQualityError

from .conftest import BASE_ROWS, write_source


def _with_row(row_index: int, **changes) -> list[tuple]:
    names = ["timestamp", "uid", "campaign", "conversion", "conversion_timestamp",
             "conversion_id", "attribution", "click", "click_pos", "click_nb",
             "cost", "cpo", "time_since_last_click"]
    rows = [list(r) for r in BASE_ROWS]
    for key, value in changes.items():
        rows[row_index][names.index(key)] = value
    return [tuple(r) for r in rows]


def test_clean_data_passes_every_check(warehouse):
    conn = sqlite3.connect(warehouse)
    results = conn.execute("SELECT check_name, passed FROM dq_results").fetchall()
    assert len(results) == len(CHECKS)
    assert all(passed for _, passed in results)


@pytest.mark.parametrize(
    "row_index, changes, failing_check",
    [
        (1, {"cost": -0.2}, "cost_non_negative"),
        (1, {"attribution": 1}, "attribution_implies_conversion"),
        (1, {"click": 2}, "flags_are_binary"),
        (1, {"conversion": 1}, "conversion_fields_consistent"),
        (2, {"conversion_timestamp": 10}, "events_in_time_order"),
        (2, {"conversion_id": 500}, "conversion_single_user"),
    ],
)
def test_bad_rows_fail_the_right_check(tmp_path, row_index, changes, failing_check):
    source = write_source(tmp_path / "bad.tsv.gz", _with_row(row_index, **changes))
    with pytest.raises(DataQualityError) as exc:
        pipeline.run(source, tmp_path / "w.db")
    failed = {f.name for f in exc.value.failures}
    assert failing_check in failed
    status = sqlite3.connect(tmp_path / "w.db").execute(
        "SELECT status FROM pipeline_runs").fetchone()[0]
    assert status == "failed"


def test_unsorted_source_only_warns(tmp_path):
    rows = list(BASE_ROWS)
    rows[0], rows[1] = rows[1], rows[0]
    summary = pipeline.run(write_source(tmp_path / "s.tsv.gz", rows), tmp_path / "w.db")
    by_name = {c.name: c for c in summary.checks}
    assert not by_name["source_sorted_by_time"].passed
    assert by_name["source_sorted_by_time"].severity == "warn"
