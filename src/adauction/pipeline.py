"""End-to-end ETL: extract -> stage -> transform -> quality checks -> marts.

Every run rebuilds the star schema from the source file, so the pipeline can
be re-run safely. Each run is logged in pipeline_runs, and the result of every
data quality check is logged in dq_results.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import db, extract, load, quality

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    run_id: int
    rows_loaded: int
    seconds: float
    checks: list[quality.CheckResult]

    @property
    def checks_passed(self) -> int:
        return sum(c.passed for c in self.checks)

    @property
    def warnings(self) -> int:
        return sum(not c.passed for c in self.checks if c.severity == "warn")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _start_run(conn: sqlite3.Connection, source: Path) -> int:
    cur = conn.execute(
        "INSERT INTO pipeline_runs (started_at, source_file, source_bytes, status)"
        " VALUES (?, ?, ?, 'running')",
        (_now(), source.name, source.stat().st_size),
    )
    conn.commit()
    return cur.lastrowid


def _finish_run(conn, run_id: int, status: str, rows: int | None, seconds: float) -> None:
    conn.execute(
        "UPDATE pipeline_runs SET finished_at = ?, status = ?, rows_loaded = ?, seconds = ?"
        " WHERE run_id = ?",
        (_now(), status, rows, round(seconds, 2), run_id),
    )
    conn.commit()


def run(
    source: str | Path,
    db_path: str | Path,
    chunksize: int = 500_000,
    keep_staging: bool = False,
) -> RunSummary:
    source = Path(source)
    conn = db.connect(db_path)
    started = time.perf_counter()
    db.run_sql_file(conn, db.SQL_DIR / "schema.sql")
    run_id = _start_run(conn, source)
    rows = None
    try:
        log.info("extract + stage: %s", source)
        rows = load.load_staging(conn, extract.iter_chunks(source, chunksize))
        log.info("staged %s rows", f"{rows:,}")

        log.info("transform: %s", ", ".join(db.run_sql_folder(conn, "transform")))

        checks = quality.run_checks(conn, run_id)
        for c in checks:
            status = "PASS" if c.passed else ("WARN" if c.severity == "warn" else "FAIL")
            level = logging.INFO if c.passed else logging.WARNING
            log.log(level, "dq %-32s %s (%s rows)", c.name, status, f"{c.failing_rows:,}")
        quality.raise_on_errors(checks)

        log.info("marts: %s", ", ".join(db.run_sql_folder(conn, "marts")))

        if not keep_staging:
            conn.execute("DROP TABLE stg_impressions")
            conn.commit()
            conn.execute("VACUUM")
    except Exception:
        _finish_run(conn, run_id, "failed", rows, time.perf_counter() - started)
        conn.close()
        raise

    seconds = time.perf_counter() - started
    _finish_run(conn, run_id, "success", rows, seconds)
    conn.close()
    return RunSummary(run_id, rows, seconds, checks)
