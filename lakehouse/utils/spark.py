"""Spark session helpers with Delta Lake configuration."""

from __future__ import annotations

import os
from pathlib import Path

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from lakehouse.utils.storage import data_root


def configure_delta(builder: SparkSession.Builder) -> SparkSession.Builder:
    builder = builder.config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    builder = builder.config(
        "spark.sql.catalog.spark_catalog",
        "org.apache.spark.sql.delta.catalog.DeltaCatalog",
    )
    return configure_spark_with_delta_pip(builder)


def get_spark(app_name: str = "lakehouse") -> SparkSession:
    warehouse = Path(
        os.environ.get("SPARK_WAREHOUSE_DIR", str(data_root() / "spark-warehouse"))
    )
    warehouse.mkdir(parents=True, exist_ok=True)

    builder = (
        SparkSession.builder.appName(app_name)
        .master(os.environ.get("SPARK_MASTER", "local[*]"))
        .config("spark.sql.warehouse.dir", str(warehouse))
        .config("spark.sql.shuffle.partitions", os.environ.get("SPARK_SHUFFLE_PARTITIONS", "200"))
        .config("spark.driver.memory", os.environ.get("SPARK_DRIVER_MEMORY", "4g"))
        .config("spark.executor.memory", os.environ.get("SPARK_EXECUTOR_MEMORY", "4g"))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.databricks.delta.schema.autoMerge.enabled", "true")
    )

    spark = configure_delta(builder).getOrCreate()
    spark.sparkContext.setLogLevel(os.environ.get("SPARK_LOG_LEVEL", "WARN"))
    return spark
