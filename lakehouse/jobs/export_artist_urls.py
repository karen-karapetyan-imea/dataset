#!/usr/bin/env python3
"""Export unique artist profile URLs from lakehouse artworks for crawling."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyspark.sql import functions as F

from lakehouse.utils.spark import get_spark
from lakehouse.utils.storage import (
    data_root,
    gold_table_path,
    html_crawler_root,
    silver_artworks_path,
)

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export unique Saatchi artist profile URLs for the HTML crawler."
    )
    parser.add_argument("--data-root", default=None)
    parser.add_argument(
        "--output",
        default=None,
        help="Output URL list path (default: html-crawler/state/urls_saatchi_artists.txt)",
    )
    parser.add_argument(
        "--prefer-gold",
        action="store_true",
        help="Read gold/current_artworks instead of silver/artworks when available",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    root = Path(args.data_root).resolve() if args.data_root else data_root()

    output = (
        Path(args.output).resolve()
        if args.output
        else html_crawler_root() / "state" / "urls_saatchi_artists.txt"
    )

    silver_path = silver_artworks_path(root)
    gold_path = gold_table_path("current_artworks", root)

    if args.prefer_gold and gold_path.exists():
        table_path = gold_path
        label = "gold/current_artworks"
    elif silver_path.exists():
        table_path = silver_path
        label = "silver/artworks"
    elif gold_path.exists():
        table_path = gold_path
        label = "gold/current_artworks"
    else:
        LOGGER.error("No artworks table found under %s", root)
        return 1

    spark = get_spark("export_artist_urls")
    try:
        df = spark.read.format("delta").load(str(table_path))
        urls_df = (
            df.select(
                F.coalesce(
                    F.col("artist_profile_url"),
                    F.concat(
                        F.lit("https://www.saatchiart.com/account/profile/"),
                        F.col("artist_id"),
                    ),
                ).alias("url")
            )
            .filter(F.col("url").isNotNull() & (F.length(F.trim(F.col("url"))) > 0))
            .distinct()
            .orderBy("url")
        )
        urls = [row.url for row in urls_df.collect()]
    finally:
        spark.stop()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for url in urls:
            handle.write(f"{url}\n")

    LOGGER.info("Exported %s artist URLs from %s to %s", len(urls), label, output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
