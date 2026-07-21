"""Gold layer schema definitions."""

from __future__ import annotations

from pyspark.sql.types import (
    ArrayType,
    DateType,
    DecimalType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

CURRENT_ARTWORKS_SCHEMA = StructType(
    [
        StructField("entity_id", StringType(), False),
        StructField("source", StringType(), False),
        StructField("entity_type", StringType(), False),
        StructField("url", StringType(), True),
        StructField("crawl_timestamp", TimestampType(), False),
        StructField("title", StringType(), True),
        StructField("artist_name", StringType(), True),
        StructField("artist_id", StringType(), True),
        StructField("artist_profile_url", StringType(), True),
        StructField("user_name", StringType(), True),
        StructField("first_name", StringType(), True),
        StructField("last_name", StringType(), True),
        StructField("biography", StringType(), True),
        StructField("education", StringType(), True),
        StructField("exhibitions", StringType(), True),
        StructField("country", StringType(), True),
        StructField("city", StringType(), True),
        StructField("state", StringType(), True),
        StructField("joined_date", StringType(), True),
        StructField("category", StringType(), True),
        StructField("medium", StringType(), True),
        StructField("materials", ArrayType(StringType()), True),
        StructField("styles", ArrayType(StringType()), True),
        StructField("subject", StringType(), True),
        StructField("description", StringType(), True),
        StructField("price", DecimalType(18, 2), True),
        StructField("currency", StringType(), True),
        StructField("availability", StringType(), True),
        StructField("artwork_year", IntegerType(), True),
        StructField("image_url", StringType(), True),
        StructField("image_urls", ArrayType(StringType()), True),
        StructField("dimensions", StringType(), True),
        StructField("sku", StringType(), True),
        StructField("keywords", ArrayType(StringType()), True),
        StructField("raw_json", StringType(), True),
    ]
)

CURRENT_ARTISTS_SCHEMA = StructType(
    [
        StructField("entity_id", StringType(), False),
        StructField("source", StringType(), False),
        StructField("entity_type", StringType(), False),
        StructField("url", StringType(), True),
        StructField("crawl_timestamp", TimestampType(), True),
        StructField("title", StringType(), True),
        StructField("artist_name", StringType(), True),
        StructField("artist_id", StringType(), True),
        StructField("artist_profile_url", StringType(), True),
        StructField("user_name", StringType(), True),
        StructField("first_name", StringType(), True),
        StructField("last_name", StringType(), True),
        StructField("biography", StringType(), True),
        StructField("education", StringType(), True),
        StructField("exhibitions", StringType(), True),
        StructField("country", StringType(), True),
        StructField("city", StringType(), True),
        StructField("state", StringType(), True),
        StructField("joined_date", StringType(), True),
        StructField("description", StringType(), True),
        StructField("image_url", StringType(), True),
        StructField("raw_json", StringType(), True),
    ]
)

PRICE_HISTORY_SCHEMA = StructType(
    [
        StructField("entity_id", StringType(), False),
        StructField("source", StringType(), False),
        StructField("crawl_timestamp", TimestampType(), False),
        StructField("price", DecimalType(18, 2), True),
        StructField("previous_price", DecimalType(18, 2), True),
        StructField("price_change", DecimalType(18, 2), True),
        StructField("percent_change", DecimalType(10, 4), True),
    ]
)

ARTIST_STATISTICS_SCHEMA = StructType(
    [
        StructField("artist_name", StringType(), False),
        StructField("source", StringType(), False),
        StructField("artwork_count", LongType(), False),
        StructField("average_price", DecimalType(18, 2), True),
        StructField("min_price", DecimalType(18, 2), True),
        StructField("max_price", DecimalType(18, 2), True),
    ]
)

MARKET_METRICS_SCHEMA = StructType(
    [
        StructField("source", StringType(), False),
        StructField("crawl_date", DateType(), False),
        StructField("total_artworks", LongType(), False),
        StructField("new_artworks", LongType(), False),
        StructField("price_changes", LongType(), False),
        StructField("average_price", DecimalType(18, 2), True),
    ]
)
