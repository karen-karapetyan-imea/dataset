#!/usr/bin/env python3
"""Backfill historical crawler outputs into Bronze Parquet."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# When running as `python lakehouse/jobs/migrate_legacy.py`, Python puts
# `lakehouse/jobs/` on `sys.path`, so the sibling `lakehouse/` package
# isn't importable unless we add the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lakehouse.utils.bronze_ingest import build_bronze_record, iter_mapping_rows, write_bronze_batch
from lakehouse.utils.storage import data_root, ensure_lakehouse_paths, infer_source

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate legacy crawl outputs to Bronze.")
    parser.add_argument("--mapping", required=True, help="Historical results JSONL file")
    parser.add_argument(
        "--html-dirs",
        required=True,
        help="Comma-separated HTML directories to search",
    )
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--manifest", default=None, help="Optional skip/error manifest JSONL path")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    mapping_file = Path(args.mapping).resolve()
    html_dirs = [Path(item.strip()).resolve() for item in args.html_dirs.split(",") if item.strip()]
    root = Path(args.data_root).resolve() if args.data_root else data_root()
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else root / "bronze" / "_migration_manifest.jsonl"
    )

    if not mapping_file.is_file():
        LOGGER.error("Mapping file not found: %s", mapping_file)
        return 1
    if not html_dirs:
        LOGGER.error("At least one HTML directory is required")
        return 1

    ensure_lakehouse_paths()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {"rows": 0, "skipped": 0, "batches": 0}
    batches: dict[str, list[dict[str, Any]]] = {}

    with manifest_path.open("w", encoding="utf-8") as manifest:
        for row in iter_mapping_rows(mapping_file):
            stats["rows"] += 1
            url = str(row.get("url") or "").strip()
            source = infer_source(url)
            if source is None:
                stats["skipped"] += 1
                manifest.write(
                    json.dumps({"status": "skip", "url": url, "reason": "unknown_source"}) + "\n"
                )
                continue

            crawl_job_id = f"legacy-{source}"
            record = build_bronze_record(
                row,
                source=source,
                html_dir=html_dirs[0],
                crawl_job_id=crawl_job_id,
                html_dirs=html_dirs,
            )
            partition_key = f"{record['source']}:{record['crawl_date']}"
            batches.setdefault(partition_key, []).append(record)

            if len(batches[partition_key]) >= args.batch_size:
                source_key, date_key = partition_key.split(":", 1)
                write_bronze_batch(
                    batches[partition_key],
                    source=source_key,
                    crawl_date=date_key,
                    data_root=root,
                )
                stats["batches"] += 1
                batches[partition_key] = []

            if stats["rows"] % 50_000 == 0:
                LOGGER.info(
                    "Migration progress rows=%s skipped=%s batches=%s",
                    stats["rows"],
                    stats["skipped"],
                    stats["batches"],
                )

        for partition_key, records in batches.items():
            if not records:
                continue
            source_key, date_key = partition_key.split(":", 1)
            write_bronze_batch(records, source=source_key, crawl_date=date_key, data_root=root)
            stats["batches"] += 1

    LOGGER.info(
        "Migration complete rows=%s skipped=%s batches=%s manifest=%s",
        stats["rows"],
        stats["skipped"],
        stats["batches"],
        manifest_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
