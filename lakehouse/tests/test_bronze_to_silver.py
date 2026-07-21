"""Bronze to Silver transformation tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from lakehouse.schemas.bronze import BRONZE_ARROW_SCHEMA
from lakehouse.utils.bronze_ingest import write_bronze_batch
from lakehouse.utils.compression import compress_html
from lakehouse.utils.parser_adapter import normalize_to_silver, parse_html_record

HTML_CRAWLER_FIXTURES = Path(__file__).resolve().parents[2] / "html-crawler" / "tests" / "fixtures"


def _write_fixture_bronze(tmp_data_root: Path, source: str, crawl_date: str, fixture_name: str, url: str) -> None:
    html = (HTML_CRAWLER_FIXTURES / fixture_name).read_bytes()
    record = {
        "url": url,
        "url_sha1": "fixture",
        "source": source,
        "crawl_timestamp": datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        "status_code": 200,
        "response_time_ms": 100,
        "headers_json": None,
        "content_type": "text/html",
        "content_length": len(html),
        "html": compress_html(html),
        "proxy_id": None,
        "crawl_job_id": f"{source}-{crawl_date}",
        "error_message": "",
        "is_blocked": False,
    }
    write_bronze_batch([record], source=source, crawl_date=crawl_date, data_root=tmp_data_root)


def test_parse_saatchi_artwork_fixture() -> None:
    html = (HTML_CRAWLER_FIXTURES / "saatchi_artwork_sample.html").read_bytes()
    url = "https://www.saatchiart.com/art/Painting-Gold-abstract-painting-GB416-FEATURED/735695/9336593/view"
    crawl_ts = datetime(2026, 7, 20, tzinfo=timezone.utc)
    silver, failure = parse_html_record(
        source="saatchi",
        url=url,
        html_bytes=html,
        crawl_timestamp=crawl_ts,
    )
    assert failure is None
    assert silver is not None
    assert silver["entity_id"] == "9336593"
    assert silver["title"] == "Gold abstract painting GB416 (FEATURED)"
    assert silver["artist_name"] == "Radek Smach"
    assert silver["price"] == Decimal("1999.00")
    assert silver["artist_id"] == "735695"
    assert silver["category"] == "Painting"
    assert silver["artwork_year"] == 2024
    assert "materials" in silver
    assert "styles" in silver
    assert "availability" in silver
    assert "sku" in silver


def test_parse_artsper_artwork_fixture() -> None:
    html = (HTML_CRAWLER_FIXTURES / "artsper_artwork_sample.html").read_bytes()
    url = "https://www.artsper.com/us/contemporary-artworks/painting/2361374/sample-title"
    crawl_ts = datetime(2026, 7, 20, tzinfo=timezone.utc)
    silver, failure = parse_html_record(
        source="artsper",
        url=url,
        html_bytes=html,
        crawl_timestamp=crawl_ts,
    )
    assert failure is None
    assert silver is not None
    assert silver["entity_id"] == "2361374"
    assert silver["title"]


def test_bronze_parquet_roundtrip(tmp_data_root: Path) -> None:
    url = "https://www.saatchiart.com/art/Painting-Gold-abstract-painting-GB416-FEATURED/735695/9336593/view"
    _write_fixture_bronze(tmp_data_root, "saatchi", "2026-07-20", "saatchi_artwork_sample.html", url)

    bronze_path = tmp_data_root / "bronze" / "source=saatchi" / "crawl_date=2026-07-20"
    table = pq.read_table(bronze_path / "part-00000.parquet")
    assert table.num_rows == 1
    assert table.schema.equals(BRONZE_ARROW_SCHEMA)


def test_normalize_dimensions_dict() -> None:
    record = {
        "title": "Sample",
        "url": "https://example.com",
        "artist": "Artist",
        "artwork_id": "99",
        "price": "10",
        "currency": "USD",
        "dimensions": {"height": "10", "width": "20"},
        "image_urls": [],
    }
    silver = normalize_to_silver(
        record,
        source="saatchi",
        entity_type="artwork",
        url=record["url"],
        crawl_timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    assert silver["dimensions"] == "height=10, width=20"
    payload = json.loads(silver["raw_json"])
    assert payload["title"] == "Sample"


def test_normalize_artist_profile_fields() -> None:
    record = {
        "entity_type": "artist",
        "url": "https://www.saatchiart.com/micoschholland",
        "canonical_url": "https://www.saatchiart.com/micoschholland",
        "artist_external_id": "57091",
        "name": "Micosch Holland",
        "first_name": "Micosch",
        "last_name": "Holland",
        "user_name": "micoschholland",
        "biography": "Artist bio",
        "education": "Academy",
        "exhibitions": "Show 2024",
        "country": "Germany",
        "city": "Berlin",
        "state": None,
        "joined_date": "2015-01-01",
        "profile_image_url": "https://example.com/avatar.jpg",
    }
    silver = normalize_to_silver(
        record,
        source="saatchi",
        entity_type="artist",
        url=record["url"],
        crawl_timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    assert silver["entity_id"] == "57091"
    assert silver["artist_id"] == "57091"
    assert silver["artist_name"] == "Micosch Holland"
    assert silver["title"] == "Micosch Holland"
    assert silver["artist_profile_url"] == "https://www.saatchiart.com/micoschholland"
    assert silver["user_name"] == "micoschholland"
    assert silver["first_name"] == "Micosch"
    assert silver["last_name"] == "Holland"
    assert silver["biography"] == "Artist bio"
    assert silver["description"] == "Artist bio"
    assert silver["education"] == "Academy"
    assert silver["exhibitions"] == "Show 2024"
    assert silver["country"] == "Germany"
    assert silver["city"] == "Berlin"
    assert silver["joined_date"] == "2015-01-01"
    assert silver["image_url"] == "https://example.com/avatar.jpg"


def test_parse_saatchi_artist_fixture() -> None:
    html = (HTML_CRAWLER_FIXTURES / "saatchi_artist_sample.html").read_bytes()
    url = "https://www.saatchiart.com/account/profile/735695"
    crawl_ts = datetime(2026, 7, 20, tzinfo=timezone.utc)
    silver, failure = parse_html_record(
        source="saatchi",
        url=url,
        html_bytes=html,
        crawl_timestamp=crawl_ts,
    )
    assert failure is None
    assert silver is not None
    assert silver["entity_type"] == "artist"
    assert silver["entity_id"]
    assert silver["artist_name"]
    assert silver["artist_profile_url"]
