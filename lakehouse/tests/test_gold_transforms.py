"""Gold layer transformation tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pyspark.sql import Row
from pyspark.sql import Window
from pyspark.sql import functions as F


def test_current_artworks_window(spark) -> None:
    rows = [
        Row(
            entity_id="1",
            source="saatchi",
            entity_type="artwork",
            url="u1",
            crawl_timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc),
            title="A",
            artist_name="Artist",
            artist_id="10",
            artist_profile_url=None,
            category="Painting",
            medium="Oil",
            materials=["Canvas"],
            styles=["Abstract"],
            subject=None,
            description=None,
            price=Decimal("100.00"),
            currency="USD",
            availability="avail",
            artwork_year=2020,
            image_url="img1",
            image_urls=["img1"],
            dimensions=None,
            sku=None,
            keywords=[],
            raw_json="{}",
        ),
        Row(
            entity_id="1",
            source="saatchi",
            entity_type="artwork",
            url="u1",
            crawl_timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc),
            title="A2",
            artist_name="Artist",
            artist_id="10",
            artist_profile_url=None,
            category="Painting",
            medium="Oil",
            materials=["Canvas"],
            styles=["Abstract"],
            subject=None,
            description=None,
            price=Decimal("120.00"),
            currency="USD",
            availability="avail",
            artwork_year=2020,
            image_url="img2",
            image_urls=["img2"],
            dimensions=None,
            sku=None,
            keywords=[],
            raw_json="{}",
        ),
    ]
    df = spark.createDataFrame(rows)
    window = Window.partitionBy("entity_id", "source").orderBy(F.col("crawl_timestamp").desc())
    current = (
        df.withColumn("row_num", F.row_number().over(window))
        .filter(F.col("row_num") == 1)
        .drop("row_num")
    )
    result = current.collect()[0]
    assert result.title == "A2"
    assert result.price == Decimal("120.00")


def test_price_history_lag(spark) -> None:
    rows = [
        Row(
            entity_id="1",
            source="saatchi",
            crawl_timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc),
            price=Decimal("100.00"),
        ),
        Row(
            entity_id="1",
            source="saatchi",
            crawl_timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc),
            price=Decimal("120.00"),
        ),
    ]
    df = spark.createDataFrame(rows)
    window = Window.partitionBy("entity_id", "source").orderBy("crawl_timestamp")
    history = (
        df.withColumn("previous_price", F.lag("price").over(window))
        .withColumn("price_change", F.col("price") - F.col("previous_price"))
        .withColumn(
            "percent_change",
            F.when(
                F.col("previous_price").isNotNull() & (F.col("previous_price") != 0),
                (F.col("price_change") / F.col("previous_price")) * 100,
            ),
        )
    )
    latest = history.orderBy(F.col("crawl_timestamp").desc()).collect()[0]
    assert latest.previous_price == Decimal("100.00")
    assert latest.price_change == Decimal("20.00")
    assert float(latest.percent_change) == 20.0
