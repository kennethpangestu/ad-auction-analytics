"""Command line entry point.

    python -m adauction etl      --source data/raw/criteo_attribution_dataset.tsv.gz
    python -m adauction analyze  --db data/warehouse/ad_auction.db
    python -m adauction sample   --source data/raw/criteo_attribution_dataset.tsv.gz
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import pipeline
from .quality import DataQualityError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "data" / "raw" / "criteo_attribution_dataset.tsv.gz"
DEFAULT_DB = ROOT / "data" / "warehouse" / "ad_auction.db"
DEFAULT_SAMPLE = ROOT / "data" / "sample" / "criteo_sample.tsv.gz"
DEFAULT_REPORTS = ROOT / "reports"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adauction")
    sub = parser.add_subparsers(dest="command", required=True)

    etl = sub.add_parser("etl", help="build the SQLite warehouse from a source file")
    etl.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    etl.add_argument("--db", type=Path, default=DEFAULT_DB)
    etl.add_argument("--chunksize", type=int, default=500_000)
    etl.add_argument("--keep-staging", action="store_true")

    an = sub.add_parser("analyze", help="run the analyses and write reports/")
    an.add_argument("--db", type=Path, default=DEFAULT_DB)
    an.add_argument("--out", type=Path, default=DEFAULT_REPORTS)

    sm = sub.add_parser("sample", help="write a user-level sample of the source file")
    sm.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    sm.add_argument("--out", type=Path, default=DEFAULT_SAMPLE)
    sm.add_argument("--rate", type=float, default=0.01)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    if args.command == "etl":
        try:
            summary = pipeline.run(args.source, args.db, args.chunksize, args.keep_staging)
        except DataQualityError as exc:
            logging.error("%s", exc)
            return 1
        print(
            f"run {summary.run_id}: loaded {summary.rows_loaded:,} rows in "
            f"{summary.seconds:.1f}s, {summary.checks_passed}/{len(summary.checks)} checks passed"
            f" ({summary.warnings} warning{'' if summary.warnings == 1 else 's'})"
        )
    elif args.command == "analyze":
        from . import report

        report.build(args.db, args.out)
    elif args.command == "sample":
        from . import sample

        n = sample.write_user_sample(args.source, args.out, args.rate)
        print(f"wrote {n:,} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
