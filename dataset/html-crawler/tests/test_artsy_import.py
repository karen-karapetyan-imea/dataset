from __future__ import annotations

from pathlib import Path

from import_artsy_to_db import build_row


def test_build_artsy_artwork_row() -> None:
    record = {
        "entity_type": "artwork",
        "source_file": "abc.html",
        "url": "https://www.artsy.net/artwork/sample",
        "external_id": "sample",
        "title": "Sample",
        "artist_name": "Artist",
        "artist_external_id": "artist-slug",
        "image_urls": ["https://example.com/img.jpg"],
    }
    row = build_row(record, html_dir=Path("/data/artsy_data"))
    assert row["id"] == "sample"
    assert row["title"] == "Sample"
    assert row["html_path"] == "artsy_data/abc.html"


def test_build_artsy_artist_row() -> None:
    record = {
        "entity_type": "artist",
        "source_file": "def.html",
        "url": "https://www.artsy.net/artist/sample",
        "external_id": "sample",
        "name": "Sample Artist",
    }
    row = build_row(record, html_dir=Path("/data/artsy_data"))
    assert row["name"] == "Sample Artist"
    assert row["profile_url"] == "https://www.artsy.net/artist/sample"
