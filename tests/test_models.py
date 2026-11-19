import numpy as np
import pandas as pd
import pytest

from adauction.extract import CAT_COLUMNS
from adauction.models import (
    N_BITS,
    downsample_negatives,
    evaluate,
    feature_matrix,
    fit,
    normalized_entropy,
    recalibrate,
)


def _frame(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"campaign_id": rng.integers(0, 20, n)})
    for col in CAT_COLUMNS:
        df[col] = rng.integers(0, 50, n) * 1_000_003
    return df


def test_feature_matrix_shape_and_determinism():
    df = _frame(100)
    a, b = feature_matrix(df), feature_matrix(df)
    assert a.shape == (100, 1 << N_BITS)
    assert (a != b).nnz == 0
    # 1 campaign + 9 context + 9 crosses = 19 active features per row
    assert np.all(a.sum(axis=1).A1 == 19)


def test_user_history_adds_five_features():
    df = _frame(50)
    df["time_since_last_click"] = np.where(np.arange(50) % 2 == 0, np.nan, 3600.0)
    df["impression_number"] = np.arange(1, 51)
    df["hour_of_day"] = np.arange(50) % 24
    m = feature_matrix(df)
    assert np.all(m.sum(axis=1).A1 == 24)


def test_same_value_in_different_fields_hashes_differently():
    df = pd.DataFrame({"campaign_id": [7]} | {c: [7] for c in CAT_COLUMNS})
    m = feature_matrix(df)
    assert m.nnz == 19


def test_recalibration_inverts_downsampling():
    # a true rate of 1% looks like about 9.2% after keeping 10% of negatives
    p_true = 0.01
    p_sampled = p_true / (p_true + (1 - p_true) * 0.1)
    assert recalibrate(np.array([p_sampled]), 0.1)[0] == pytest.approx(p_true)


def test_downsampling_keeps_every_positive():
    y = np.array([1] * 50 + [0] * 10_000)
    keep = downsample_negatives(y, 0.1)
    assert keep[:50].all()
    assert 800 < keep[50:].sum() < 1_200


def test_normalized_entropy_is_one_for_the_base_rate():
    y = np.array([0, 0, 0, 1])
    assert normalized_entropy(y, np.full(4, 0.25)) == pytest.approx(1.0)
    assert normalized_entropy(y, np.array([0.1, 0.1, 0.1, 0.9])) < 1.0


def test_model_learns_a_campaign_effect_and_stays_calibrated():
    df = _frame(40_000, seed=3)
    rng = np.random.default_rng(4)
    rate = np.where(df["campaign_id"] < 5, 0.08, 0.01)
    y = (rng.random(len(df)) < rate).astype(int)
    X = feature_matrix(df)
    model = fit(X[:30_000], y[:30_000], "test", neg_rate=0.2, C=0.05)
    p = model.predict(X[30_000:])
    metrics = evaluate(y[30_000:], p)
    assert metrics["auc"] > 0.65
    assert metrics["normalized_entropy"] < 1.0
    assert metrics["calibration"] == pytest.approx(1.0, abs=0.25)
