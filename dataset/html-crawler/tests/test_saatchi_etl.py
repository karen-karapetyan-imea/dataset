from __future__ import annotations

from pathlib import Path

import pytest

from etl.saatchi import (
    extract_artist_record,
    extract_artwork_record,
    route_saatchi_page,
)
from etl.urls import saatchi_artist_from_url, saatchi_artwork_from_url

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ARTWORK_HTML = FIXTURES / "saatchi_artwork_sample.html"
ARTIST_HTML = FIXTURES / "saatchi_artist_sample.html"


def test_saatchi_artwork_url() -> None:
    url = (
        "https://www.saatchiart.com/art/Painting-Gold-abstract-painting-GB416-FEATURED/"
        "735695/9336593/view"
    )
    assert saatchi_artwork_from_url(url) == ("735695", "9336593")


def test_saatchi_artist_url() -> None:
    url = "https://www.saatchiart.com/account/profile/735695"
    assert saatchi_artist_from_url(url) == "735695"


def test_route_saatchi_page() -> None:
    artwork_html = ARTWORK_HTML.read_text(encoding="utf-8")
    artist_html = ARTIST_HTML.read_text(encoding="utf-8")
    assert route_saatchi_page(artwork_html) == "artwork"
    assert route_saatchi_page(artist_html) == "artist"


def test_extract_artwork_record() -> None:
    record, missing = extract_artwork_record(ARTWORK_HTML)
    assert not missing
    assert record["artwork_id"] == "9336593"
    assert record["artist_external_id"] == "735695"
    assert record["title"] == "Gold abstract painting GB416 (FEATURED)"
    assert record["medium"] == "Acrylic"
    assert record["price"] == "1999"
    assert record["currency"] == "USD"
    assert len(record["image_urls"]) >= 1
    assert record["artist"] == "Radek Smach"


def test_extract_artist_record() -> None:
    record, missing = extract_artist_record(ARTIST_HTML)
    assert not missing
    assert record["artist_external_id"] == "735695"
    assert record["name"] == "Radek Smach"
    assert record["user_name"] == "radeksmach"
    assert record["url"] == "https://www.saatchiart.com/radeksmach"
    assert "abstract expressionism" in (record.get("biography") or "").lower()
    assert record["profile_image_url"]


def test_extract_artwork_fallback_without_next_data() -> None:
    html = ARTWORK_HTML.read_text(encoding="utf-8")
    stripped = html.replace('id="__NEXT_DATA__"', 'id="__NEXT_DATA_REMOVED__"')
    path = FIXTURES / "_tmp_artwork_fallback.html"
    path.write_text(stripped, encoding="utf-8")
    try:
        record, missing = extract_artwork_record(path)
        assert not missing
        assert record["title"]
        assert record["url"]
    finally:
        path.unlink(missing_ok=True)


def test_extract_artist_fallback_without_next_data() -> None:
    html = ARTIST_HTML.read_text(encoding="utf-8")
    stripped = html.replace('id="__NEXT_DATA__"', 'id="__NEXT_DATA_REMOVED__"')
    path = FIXTURES / "_tmp_artist_fallback.html"
    path.write_text(stripped, encoding="utf-8")
    try:
        record, missing = extract_artist_record(path)
        assert record["name"]
        assert record["artist_external_id"] == "735695"
        assert "url" in record
    finally:
        path.unlink(missing_ok=True)
