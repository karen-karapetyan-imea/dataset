#!/usr/bin/env python3
"""Ingest crawler HTML + JSONL metadata into Bronze Parquet partitions."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# When running as `python lakehouse/jobs/write_bronze.py`, Python puts
# `lakehouse/jobs/` on `sys.path`, so the sibling `lakehouse/` package
# isn't importable unless we add the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lakehouse.utils.bronze_ingest import ingest_mapping_to_bronze
from lakehouse.utils.storage import data_root, ensure_lakehouse_paths

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write Bronze Parquet from crawler outputs.")
    parser.add_argument("--input", required=True, help="Directory containing sha1.html files")
    parser.add_argument("--mapping", required=True, help="Crawl results JSONL mapping file")
    parser.add_argument("--source", required=True, choices=["saatchi", "artsper", "artsy"])
    parser.add_argument("--crawl-date", required=True, help="Partition crawl date (YYYY-MM-DD)")
    parser.add_argument("--crawl-job-id", default=None, help="Crawl job identifier")
    parser.add_argument("--data-root", default=None, help="Lakehouse data root directory")
    parser.add_argument("--batch-size", type=int, default=10_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    html_dir = Path(args.input).resolve()
    mapping_file = Path(args.mapping).resolve()
    root = Path(args.data_root).resolve() if args.data_root else data_root()
    crawl_job_id = args.crawl_job_id or f"{args.source}-{args.crawl_date}"

    if not html_dir.is_dir():
        LOGGER.error("HTML directory does not exist: %s", html_dir)
        return 1
    if not mapping_file.is_file():
        LOGGER.error("Mapping file does not exist: %s", mapping_file)
        return 1

    ensure_lakehouse_paths()
    stats = ingest_mapping_to_bronze(
        mapping_file=mapping_file,
        html_dir=html_dir,
        source=args.source,
        crawl_date=args.crawl_date,
        crawl_job_id=crawl_job_id,
        data_root=root,
        batch_size=args.batch_size,
    )
    LOGGER.info(
        "Bronze ingest complete: rows=%s batches=%s partitions=%s",
        stats["rows"],
        stats["batches"],
        stats["partitions"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
