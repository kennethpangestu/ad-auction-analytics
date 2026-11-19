import numpy as np
import pytest

from adauction.replay import multiplier_for_spend, replay, spend_curve

COST = np.array([1.0, 2.0, 3.0, 4.0])
VALUE = np.array([10.0, 0.0, 6.0, 0.0])
CONV = np.array([1.0, 0.0, 1.0, 0.0])


def test_win_only_when_bid_covers_price_paid():
    out = replay(np.array([1.0, 1.9, 3.0, 0.0]), COST, VALUE, CONV)
    # wins auctions 0 and 2 (bid == cost counts as a win), loses 1 and 3
    assert out["impressions"] == 2
    assert out["spend"] == pytest.approx(4.0)
    assert out["conversions"] == 2
    assert out["profit"] == pytest.approx(12.0)
    assert out["cpa"] == pytest.approx(2.0)


def test_infinite_bids_reproduce_the_log():
    out = replay(np.full(4, np.inf), COST, VALUE, CONV)
    assert out["spend"] == COST.sum()
    assert out["conversions"] == CONV.sum()


def test_zero_bids_buy_nothing():
    out = replay(np.zeros(4), COST, VALUE, CONV)
    assert out["impressions"] == 0 and out["spend"] == 0
    assert np.isnan(out["cpa"])


def test_multiplier_hits_the_budget():
    score = np.array([0.5, 0.1, 0.4, 0.2])
    m = multiplier_for_spend(score, COST, target_spend=4.0)
    out = replay(m * score, COST, VALUE, CONV)
    assert out["spend"] == pytest.approx(4.0)


def test_spend_never_exceeds_much_and_grows_with_budget():
    rng = np.random.default_rng(0)
    cost = rng.gamma(2.0, 1.0, 5_000)
    conv = (rng.random(5_000) < 0.05).astype(float)
    score = rng.random(5_000)
    curve = spend_curve({"s": score}, cost, conv, conv, np.linspace(0.1, 1.0, 10))
    assert curve["spend_share"].is_monotonic_increasing
    # bisection lands within one impression's price of each target
    assert (curve["spend_share"] - curve["budget_share"]).abs().max() < cost.max() / cost.sum()


def test_a_perfect_score_beats_a_flat_bid():
    rng = np.random.default_rng(1)
    cost = rng.gamma(2.0, 1.0, 20_000)
    conv = (rng.random(20_000) < 0.02).astype(float)
    perfect = conv + 1e-6
    flat = np.ones_like(cost)
    curve = spend_curve({"perfect": perfect, "flat": flat}, cost, conv, conv, np.array([0.2]))
    by = curve.set_index("strategy")
    assert by.loc["perfect", "conversion_share"] > by.loc["flat", "conversion_share"]
    assert by.loc["perfect", "value_share"] > by.loc["flat", "value_share"]
