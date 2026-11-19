"""Conversion models for bidding, with the hashing trick and negative downsampling.

Features are the campaign, the nine anonymized context features, and each
context feature crossed with the campaign (the setup in Diemert et al. 2017).
Everything is hashed into a fixed number of columns with vectorized NumPy,
so the full feature matrix is built without Python loops over rows.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

from .extract import CAT_COLUMNS

N_BITS = 20
_MASK = np.uint64((1 << N_BITS) - 1)
_M1 = np.uint64(0x9E3779B97F4A7C15)
_M2 = np.uint64(0xBF58476D1CE4E5B9)


def _mix(x: np.ndarray) -> np.ndarray:
    """splitmix64 finalizer: spreads nearby integers across the hash space."""
    with np.errstate(over="ignore"):
        x = (x ^ (x >> np.uint64(30))) * _M2
        x = (x ^ (x >> np.uint64(27))) * _M1
        return x ^ (x >> np.uint64(31))


def _hash_field(field_id: int, values: np.ndarray) -> np.ndarray:
    v = values.astype(np.int64).view(np.uint64)
    with np.errstate(over="ignore"):
        return (_mix(v + np.uint64(field_id) * _M1) & _MASK).astype(np.int32)


def feature_matrix(df: pd.DataFrame) -> sparse.csr_matrix:
    """One-hot hashed features: campaign, cat1-9, and campaign x cat1-9."""
    n = len(df)
    campaign = df["campaign_id"].to_numpy(np.int64)
    columns = [_hash_field(0, campaign)]
    for k, col in enumerate(CAT_COLUMNS, start=1):
        cat = df[col].to_numpy(np.int64)
        columns.append(_hash_field(k, cat))
        with np.errstate(over="ignore"):
            crossed = campaign.view(np.uint64) * np.uint64(1_000_003) + cat.view(np.uint64)
        columns.append(_hash_field(100 + k, crossed.view(np.int64)))
    idx = np.stack(columns, axis=1)
    rows = np.repeat(np.arange(n, dtype=np.int32), idx.shape[1])
    data = np.ones(idx.size, dtype=np.float64)
    m = sparse.csr_matrix((data, (rows, idx.ravel())), shape=(n, 1 << N_BITS))
    m.sum_duplicates()
    return m


def downsample_negatives(y: np.ndarray, rate: float, seed: int = 0) -> np.ndarray:
    """Keep every positive and a random `rate` share of negatives. Returns a mask."""
    rng = np.random.default_rng(seed)
    return (y == 1) | (rng.random(len(y)) < rate)


def recalibrate(p: np.ndarray, rate: float) -> np.ndarray:
    """Undo negative downsampling: map probabilities back to the true base rate."""
    return p / (p + (1.0 - p) / rate)


def normalized_entropy(y: np.ndarray, p: np.ndarray) -> float:
    """Log loss divided by the log loss of always predicting the base rate.

    Below 1.0 means the model carries information beyond the average rate.
    """
    base = np.clip(y.mean(), 1e-12, 1 - 1e-12)
    return log_loss(y, p, labels=[0, 1]) / log_loss(y, np.full(len(y), base), labels=[0, 1])


@dataclass
class FittedModel:
    label: str
    model: LogisticRegression
    neg_rate: float

    def predict(self, X: sparse.csr_matrix) -> np.ndarray:
        return recalibrate(self.model.predict_proba(X)[:, 1], self.neg_rate)


def fit(
    X: sparse.csr_matrix, y: np.ndarray, label: str, neg_rate: float = 0.1, C: float = 0.5
) -> FittedModel:
    keep = downsample_negatives(y, neg_rate)
    model = LogisticRegression(C=C, max_iter=200)
    model.fit(X[keep], y[keep])
    return FittedModel(label, model, neg_rate)


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "auc": float(roc_auc_score(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "normalized_entropy": float(normalized_entropy(y, p)),
        "calibration": float(p.mean() / y.mean()),  # 1.0 = predicted rate matches actual
    }
