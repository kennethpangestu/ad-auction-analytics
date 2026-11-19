"""Turn the warehouse into the numbers and charts shown in the README.

Writes:
  reports/findings.md     every headline number, generated, never typed by hand
  reports/metrics.json    the same numbers in machine-readable form
  reports/tables/*.csv    the mart tables behind each chart
  reports/figures/*.png   the charts
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import bidding  # noqa: E402

log = logging.getLogger(__name__)

# Reference palette (light mode): categorical slots in fixed order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
STRATEGY_COLORS = {
    "Attribution model": SERIES[0],
    "Conversion model": SERIES[1],
    "Campaign average": SERIES[2],
    "Flat bid": SERIES[3],
}


def _style(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=22 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_2)


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _bar(ax, labels, values, highlight: int | None = None) -> None:
    colors = [SERIES[0]] * len(values)
    if highlight is not None:
        colors = ["#a9c7ee"] * len(values)
        colors[highlight] = SERIES[0]
    ax.bar(labels, values, color=colors, width=0.7, edgecolor=SURFACE, linewidth=2)


def _query(conn, sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, conn)


def headline(conn: sqlite3.Connection) -> dict:
    row = _query(conn, """
        SELECT COUNT(*) AS impressions, COUNT(DISTINCT user_id) AS users,
               COUNT(DISTINCT campaign_id) AS campaigns, COUNT(DISTINCT day_key) AS days,
               SUM(click) AS clicks, SUM(is_last_click) AS conversions_with_last_click,
               SUM(credited) AS attributed_conversions, TOTAL(cost) AS spend,
               TOTAL(CASE WHEN credited = 1 THEN cpo END) AS attributed_value
        FROM fact_impression""").iloc[0].to_dict()
    journeys = _query(conn, """
        SELECT COUNT(*) AS journeys, SUM(attributed) AS attributed_journeys,
               AVG(clicks_total) AS avg_clicks_before_conversion
        FROM fact_conversion""").iloc[0].to_dict()
    checks = _query(conn, """
        SELECT severity, COUNT(*) AS n, SUM(passed) AS passed FROM dq_results
        WHERE run_id = (SELECT MAX(run_id) FROM pipeline_runs WHERE status = 'success')
        GROUP BY severity""").set_index("severity")
    run = _query(conn, """
        SELECT rows_loaded, seconds FROM pipeline_runs WHERE status = 'success'
        ORDER BY run_id DESC LIMIT 1""").iloc[0].to_dict()
    out = {
        k: int(v) if float(v).is_integer() else float(v) for k, v in {**row, **journeys}.items()
    }
    out["attribution_rate"] = out["attributed_journeys"] / out["journeys"]
    out["cpa"] = out["spend"] / out["attributed_conversions"]
    out["dq_checks"] = int(checks["n"].sum())
    out["dq_error_checks_passed"] = int(checks.loc["error", "passed"])
    out["dq_error_checks"] = int(checks.loc["error", "n"])
    out["dq_warnings_raised"] = int(checks.loc["warn", "n"] - checks.loc["warn", "passed"])
    out["etl_seconds"] = float(run["seconds"])
    return out


def build(db_path: str | Path, out_dir: str | Path, run_bidding: bool = True) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    metrics = {"headline": headline(conn)}
    dq = _query(conn, """
        SELECT check_name, severity, description, failing_rows, passed FROM dq_results
        WHERE run_id = (SELECT MAX(run_id) FROM pipeline_runs WHERE status = 'success')""")
    deciles = _query(conn, "SELECT * FROM mart_price_deciles ORDER BY price_decile")
    freq = _query(conn, "SELECT * FROM mart_frequency ORDER BY bucket_order")
    delay = _query(conn, "SELECT * FROM mart_conversion_delay ORDER BY bucket_order")
    daily = _query(conn, "SELECT * FROM mart_daily ORDER BY day_key")
    for name, df in [("data_quality", dq), ("price_deciles", deciles), ("frequency", freq),
                     ("conversion_delay", delay), ("daily", daily)]:
        df.to_csv(out_dir / "tables" / f"{name}.csv", index=False)

    # Chart 1: CPA by price decile
    fig, ax = plt.subplots(figsize=(8, 4.2))
    _bar(ax, deciles["price_decile"].astype(str), deciles["cpa"], highlight=len(deciles) - 1)
    top = deciles.iloc[-1]
    _style(ax, "Cost per attributed conversion by price paid",
           f"Impressions in 10 equal groups by price. The priciest group is "
           f"{top['spend_share']:.0%} of spend.")
    ax.set_xlabel("Price decile (1 = cheapest 10% of impressions)", color=INK_2, fontsize=9)
    ax.set_ylabel("Spend per attributed conversion", color=INK_2, fontsize=9)
    _save(fig, out_dir / "figures" / "cpa_by_price_decile.png")

    # Chart 2: CPA by how many times the user had seen the campaign
    fig, ax = plt.subplots(figsize=(8, 4.2))
    _bar(ax, freq["impression_number"], freq["cpa"])
    _style(ax, "Cost per attributed conversion by impression number",
           "How many times the user had seen the same campaign, including this impression.")
    ax.set_xlabel("Impression number for this user and campaign", color=INK_2, fontsize=9)
    ax.set_ylabel("Spend per attributed conversion", color=INK_2, fontsize=9)
    _save(fig, out_dir / "figures" / "cpa_by_frequency.png")

    # Chart 3: how fast conversions arrive after the last click
    fig, ax = plt.subplots(figsize=(8, 4.2))
    within_labels = {1: "1 hour", 2: "1 day", 3: "3 days", 4: "7 days", 5: "14 days",
                     6: "30 days"}
    _bar(ax, delay["bucket_order"].map(within_labels), delay["cumulative_share"] * 100)
    for i, v in enumerate(delay["cumulative_share"] * 100):
        ax.text(i, v + 1.5, f"{v:.0f}%", ha="center", fontsize=9, color=INK)
    _style(ax, "Share of conversions that have arrived, by time since the last click",
           "A day's CPA keeps changing until its late conversions come in.")
    ax.set_ylim(0, 110)
    ax.set_xlabel("Time since the last click", color=INK_2, fontsize=9)
    ax.set_ylabel("% of conversions arrived", color=INK_2, fontsize=9)
    _save(fig, out_dir / "figures" / "conversion_delay.png")

    def cpa(rows: pd.DataFrame) -> float:
        conversions = rows["attributed_conversions"].sum()
        return float(rows["spend"].sum() / conversions) if conversions else float("nan")

    bottom_half = deciles[deciles["price_decile"] <= 5]
    metrics["price_deciles"] = {
        "top_decile_spend_share": float(top["spend_share"]),
        "top_decile_attributed_share": float(top["attributed_share"]),
        "top_decile_cpa": float(top["cpa"]),
        "bottom_half_spend_share": float(bottom_half["spend_share"].sum()),
        "bottom_half_attributed_share": float(bottom_half["attributed_share"].sum()),
        "bottom_half_cpa": cpa(bottom_half),
    }
    first = freq.iloc[0]
    over_10 = freq[freq["bucket_order"] >= 6]
    metrics["frequency"] = {
        "first_impression_cpa": float(first["cpa"]),
        "first_impression_spend_share": float(first["spend_share"]),
        "over_10_spend_share": float(over_10["spend_share"].sum()),
        "over_10_cpa": cpa(over_10),
    }
    # Buckets with no conversions are missing from the mart, so fill them forward.
    within = (delay.set_index("bucket_order")["cumulative_share"]
              .reindex(range(1, 7)).ffill().fillna(0.0))
    metrics["conversion_delay"] = {
        "within_1_hour": float(within[1]),
        "within_1_day": float(within[2]),
        "within_7_days": float(within[4]),
        "after_7_days": float(1 - within[4]),
    }

    if run_bidding:
        result = bidding.run(conn)
        result.model_metrics.to_csv(out_dir / "tables" / "model_metrics.csv", index=False)
        result.curve.to_csv(out_dir / "tables" / "bidding_replay.csv", index=False)
        metrics["bidding"] = _bidding_metrics(result)
        _replay_chart(result.curve, out_dir / "figures" / "bidding_replay.png")

    conn.close()
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    (out_dir / "findings.md").write_text(_findings_md(metrics, dq))
    log.info("wrote %s", out_dir)
    return metrics


def _bidding_metrics(result: bidding.BiddingResult) -> dict:
    curve = result.curve
    mm = result.model_metrics.set_index(["model", "evaluated_on"])

    def at(share: float, column: str) -> dict:
        part = curve[curve["budget_share"] == share].set_index("strategy")
        return {k: float(v) for k, v in part[column].items()}

    return {
        "chosen_c": result.chosen_c,
        "train_rows": result.train_rows,
        "test_attributed_conversions": int(
            curve[curve["budget_share"] == 1.0]["conversions"].max()),
        "value_share_at_50": at(0.5, "value_share"),
        "value_share_at_20": at(0.2, "value_share"),
        "conversion_share_at_50": at(0.5, "conversion_share"),
        "cpa_at_50": at(0.5, "cpa"),
        "roas_at_50": {k: v / s for (k, v), s in zip(at(0.5, "value").items(),
                                                     at(0.5, "spend").values(), strict=True)},
        "attribution_model_on_attribution": mm.loc[("attribution", "attribution")].to_dict(),
        "conversion_model_on_attribution": mm.loc[("conversion", "attribution")].to_dict(),
        "conversion_model_on_conversion": mm.loc[("conversion", "conversion")].to_dict(),
    }


def _replay_chart(curve: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for name, color in STRATEGY_COLORS.items():
        part = curve[curve["strategy"] == name]
        ax.plot(part["spend_share"] * 100, part["value_share"] * 100, color=color,
                linewidth=2, label=name)
        mid = part[part["budget_share"] == 0.5].iloc[0]
        ax.plot(mid["spend_share"] * 100, mid["value_share"] * 100, "o", color=color,
                markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
    ax.axvline(50, color=GRID, linewidth=1, linestyle="--")
    _style(ax, "Attributed order value kept when the budget is cut",
           "Replay on the 10 held-out days. Dots mark half of the logged spend.")
    ax.set_xlabel("Spend, % of what the logged bidder spent", color=INK_2, fontsize=9)
    ax.set_ylabel("Attributed order value, % of logged", color=INK_2, fontsize=9)
    ax.set_xlim(0, 102)
    ax.set_ylim(0, 102)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right")
    _save(fig, path)


def _pct(x: float) -> str:
    return f"{x:.1%}"


def _findings_md(m: dict, dq: pd.DataFrame) -> str:
    h = m["headline"]
    lines = [
        "# Findings (generated by `python -m adauction analyze`)",
        "",
        "## Warehouse",
        "",
        f"- Impressions: {h['impressions']:,} across {h['campaigns']:,} campaigns, "
        f"{h['users']:,} users and {h['days']} days",
        f"- Clicks: {h['clicks']:,}",
        f"- Conversion journeys: {h['journeys']:,}, of which {h['attributed_journeys']:,} "
        f"({_pct(h['attribution_rate'])}) were attributed to Criteo",
        f"- Attributed conversions with their last click in the data: "
        f"{h['attributed_conversions']:,}",
        f"- Spend: {h['spend']:,.2f} (transformed units), CPA {h['cpa']:.4f}",
        f"- ETL run time: {h['etl_seconds']:.0f} seconds",
        f"- Data quality: {h['dq_checks']} checks, {h['dq_error_checks_passed']} of "
        f"{h['dq_error_checks']} blocking checks passed, {h['dq_warnings_raised']} warnings",
        "",
        "| Check | Severity | Failing rows | Result |",
        "|---|---|---|---|",
    ]
    for r in dq.itertuples():
        lines.append(f"| `{r.check_name}` | {r.severity} | {r.failing_rows:,} | "
                     f"{'pass' if r.passed else 'warning' if r.severity == 'warn' else 'FAIL'} |")
    p, f, d = m["price_deciles"], m["frequency"], m["conversion_delay"]
    lines += [
        "",
        "## Price paid",
        "",
        f"- The most expensive 10% of impressions took {_pct(p['top_decile_spend_share'])} of "
        f"spend and earned {_pct(p['top_decile_attributed_share'])} of attributed conversions",
        f"- CPA in that top group: {p['top_decile_cpa']:.4f}, vs {p['bottom_half_cpa']:.4f} in "
        f"the cheapest half (which took {_pct(p['bottom_half_spend_share'])} of spend and earned "
        f"{_pct(p['bottom_half_attributed_share'])} of attributed conversions)",
        "",
        "## Frequency",
        "",
        f"- First impressions: CPA {f['first_impression_cpa']:.4f}, "
        f"{_pct(f['first_impression_spend_share'])} of spend",
        f"- Impression 11 and later: CPA {f['over_10_cpa']:.4f}, "
        f"{_pct(f['over_10_spend_share'])} of spend",
        "",
        "## Conversion delay (from last click)",
        "",
        f"- Within 1 hour: {_pct(d['within_1_hour'])}; within 1 day: {_pct(d['within_1_day'])}; "
        f"within 7 days: {_pct(d['within_7_days'])}; after 7 days: {_pct(d['after_7_days'])}",
    ]
    if "bidding" in m:
        b = m["bidding"]
        att = b["attribution_model_on_attribution"]
        conv = b["conversion_model_on_conversion"]
        conv_att = b["conversion_model_on_attribution"]
        lines += [
            "",
            "## Bidding replay (days 21 to 30)",
            "",
            f"- Held-out attributed conversions: {b['test_attributed_conversions']:,}",
            "- Training rows after negative downsampling: "
            + ", ".join(f"{k} model {v:,}" for k, v in b["train_rows"].items()),
            f"- Regularization chosen on days 18 to 20: {b['chosen_c']}",
            "",
            "| Model | Label | AUC | Normalized entropy | Calibration | AUC on attributed label |",
            "|---|---|---|---|---|---|",
            f"| Attribution model | last click of an attributed conversion | {att['auc']:.3f} | "
            f"{att['normalized_entropy']:.3f} | {att['calibration']:.2f} | {att['auc']:.3f} |",
            f"| Conversion model | click followed by any conversion | {conv['auc']:.3f} | "
            f"{conv['normalized_entropy']:.3f} | {conv['calibration']:.2f} | "
            f"{conv_att['auc']:.3f} |",
            "",
            "Share of the logged outcome kept when spend is cut:",
            "",
            "| Strategy | Value kept at 20% spend | Value kept at 50% spend "
            "| Conversions kept at 50% spend | Value per unit of spend at 50% |",
            "|---|---|---|---|---|",
        ]
        for name in STRATEGY_COLORS:
            lines.append(
                f"| {name} | {_pct(b['value_share_at_20'][name])} | "
                f"{_pct(b['value_share_at_50'][name])} | "
                f"{_pct(b['conversion_share_at_50'][name])} | {b['roas_at_50'][name]:.2f} |"
            )
    return "\n".join(lines) + "\n"
