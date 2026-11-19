import json

import pytest

from adauction import report


def test_report_writes_every_output(warehouse, tmp_path):
    metrics = report.build(warehouse, tmp_path, run_bidding=False)
    for name in ["cpa_by_price_decile", "cpa_by_frequency", "conversion_delay"]:
        assert (tmp_path / "figures" / f"{name}.png").stat().st_size > 0
    for name in ["data_quality", "price_deciles", "frequency", "conversion_delay", "daily"]:
        assert (tmp_path / "tables" / f"{name}.csv").exists()
    assert json.loads((tmp_path / "metrics.json").read_text()) == json.loads(
        json.dumps(metrics, default=str))
    assert "## Price paid" in (tmp_path / "findings.md").read_text()


def test_headline_numbers(warehouse, tmp_path):
    h = report.build(warehouse, tmp_path, run_bidding=False)["headline"]
    assert h["impressions"] == 7
    assert h["journeys"] == 2
    assert h["attributed_journeys"] == 1
    assert h["attributed_conversions"] == 1
    assert h["spend"] == pytest.approx(2.75)
    assert h["dq_error_checks_passed"] == h["dq_error_checks"]
    assert h["dq_warnings_raised"] == 0
