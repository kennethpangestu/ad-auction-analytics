"""Bidding experiment: does an attribution-aware model buy more value per dollar?

Two models predict, for each impression, the chance that it pays off:

  conversion model   P(the click leads to any conversion)
  attribution model  P(the impression becomes the last click of a conversion
                       that the advertiser attributes to Criteo)

Criteo is paid the advertiser's cost per order (cpo) only for the second kind,
so the expected value of an impression is cpo x probability, and the bid is
    bid = multiplier x cpo x predicted probability
The replay in replay.py measures what each bidder would have bought on the
held-out days at the same budget: attributed conversions and their value.
Two simple baselines are included: a flat bid (every auction is worth the
same, so the cheapest impressions are kept) and the campaign's historical rate.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import models, replay
from .extract import CAT_COLUMNS

log = logging.getLogger(__name__)

TRAIN_DAYS = range(0, 21)  # three weeks to learn from
TEST_DAYS = range(21, 31)  # the last ten days are held out
VALID_DAYS = range(18, 21)  # end of the training window, used to pick C
NEG_RATE = 0.05
C_GRID = (0.01, 0.03, 0.1)
LABELS = {"conversion": "conversion", "attribution": "credited"}
BUDGET_SHARES = np.round(np.arange(0.1, 1.0001, 0.05), 2)
PRIOR_IMPRESSIONS = 1_000  # strength of the shrinkage for the campaign baseline

_DTYPES = {
    "impression_id": "int32", "day_key": "int8", "campaign_id": "int32",
    **{c: "int32" for c in CAT_COLUMNS},
    "cost": "float64", "cpo": "float64", "conversion": "int8", "credited": "int8",
    # bid-time user history (time_since_last_click is NULL when no earlier click)
    "time_since_last_click": "float64", "impression_number": "int32", "hour_of_day": "int8",
}
_COLUMNS = ", ".join(_DTYPES)


@dataclass
class BiddingResult:
    model_metrics: pd.DataFrame
    curve: pd.DataFrame
    chosen_c: dict[str, float]
    train_rows: dict[str, int] = field(default_factory=dict)


def _read(conn: sqlite3.Connection, days: range, sampled: bool) -> pd.DataFrame:
    """Read a day range. With sampled=True keep all conversions and a hash-based
    NEG_RATE share of everything else (deterministic, so reruns match)."""
    where = f"day_key BETWEEN {days.start} AND {days.stop - 1}"
    if sampled:
        where += (
            f" AND (conversion = 1 OR ((impression_id * 2654435761) % 1000000)"
            f" < {int(NEG_RATE * 1_000_000)})"
        )
    query = f"SELECT {_COLUMNS} FROM fact_impression WHERE {where}"
    # Read in chunks and shrink the types as we go: millions of rows as Python
    # objects would need several GB of memory, compact NumPy columns need ~70 bytes a row.
    parts = [chunk.astype(_DTYPES) for chunk in pd.read_sql(query, conn, chunksize=500_000)]
    return pd.concat(parts, ignore_index=True)


def _in_sample(df: pd.DataFrame) -> np.ndarray:
    ids = df["impression_id"].to_numpy().astype(np.int64)
    return ((ids * 2654435761) % 1_000_000) < NEG_RATE * 1_000_000


def _training_set(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Every positive for this label, plus the uniformly sampled negatives."""
    y = df[LABELS[label]].to_numpy()
    return df[(y == 1) | _in_sample(df)]


def _predict(fitted: models.FittedModel, df: pd.DataFrame, chunk: int = 1_000_000) -> np.ndarray:
    out = np.empty(len(df))
    for start in range(0, len(df), chunk):
        part = df.iloc[start : start + chunk]
        out[start : start + len(part)] = fitted.predict(models.feature_matrix(part))
    return out


def _fit(df: pd.DataFrame, label: str, C: float) -> models.FittedModel:
    train = _training_set(df, label)
    return models.fit(
        models.feature_matrix(train), train[LABELS[label]].to_numpy(), label,
        neg_rate=NEG_RATE, C=C, presampled=True,
    )


def _choose_c(sampled_train: pd.DataFrame, valid: pd.DataFrame, label: str) -> float:
    fit_part = sampled_train[sampled_train["day_key"] < VALID_DAYS.start]
    y_valid = valid[LABELS[label]].to_numpy()
    scores = {}
    for C in C_GRID:
        p = _predict(_fit(fit_part, label, C), valid)
        scores[C] = models.normalized_entropy(y_valid, p)
        log.info("  %s model, C=%s: validation normalized entropy %.4f", label, C, scores[C])
    return min(scores, key=scores.get)


def run(conn: sqlite3.Connection) -> BiddingResult:
    log.info("bidding: reading training sample and held-out days")
    sampled_train = _read(conn, TRAIN_DAYS, sampled=True)
    valid = _read(conn, VALID_DAYS, sampled=False)
    test = _read(conn, TEST_DAYS, sampled=False)

    chosen, predictions, metrics, train_rows = {}, {}, [], {}
    for label in LABELS:
        chosen[label] = _choose_c(sampled_train, valid, label)
        fitted = _fit(sampled_train, label, chosen[label])
        train_rows[label] = len(_training_set(sampled_train, label))
        predictions[label] = _predict(fitted, test)
        for target in LABELS:
            row = models.evaluate(test[LABELS[target]].to_numpy(), predictions[label])
            metrics.append({"model": label, "evaluated_on": target, **row})
        log.info("  %s model trained on %s rows with C=%s", label, f"{train_rows[label]:,}",
                 chosen[label])
    del valid

    # Campaign baseline: each campaign's credited rate over the training weeks,
    # shrunk toward the overall rate so small campaigns do not get a rate of 0.
    counts = pd.read_sql(
        "SELECT campaign_id, SUM(credited) AS credited, COUNT(*) AS n FROM fact_impression"
        f" WHERE day_key BETWEEN {TRAIN_DAYS.start} AND {TRAIN_DAYS.stop - 1}"
        " GROUP BY campaign_id",
        conn,
    ).set_index("campaign_id")
    overall = counts["credited"].sum() / counts["n"].sum()
    rates = (counts["credited"] + PRIOR_IMPRESSIONS * overall) / (counts["n"] + PRIOR_IMPRESSIONS)
    campaign_rate = test["campaign_id"].map(rates).fillna(overall).to_numpy()

    cpo = test["cpo"].to_numpy()
    cost = test["cost"].to_numpy()
    credited = test["credited"].to_numpy().astype(float)
    strategies = {
        "Flat bid": np.ones(len(test)),
        "Campaign average": cpo * campaign_rate,
        "Conversion model": cpo * predictions["conversion"],
        "Attribution model": cpo * predictions["attribution"],
    }
    curve = replay.spend_curve(strategies, cost, cpo * credited, credited, BUDGET_SHARES)
    return BiddingResult(pd.DataFrame(metrics), curve, chosen, train_rows)
