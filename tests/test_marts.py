import sqlite3

import pandas as pd
import pytest


def _read(warehouse, table):
    return pd.read_sql(f"SELECT * FROM {table}", sqlite3.connect(warehouse))


def test_campaign_daily_kpis(warehouse):
    df = _read(warehouse, "mart_campaign_daily").set_index(["campaign_id", "day_key"])
    day0 = df.loc[(10, 0)]
    assert day0["impressions"] == 3
    assert day0["clicks"] == 2
    assert day0["conversions"] == 1
    assert day0["attributed_conversions"] == 1
    assert day0["spend"] == pytest.approx(1.70)
    assert day0["ecpm"] == pytest.approx(1000 * 1.70 / 3)
    assert day0["cpc"] == pytest.approx(1.70 / 2)
    assert day0["cpa"] == pytest.approx(1.70)
    assert day0["roas"] == pytest.approx(20.0 / 1.70)
    # no attributed conversion: CPA is undefined rather than zero
    assert pd.isna(df.loc[(20, 0), "cpa"])


def test_daily_mart_rolls_up_campaigns(warehouse):
    daily = _read(warehouse, "mart_daily").set_index("day_key")
    campaign = _read(warehouse, "mart_campaign_daily")
    assert daily["spend"].sum() == pytest.approx(campaign["spend"].sum())
    assert daily.loc[0, "active_campaigns"] == 2
    assert daily["impressions"].sum() == 7


def test_price_deciles_cover_all_spend(warehouse):
    df = _read(warehouse, "mart_price_deciles")
    assert df["impressions"].sum() == 7
    assert df["spend_share"].sum() == pytest.approx(1.0)
    assert df["min_price"].is_monotonic_increasing


def test_frequency_buckets(warehouse):
    df = _read(warehouse, "mart_frequency").set_index("impression_number")
    assert df.loc["1", "impressions"] == 4
    assert df.loc["2", "impressions"] == 2
    assert df.loc["3", "impressions"] == 1
    assert df["spend_share"].sum() == pytest.approx(1.0)


def test_conversion_delay(warehouse):
    df = _read(warehouse, "mart_conversion_delay")
    # both journeys convert 1 to 24 hours after their last click
    assert df["delay"].tolist() == ["1 to 24 hours"]
    assert df["cumulative_share"].iloc[-1] == pytest.approx(1.0)
