#!/usr/bin/env python3
"""Inspect lakehouse Bronze/Silver/Gold tables from the terminal."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# When running as `python lakehouse/scripts/inspect_data.py`, Python puts
# `lakehouse/scripts/` on `sys.path`, so the sibling `lakehouse/` package
# isn't importable unless we add the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lakehouse.utils.spark import get_spark
from lakehouse.utils.storage import (
    bronze_partition_path,
    data_root,
    gold_table_path,
    silver_artists_path,
    silver_artworks_path,
    silver_failures_path,
)

LOGGER = logging.getLogger(__name__)

GOLD_TABLES = (
    "current_artworks",
    "current_artists",
    "price_history",
    "artist_statistics",
    "market_metrics",
)

# Wide columns make Spark `.show()` unreadable in a terminal.
DEFAULT_COLUMNS = {
    "bronze": ["url", "source", "crawl_date", "status_code", "content_length", "is_blocked"],
    "silver.artworks": [
        "entity_id",
        "source",
        "title",
        "artist_name",
        "artist_id",
        "category",
        "medium",
        "materials",
        "styles",
        "subject",
        "price",
        "currency",
        "availability",
        "artwork_year",
        "sku",
        "url",
    ],
    "silver.artists": [
        "entity_id",
        "source",
        "artist_name",
        "artist_id",
        "user_name",
        "first_name",
        "last_name",
        "country",
        "city",
        "joined_date",
        "artist_profile_url",
        "url",
    ],
    "gold.current_artworks": [
        "entity_id",
        "source",
        "title",
        "artist_name",
        "artist_id",
        "category",
        "medium",
        "materials",
        "styles",
        "subject",
        "price",
        "currency",
        "availability",
        "artwork_year",
        "sku",
        "url",
    ],
    "gold.current_artists": [
        "entity_id",
        "source",
        "artist_name",
        "artist_id",
        "user_name",
        "first_name",
        "last_name",
        "country",
        "city",
        "state",
        "joined_date",
        "artist_profile_url",
        "url",
    ],
    "gold.price_history": [
        "entity_id",
        "source",
        "crawl_timestamp",
        "price",
        "previous_price",
        "price_change",
        "percent_change",
    ],
    "gold.artist_statistics": [
        "artist_name",
        "source",
        "artwork_count",
        "average_price",
        "min_price",
        "max_price",
    ],
    "gold.market_metrics": [
        "source",
        "crawl_date",
        "total_artworks",
        "new_artworks",
        "price_changes",
        "average_price",
    ],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect lakehouse tables and print rows to the terminal."
    )
    parser.add_argument(
        "--table",
        choices=[
            "bronze",
            "silver.artworks",
            "silver.artists",
            "gold.current_artworks",
            "gold.current_artists",
            "gold.price_history",
            "gold.artist_statistics",
            "gold.market_metrics",
            "failures",
        ],
        help="Table to inspect. Omit to print a summary of all tables.",
    )
    parser.add_argument("--source", default="saatchi", choices=["saatchi", "artsper", "artsy"])
    parser.add_argument("--crawl-date", default=None, help="Bronze/failures partition date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to print")
    parser.add_argument(
        "--columns",
        default=None,
        help="Comma-separated columns. Default excludes raw_json/image_urls for readability.",
    )
    parser.add_argument(
        "--all-columns",
        action="store_true",
        help="Include every column (including raw_json / image_urls).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "vertical", "json", "csv"],
        default="vertical",
        help="Output format. Default: vertical (best for terminals).",
    )
    parser.add_argument("--truncate", type=int, default=80, help="Max cell width for table mode")
    parser.add_argument("--data-root", default=None, help="Lakehouse data root directory")
    parser.add_argument(
        "--sql",
        default=None,
        help="Optional Spark SQL to run against the selected Delta table",
    )
    return parser


def _resolve_root(data_root_arg: str | None) -> Path:
    return Path(data_root_arg).resolve() if data_root_arg else data_root()


def _table_path(table: str, root: Path, source: str, crawl_date: str | None) -> Path:
    if table == "bronze":
        if not crawl_date:
            raise ValueError("--crawl-date is required for bronze")
        return bronze_partition_path(source, crawl_date, root)
    if table == "silver.artworks":
        return silver_artworks_path(root)
    if table == "silver.artists":
        return silver_artists_path(root)
    if table == "gold.current_artworks":
        return gold_table_path("current_artworks", root)
    if table == "gold.current_artists":
        return gold_table_path("current_artists", root)
    if table == "gold.price_history":
        return gold_table_path("price_history", root)
    if table == "gold.artist_statistics":
        return gold_table_path("artist_statistics", root)
    if table == "gold.market_metrics":
        return gold_table_path("market_metrics", root)
    if table == "failures":
        if not crawl_date:
            raise ValueError("--crawl-date is required for failures")
        return silver_failures_path(source, crawl_date, root)
    raise ValueError(f"Unknown table: {table}")


def _load_dataframe(spark, table: str, path: Path):
    if table == "bronze":
        return spark.read.parquet(str(path))
    if table == "failures":
        manifest = path / "failures.jsonl"
        if not manifest.is_file():
            raise FileNotFoundError(f"Failures manifest not found: {manifest}")
        rows = []
        with manifest.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return spark.createDataFrame(rows)
    return spark.read.format("delta").load(str(path))


def _select_columns(df, table: str, columns: str | None, all_columns: bool):
    if all_columns:
        return df
    if columns:
        selected = [column.strip() for column in columns.split(",") if column.strip()]
        return df.select(*selected)
    defaults = DEFAULT_COLUMNS.get(table)
    if not defaults:
        return df
    available = [column for column in defaults if column in df.columns]
    return df.select(*available) if available else df


def _print_dataframe(df, *, limit: int, output_format: str, truncate: int) -> None:
    limited = df.limit(limit)
    if output_format == "table":
        limited.show(limit, truncate=truncate, vertical=False)
        return
    if output_format == "vertical":
        limited.show(limit, truncate=truncate, vertical=True)
        return
    if output_format == "json":
        rows = [row.asDict(recursive=True) for row in limited.collect()]
        print(json.dumps(rows, indent=2, default=str))
        return
    if output_format == "csv":
        # Print a simple CSV to stdout without writing temp files.
        pandas_df = limited.toPandas()
        print(pandas_df.to_csv(index=False))
        return
    raise ValueError(f"Unsupported format: {output_format}")


def _print_summary(spark, root: Path, source: str, crawl_date: str | None) -> None:
    print(f"data_root: {root}")
    print()

    if crawl_date:
        bronze_path = bronze_partition_path(source, crawl_date, root)
        if bronze_path.is_dir():
            count = _load_dataframe(spark, "bronze", bronze_path).count()
            print(f"bronze/{source}/{crawl_date}: {count} rows")
        else:
            print(f"bronze/{source}/{crawl_date}: missing")

    for name, loader_name, path_fn in (
        ("silver.artworks", "silver.artworks", silver_artworks_path),
        ("silver.artists", "silver.artists", silver_artists_path),
    ):
        path = path_fn(root)
        if path.exists():
            count = _load_dataframe(spark, loader_name, path).count()
            print(f"{name}: {count} rows")
        else:
            print(f"{name}: missing")

    for table_name in GOLD_TABLES:
        path = gold_table_path(table_name, root)
        label = f"gold.{table_name}"
        if path.exists():
            count = _load_dataframe(spark, f"gold.{table_name}", path).count()
            print(f"{label}: {count} rows")
        else:
            print(f"{label}: missing")

    if crawl_date:
        failures_path = silver_failures_path(source, crawl_date, root)
        manifest = failures_path / "failures.jsonl"
        if manifest.is_file():
            lines = sum(1 for _ in manifest.open("r", encoding="utf-8"))
            print(f"failures/{source}/{crawl_date}: {lines} rows")
        else:
            print(f"failures/{source}/{crawl_date}: missing")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    root = _resolve_root(args.data_root)

    spark = get_spark("inspect_data")
    try:
        if args.table is None:
            _print_summary(spark, root, args.source, args.crawl_date)
            return 0

        path = _table_path(args.table, root, args.source, args.crawl_date)
        if args.table != "failures" and not path.exists():
            LOGGER.error("Table path does not exist: %s", path)
            return 1

        df = _load_dataframe(spark, args.table, path)
        if args.sql:
            df.createOrReplaceTempView("lakehouse_table")
            df = spark.sql(args.sql)

        df = _select_columns(df, args.table, args.columns, args.all_columns)

        print(f"table: {args.table}")
        print(f"path:  {path}")
        print(f"rows:  {df.count()}")
        print(f"cols:  {', '.join(df.columns)}")
        print()
        _print_dataframe(
            df,
            limit=args.limit,
            output_format=args.format,
            truncate=args.truncate,
        )
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
