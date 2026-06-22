from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from import_to_legacy_db import build_artist_row, build_artwork_row, storage_path


def test_storage_path() -> None:
    assert storage_path(Path("/tmp/artsper_data"), "abc.html") == "artsper_data/abc.html"


def test_build_artist_row() -> None:
    row = build_artist_row(
        "128876",
        {
            "name": "Nathalie Cubero",
            "url": "https://www.artsper.com/us/contemporary-artists/france/128876/nathalie-cubero",
            "image_url": "https://example.com/img.jpg",
            "about_text": "Bio",
        },
        html_dir=Path("artsper_data"),
        filename="deadbeef.html",
    )
    assert row["id"] == 128876
    assert row["artist_name"] == "Nathalie Cubero"
    assert row["path"] == "artsper_data/deadbeef.html"


def test_build_artwork_row() -> None:
    row = build_artwork_row(
        "2361374",
        {
            "title": "Un petit bout",
            "year": "2024",
            "artist": "Artist Name",
            "artform": "Painting",
            "medium": "Oil",
            "price": "1200",
            "currency": "EUR",
            "image_urls": ["https://example.com/cover.jpg"],
            "url": "https://www.artsper.com/us/contemporary-artworks/painting/2361374/x",
            "artist_url": "https://www.artsper.com/us/contemporary-artists/france/1/name",
        },
        html_dir=Path("artsper_data"),
        filename="cafebabe.html",
    )
    assert row["id"] == 2361374
    assert row["artwork_year"] == 2024
    assert row["price"] == Decimal("1200")
    assert row["artist_slug"].endswith("/name")
