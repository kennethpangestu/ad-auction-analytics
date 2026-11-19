import sqlite3

import pytest

from adauction import pipeline
from adauction.quality import CHECKS, DataQualityError

from .conftest import BASE_ROWS, DAY, write_source

FIELDS = ["timestamp", "uid", "campaign", "conversion", "conversion_timestamp",
          "conversion_id", "attribution", "click", "click_pos", "click_nb",
          "cost", "cpo", "time_since_last_click"]


def _with_changes(*edits: tuple[int, dict]) -> list[tuple]:
    rows = [list(r) for r in BASE_ROWS]
    for row_index, changes in edits:
        for key, value in changes.items():
            rows[row_index][FIELDS.index(key)] = value
    return [tuple(r) for r in rows]


def test_clean_data_passes_every_check(warehouse):
    conn = sqlite3.connect(warehouse)
    results = conn.execute("SELECT check_name, passed FROM dq_results").fetchall()
    assert len(results) == len(CHECKS)
    assert all(passed for _, passed in results)


@pytest.mark.parametrize(
    "edits, failing_check",
    [
        ([(1, {"cost": -0.2})], "prices_positive"),
        ([(1, {"attribution": 1})], "attribution_implies_conversion"),
        ([(1, {"click": 2})], "flags_are_binary"),
        ([(1, {"conversion": 1, "click": 1})], "conversion_fields_consistent"),
        ([(2, {"click": 0})], "conversions_are_post_click"),
        ([(2, {"conversion_timestamp": 10})], "conversion_after_impression"),
        ([(2, {"conversion_timestamp": 300 + 31 * DAY})], "conversion_within_30_days"),
        ([(0, {"click_pos": 5})], "click_position_valid"),
        ([(0, {"click_pos": 1})], "one_last_click_per_journey"),
        ([(3, {"attribution": 0})], "journey_is_consistent"),
    ],
)
def test_bad_rows_fail_the_right_check(tmp_path, edits, failing_check):
    source = write_source(tmp_path / "bad.tsv.gz", _with_changes(*edits))
    with pytest.raises(DataQualityError) as exc:
        pipeline.run(source, tmp_path / "w.db")
    assert failing_check in {f.name for f in exc.value.failures}
    status = sqlite3.connect(tmp_path / "w.db").execute(
        "SELECT status FROM pipeline_runs").fetchone()[0]
    assert status == "failed"


@pytest.mark.parametrize(
    "rows, warning",
    [
        (_with_changes((2, {"conversion_id": 500})), "conversion_id_shared_by_users"),
        (_with_changes((0, {"click_nb": 3}), (3, {"click_nb": 3})), "journeys_missing_last_click"),
        ([BASE_ROWS[1], BASE_ROWS[0], *BASE_ROWS[2:]], "source_sorted_by_time"),
    ],
)
def test_known_release_quirks_only_warn(tmp_path, rows, warning):
    summary = pipeline.run(write_source(tmp_path / "s.tsv.gz", rows), tmp_path / "w.db")
    by_name = {c.name: c for c in summary.checks}
    assert not by_name[warning].passed
    assert by_name[warning].severity == "warn"
    assert all(c.passed for c in summary.checks if c.severity == "error")
