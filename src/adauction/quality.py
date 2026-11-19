"""Data quality checks that run against the warehouse after every load.

Each check is a SQL query that counts the rows breaking one rule. A check
passes when that count is zero. Checks marked "error" stop the pipeline;
checks marked "warn" are recorded but do not stop it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    severity: str  # "error" or "warn"
    description: str
    sql: str  # returns a single integer: the number of failing rows


CHECKS: list[Check] = [
    # Completeness and reconciliation
    Check(
        "row_count_reconciles",
        "error",
        "Fact table has exactly one row per staged source row",
        "SELECT ABS((SELECT COUNT(*) FROM stg_impressions)"
        " - (SELECT COUNT(*) FROM fact_impression))",
    ),
    Check(
        "spend_reconciles",
        "error",
        "Total spend in the fact table matches the source (to 1e-6)",
        "SELECT ABS((SELECT TOTAL(cost) FROM stg_impressions)"
        " - (SELECT TOTAL(cost) FROM fact_impression)) > 1e-6",
    ),
    Check(
        "no_null_keys",
        "error",
        "Every impression has a timestamp, user and campaign",
        "SELECT COUNT(*) FROM fact_impression"
        " WHERE ts IS NULL OR user_id IS NULL OR campaign_id IS NULL",
    ),
    Check(
        "impression_id_unique",
        "error",
        "impression_id is unique",
        "SELECT COUNT(*) - COUNT(DISTINCT impression_id) FROM fact_impression",
    ),
    # Referential integrity of the star schema
    Check(
        "fk_campaign",
        "error",
        "Every impression joins to dim_campaign",
        "SELECT COUNT(*) FROM fact_impression f"
        " LEFT JOIN dim_campaign c ON c.campaign_id = f.campaign_id"
        " WHERE c.campaign_id IS NULL",
    ),
    Check(
        "fk_date",
        "error",
        "Every impression joins to dim_date",
        "SELECT COUNT(*) FROM fact_impression f"
        " LEFT JOIN dim_date d ON d.day_key = f.day_key WHERE d.day_key IS NULL",
    ),
    Check(
        "fk_user",
        "error",
        "Every impression joins to dim_user",
        "SELECT COUNT(*) FROM fact_impression f"
        " LEFT JOIN dim_user u ON u.user_id = f.user_id WHERE u.user_id IS NULL",
    ),
    # Valid values
    Check(
        "flags_are_binary",
        "error",
        "click, conversion and attributed are 0 or 1",
        "SELECT COUNT(*) FROM fact_impression"
        " WHERE click NOT IN (0, 1) OR conversion NOT IN (0, 1) OR attributed NOT IN (0, 1)",
    ),
    Check(
        "cost_non_negative",
        "error",
        "Price paid is never negative",
        "SELECT COUNT(*) FROM fact_impression WHERE cost < 0",
    ),
    Check(
        "events_in_time_order",
        "error",
        "A conversion never happens before its impression",
        "SELECT COUNT(*) FROM fact_impression WHERE conversion_ts < ts",
    ),
    # Business rules from the dataset documentation
    Check(
        "conversion_fields_consistent",
        "error",
        "conversion_id and conversion_ts are present exactly when conversion = 1",
        "SELECT COUNT(*) FROM fact_impression WHERE"
        " (conversion = 1 AND (conversion_id IS NULL OR conversion_ts IS NULL))"
        " OR (conversion = 0 AND (conversion_id IS NOT NULL OR conversion_ts IS NOT NULL))",
    ),
    Check(
        "attribution_implies_conversion",
        "error",
        "An impression can only be attributed if it led to a conversion",
        "SELECT COUNT(*) FROM fact_impression WHERE attributed = 1 AND conversion = 0",
    ),
    Check(
        "conversion_single_user",
        "error",
        "Each conversion belongs to exactly one user",
        "SELECT COUNT(*) FROM (SELECT conversion_id FROM fact_impression"
        " WHERE conversion_id IS NOT NULL GROUP BY conversion_id"
        " HAVING COUNT(DISTINCT user_id) > 1)",
    ),
    Check(
        "source_sorted_by_time",
        "warn",
        "Source rows arrive in timestamp order (documented by Criteo)",
        "SELECT COUNT(*) FROM (SELECT ts, LAG(ts) OVER (ORDER BY impression_id) AS prev_ts"
        " FROM fact_impression) WHERE ts < prev_ts",
    ),
    Check(
        "conversion_journeys_complete",
        "error",
        "fact_conversion has one row per distinct conversion_id",
        "SELECT ABS((SELECT COUNT(DISTINCT conversion_id) FROM fact_impression)"
        " - (SELECT COUNT(*) FROM fact_conversion))",
    ),
]


@dataclass
class CheckResult:
    name: str
    severity: str
    description: str
    failing_rows: int

    @property
    def passed(self) -> bool:
        return self.failing_rows == 0


class DataQualityError(RuntimeError):
    def __init__(self, failures: list[CheckResult]):
        names = ", ".join(f"{f.name} ({f.failing_rows})" for f in failures)
        super().__init__(f"data quality checks failed: {names}")
        self.failures = failures


def run_checks(
    conn: sqlite3.Connection, run_id: int | None = None, checks: list[Check] = CHECKS
) -> list[CheckResult]:
    """Run every check, store the results in dq_results, and return them."""
    results = []
    for check in checks:
        failing = int(conn.execute(check.sql).fetchone()[0] or 0)
        results.append(CheckResult(check.name, check.severity, check.description, failing))
    conn.executemany(
        "INSERT INTO dq_results (run_id, check_name, severity, description, failing_rows, passed)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            (run_id, r.name, r.severity, r.description, r.failing_rows, int(r.passed))
            for r in results
        ],
    )
    conn.commit()
    return results


def raise_on_errors(results: list[CheckResult]) -> None:
    failures = [r for r in results if r.severity == "error" and not r.passed]
    if failures:
        raise DataQualityError(failures)
