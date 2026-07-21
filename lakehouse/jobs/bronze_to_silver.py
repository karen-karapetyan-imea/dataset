#!/usr/bin/env python3
"""Transform Bronze Parquet into Silver Delta tables."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

# When running as `python lakehouse/jobs/bronze_to_silver.py`, Python puts
# `lakehouse/jobs/` on `sys.path`, so the sibling `lakehouse/` package
# isn't importable unless we add the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyspark.sql import Row

from lakehouse.schemas.silver import SILVER_SCHEMA
from lakehouse.utils.compression import decompress_html
from lakehouse.utils.parser_adapter import ensure_crawler_import_path, parse_html_record
from lakehouse.utils.spark import get_spark
from lakehouse.utils.storage import (
    bronze_partition_path,
    data_root,
    ensure_lakehouse_paths,
    silver_artists_path,
    silver_artworks_path,
    silver_failures_path,
)

LOGGER = logging.getLogger(__name__)


def _parse_partition(rows: Iterator[Row]) -> Iterator[tuple[dict[str, Any] | None, dict[str, Any] | None]]:
    ensure_crawler_import_path()
    for row in rows:
        try:
            html_bytes = decompress_html(row.html)
            if not html_bytes:
                yield None, {"status": "skip", "url": row.url, "reason": "empty_html"}
                continue
            silver_row, failure = parse_html_record(
                source=row.source,
                url=row.url,
                html_bytes=html_bytes,
                crawl_timestamp=row.crawl_timestamp,
            )
            yield silver_row, failure
        except Exception as exc:
            yield None, {"status": "error", "url": row.url, "error": str(exc)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bronze to Silver transformation.")
    parser.add_argument("--source", required=True, choices=["saatchi", "artsper", "artsy"])
    parser.add_argument("--crawl-date", required=True, help="Bronze partition crawl date")
    parser.add_argument("--data-root", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    root = Path(args.data_root).resolve() if args.data_root else data_root()
    bronze_path = bronze_partition_path(args.source, args.crawl_date, root)
    if not bronze_path.is_dir():
        LOGGER.error("Bronze partition not found: %s", bronze_path)
        return 1

    ensure_lakehouse_paths()
    spark = get_spark("bronze_to_silver")

    bronze_df = spark.read.parquet(str(bronze_path))
    bronze_df = bronze_df.filter((bronze_df.status_code == 200) & bronze_df.html.isNotNull())

    parsed_rdd = bronze_df.rdd.mapPartitions(_parse_partition)
    silver_rows = parsed_rdd.filter(lambda item: item[0] is not None).map(lambda item: item[0])
    failure_rows = parsed_rdd.filter(lambda item: item[1] is not None).map(lambda item: item[1])

    if silver_rows.isEmpty():
        LOGGER.warning("No silver rows produced for %s/%s", args.source, args.crawl_date)
    else:
        silver_df = spark.createDataFrame(silver_rows, schema=SILVER_SCHEMA)
        artworks_df = silver_df.filter(silver_df.entity_type == "artwork")
        artists_df = silver_df.filter(silver_df.entity_type == "artist")

        artworks_path = silver_artworks_path(root)
        artists_path = silver_artists_path(root)

        if not artworks_df.rdd.isEmpty():
            artworks_df.write.format("delta").mode("append").option("mergeSchema", "true").save(
                str(artworks_path)
            )
            LOGGER.info("Appended artwork rows to %s", artworks_path)

        if not artists_df.rdd.isEmpty():
            artists_df.write.format("delta").mode("append").option("mergeSchema", "true").save(
                str(artists_path)
            )
            LOGGER.info("Appended artist rows to %s", artists_path)

    failures_path = silver_failures_path(args.source, args.crawl_date, root)
    failures_path.mkdir(parents=True, exist_ok=True)
    manifest = failures_path / "failures.jsonl"
    with manifest.open("w", encoding="utf-8") as handle:
        for failure in failure_rows.collect():
            handle.write(json.dumps(failure, default=str) + "\n")
    LOGGER.info("Wrote failure manifest to %s", manifest)

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
