"""Offline replay of bidding strategies on logged second-price auctions.

Every row in the log is an auction the bidder won, and `cost` is the price it
paid. In a second-price auction that price is set by the competition, not by
our own bid. So if a new strategy had bid b on the same request:

    b >= cost  ->  it still wins and pays the same cost
    b <  cost  ->  it loses, pays nothing and gets no conversion

This makes it possible to evaluate any strategy that bids *less* than the
logged bidder without running a live test. It cannot evaluate bidding more,
because auctions the logged bidder lost are not in the data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def replay(bids: np.ndarray, cost: np.ndarray, value: np.ndarray, conv: np.ndarray) -> dict:
    """Outcome of bidding `bids` on the logged auctions."""
    win = bids >= cost
    spend = float(cost[win].sum())
    total_value = float(value[win].sum())
    conversions = float(conv[win].sum())
    return {
        "impressions": int(win.sum()),
        "spend": spend,
        "conversions": conversions,
        "value": total_value,
        "profit": total_value - spend,
        "cpa": spend / conversions if conversions else np.nan,
    }


def multiplier_for_spend(
    score: np.ndarray, cost: np.ndarray, target_spend: float, iters: int = 60
) -> float:
    """Find the bid multiplier m so that bidding m * score spends about target_spend.

    Spend only goes up as m goes up, so a bisection on log(m) converges.
    """
    score = np.asarray(score, dtype=float)
    positive = score > 0
    if target_spend <= 0 or not positive.any():
        return 0.0
    ratio = cost[positive] / score[positive]
    lo, hi = np.log(max(ratio.min(), 1e-12)) - 1, np.log(ratio.max()) + 1
    for _ in range(iters):
        mid = (lo + hi) / 2
        spend = cost[score * np.exp(mid) >= cost].sum()
        if spend < target_spend:
            lo = mid
        else:
            hi = mid
    return float(np.exp(hi))


def spend_curve(
    strategies: dict[str, np.ndarray],
    cost: np.ndarray,
    value: np.ndarray,
    conv: np.ndarray,
    budget_shares: np.ndarray,
) -> pd.DataFrame:
    """Replay each strategy at a range of budgets (as shares of logged spend)."""
    logged_spend = cost.sum()
    logged_conv = conv.sum()
    logged_value = value.sum()
    rows = []
    for name, score in strategies.items():
        for share in budget_shares:
            m = multiplier_for_spend(score, cost, share * logged_spend)
            out = replay(m * score, cost, value, conv)
            out.update(
                strategy=name,
                budget_share=float(share),
                spend_share=out["spend"] / logged_spend,
                conversion_share=out["conversions"] / logged_conv if logged_conv else np.nan,
                value_share=out["value"] / logged_value if logged_value else np.nan,
            )
            rows.append(out)
    return pd.DataFrame(rows)
