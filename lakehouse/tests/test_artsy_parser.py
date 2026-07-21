"""Tests for Artsy parser."""

from __future__ import annotations

from pathlib import Path

from lakehouse.parsers.artsy import extract_artwork_record, extract_artist_record

FIXTURES = Path(__file__).parent / "fixtures"


def test_artsy_artwork_extract() -> None:
    path = FIXTURES / "artsy_artwork_sample.html"
    record, missing = extract_artwork_record(
        path,
        "https://www.artsy.net/artwork/william-michael-harnett-the-old-violin",
    )
    assert not missing
    assert record["title"] == "The Old Violin"
    assert record["artist"] == "William Michael Harnett"
    assert record["price"] == "12500.00"
    assert record["currency"] == "USD"
    assert record["artwork_slug"] == "william-michael-harnett-the-old-violin"


def test_artsy_artist_extract() -> None:
    path = FIXTURES / "artsy_artist_sample.html"
    record, missing = extract_artist_record(path, "https://www.artsy.net/artist/pablo-picasso")
    assert not missing
    assert record["name"] == "Pablo Picasso"
    assert record["artist_slug"] == "pablo-picasso"
