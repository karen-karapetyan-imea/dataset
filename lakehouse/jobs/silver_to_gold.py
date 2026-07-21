#!/usr/bin/env python3
"""Recompute Gold Delta tables from Silver."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# When running as `python lakehouse/jobs/silver_to_gold.py`, Python puts
# `lakehouse/jobs/` on `sys.path`, so the sibling `lakehouse/` package
# isn't importable unless we add the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyspark.sql import Window
from pyspark.sql import functions as F

from lakehouse.utils.spark import get_spark
from lakehouse.utils.storage import (
    data_root,
    ensure_lakehouse_paths,
    gold_table_path,
    silver_artists_path,
    silver_artworks_path,
)

LOGGER = logging.getLogger(__name__)

ARTIST_GOLD_COLUMNS = [
    "entity_id",
    "source",
    "entity_type",
    "url",
    "crawl_timestamp",
    "title",
    "artist_name",
    "artist_id",
    "artist_profile_url",
    "user_name",
    "first_name",
    "last_name",
    "biography",
    "education",
    "exhibitions",
    "country",
    "city",
    "state",
    "joined_date",
    "description",
    "image_url",
    "raw_json",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Silver to Gold transformations.")
    parser.add_argument("--data-root", default=None)
    return parser


def _ensure_columns(df, columns: list[str]):
    for column in columns:
        if column not in df.columns:
            df = df.withColumn(column, F.lit(None))
    return df.select(*columns)


def write_current_artists(spark, artworks, root: Path) -> None:
    artists_path = silver_artists_path(root)
    if artists_path.exists():
        artists = spark.read.format("delta").load(str(artists_path))
        artists = artists.filter(F.col("entity_type") == "artist")
        window = Window.partitionBy("entity_id", "source").orderBy(F.col("crawl_timestamp").desc())
        current_artists = (
            artists.withColumn("row_num", F.row_number().over(window))
            .filter(F.col("row_num") == 1)
            .drop("row_num")
        )
        current_artists = _ensure_columns(current_artists, ARTIST_GOLD_COLUMNS)
        LOGGER.info("Building gold/current_artists from silver/artists")
    else:
        # Bootstrap from artwork denormalized artist fields until artist pages are crawled.
        bootstrap = (
            artworks.filter(F.col("artist_id").isNotNull() | F.col("artist_profile_url").isNotNull())
            .withColumn(
                "entity_id",
                F.coalesce(F.col("artist_id"), F.col("artist_profile_url")),
            )
            .withColumn("entity_type", F.lit("artist"))
            .withColumn("url", F.col("artist_profile_url"))
            .withColumn("title", F.col("artist_name"))
            .withColumn("user_name", F.lit(None).cast("string"))
            .withColumn("first_name", F.lit(None).cast("string"))
            .withColumn("last_name", F.lit(None).cast("string"))
            .withColumn("biography", F.lit(None).cast("string"))
            .withColumn("education", F.lit(None).cast("string"))
            .withColumn("exhibitions", F.lit(None).cast("string"))
            .withColumn("country", F.lit(None).cast("string"))
            .withColumn("city", F.lit(None).cast("string"))
            .withColumn("state", F.lit(None).cast("string"))
            .withColumn("joined_date", F.lit(None).cast("string"))
            .withColumn("description", F.lit(None).cast("string"))
            .withColumn("image_url", F.lit(None).cast("string"))
            .withColumn("raw_json", F.lit(None).cast("string"))
        )
        window = Window.partitionBy("entity_id", "source").orderBy(F.col("crawl_timestamp").desc())
        current_artists = (
            bootstrap.withColumn("row_num", F.row_number().over(window))
            .filter(F.col("row_num") == 1)
            .drop("row_num")
        )
        current_artists = _ensure_columns(current_artists, ARTIST_GOLD_COLUMNS)
        LOGGER.info("Building gold/current_artists from silver/artworks bootstrap")

    current_artists.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
        str(gold_table_path("current_artists", root))
    )
    LOGGER.info("Wrote gold/current_artists")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    root = Path(args.data_root).resolve() if args.data_root else data_root()
    ensure_lakehouse_paths()

    artworks_path = silver_artworks_path(root)
    if not artworks_path.exists():
        LOGGER.error("Silver artworks table not found: %s", artworks_path)
        return 1

    spark = get_spark("silver_to_gold")
    artworks = spark.read.format("delta").load(str(artworks_path))

    current_window = Window.partitionBy("entity_id", "source").orderBy(F.col("crawl_timestamp").desc())
    current_artworks = (
        artworks.withColumn("row_num", F.row_number().over(current_window))
        .filter(F.col("row_num") == 1)
        .drop("row_num")
    )
    current_artworks.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
        str(gold_table_path("current_artworks", root))
    )
    LOGGER.info("Wrote gold/current_artworks")

    write_current_artists(spark, artworks, root)

    price_window = Window.partitionBy("entity_id", "source").orderBy("crawl_timestamp")
    price_history = (
        artworks.withColumn("previous_price", F.lag("price").over(price_window))
        .withColumn("price_change", F.col("price") - F.col("previous_price"))
        .withColumn(
            "percent_change",
            F.when(
                F.col("previous_price").isNotNull() & (F.col("previous_price") != 0),
                (F.col("price_change") / F.col("previous_price")) * 100,
            ),
        )
        .select(
            "entity_id",
            "source",
            "crawl_timestamp",
            "price",
            "previous_price",
            "price_change",
            "percent_change",
        )
    )
    price_history.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
        str(gold_table_path("price_history", root))
    )
    LOGGER.info("Wrote gold/price_history")

    artist_statistics = (
        current_artworks.filter(F.col("artist_name").isNotNull())
        .groupBy("artist_name", "source")
        .agg(
            F.count("*").alias("artwork_count"),
            F.avg("price").alias("average_price"),
            F.min("price").alias("min_price"),
            F.max("price").alias("max_price"),
        )
    )
    artist_statistics.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
        str(gold_table_path("artist_statistics", root))
    )
    LOGGER.info("Wrote gold/artist_statistics")

    first_seen = artworks.groupBy("entity_id", "source").agg(F.min("crawl_timestamp").alias("first_seen"))
    artworks_with_dates = artworks.withColumn("crawl_date", F.to_date("crawl_timestamp"))
    daily_counts = artworks_with_dates.groupBy("source", "crawl_date").agg(
        F.count("*").alias("total_artworks")
    )
    new_artworks = (
        artworks_with_dates.alias("a")
        .join(
            first_seen.alias("f"),
            (F.col("a.entity_id") == F.col("f.entity_id"))
            & (F.col("a.source") == F.col("f.source"))
            & (F.col("a.crawl_timestamp") == F.col("f.first_seen")),
            "inner",
        )
        .groupBy("a.source", "a.crawl_date")
        .agg(F.count("*").alias("new_artworks"))
    )
    price_changes = (
        price_history.filter(F.col("price_change").isNotNull() & (F.col("price_change") != 0))
        .withColumn("crawl_date", F.to_date("crawl_timestamp"))
        .groupBy("source", "crawl_date")
        .agg(F.count("*").alias("price_changes"))
    )
    avg_prices = artworks_with_dates.groupBy("source", "crawl_date").agg(
        F.avg("price").alias("average_price")
    )
    market_metrics = (
        daily_counts.join(new_artworks, ["source", "crawl_date"], "left")
        .join(price_changes, ["source", "crawl_date"], "left")
        .join(avg_prices, ["source", "crawl_date"], "left")
        .select(
            "source",
            "crawl_date",
            F.coalesce(F.col("total_artworks"), F.lit(0)).alias("total_artworks"),
            F.coalesce(F.col("new_artworks"), F.lit(0)).alias("new_artworks"),
            F.coalesce(F.col("price_changes"), F.lit(0)).alias("price_changes"),
            "average_price",
        )
    )
    market_metrics.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
        str(gold_table_path("market_metrics", root))
    )
    LOGGER.info("Wrote gold/market_metrics")

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
