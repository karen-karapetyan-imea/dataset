"""Bronze layer schema definitions."""

from __future__ import annotations

import pyarrow as pa
from pyspark.sql.types import (
    BinaryType,
    BooleanType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

BRONZE_SPARK_SCHEMA = StructType(
    [
        StructField("url", StringType(), False),
        StructField("url_sha1", StringType(), False),
        StructField("source", StringType(), False),
        StructField("crawl_timestamp", TimestampType(), False),
        StructField("status_code", IntegerType(), False),
        StructField("response_time_ms", LongType(), True),
        StructField("headers_json", StringType(), True),
        StructField("content_type", StringType(), True),
        StructField("content_length", LongType(), True),
        StructField("html", BinaryType(), True),
        StructField("proxy_id", StringType(), True),
        StructField("crawl_job_id", StringType(), True),
        StructField("error_message", StringType(), True),
        StructField("is_blocked", BooleanType(), False),
    ]
)

BRONZE_ARROW_SCHEMA = pa.schema(
    [
        ("url", pa.string()),
        ("url_sha1", pa.string()),
        ("source", pa.string()),
        ("crawl_timestamp", pa.timestamp("us", tz="UTC")),
        ("status_code", pa.int32()),
        ("response_time_ms", pa.int64()),
        ("headers_json", pa.string()),
        ("content_type", pa.string()),
        ("content_length", pa.int64()),
        ("html", pa.binary()),
        ("proxy_id", pa.string()),
        ("crawl_job_id", pa.string()),
        ("error_message", pa.string()),
        ("is_blocked", pa.bool_()),
    ]
)
