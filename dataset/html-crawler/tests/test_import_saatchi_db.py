from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from import_saatchi_to_db import build_artist_row, build_artwork_row

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_build_artist_row() -> None:
    record = {
        "entity_type": "artist",
        "source_file": "abc.html",
        "url": "https://www.saatchiart.com/radeksmach",
        "artist_external_id": "735695",
        "name": "Radek Smach",
        "first_name": "Radek",
        "last_name": "Smach",
        "user_name": "radeksmach",
        "profile_image_url": "https://example.com/avatar.jpg",
        "biography": "About text",
        "education": "School",
        "exhibitions": "Show",
        "country": "Czech Republic",
        "city": "Opava",
        "state": None,
        "canonical_url": "https://www.saatchiart.com/account/profile/735695",
        "joined_date": "2015-01-01",
    }
    row = build_artist_row(record, html_dir=Path("/data/saatchi_html"))
    assert row["id"] == 735695
    assert row["artist_name"] == "Radek Smach"
    assert row["html_path"] == "saatchi_html/abc.html"
    assert row["profile_url"] == "https://www.saatchiart.com/radeksmach"


def test_build_artwork_row() -> None:
    record = {
        "entity_type": "artwork",
        "source_file": "def.html",
        "url": "https://www.saatchiart.com/art/Painting-Test/735695/9336593/view",
        "artwork_id": "9336593",
        "artist_external_id": "735695",
        "title": "Gold abstract painting GB416 (FEATURED)",
        "artist": "Radek Smach",
        "artist_url": "https://www.saatchiart.com/radeksmach",
        "artform": "Painting",
        "medium": "Acrylic",
        "materials": ["Canvas"],
        "styles": ["Abstract"],
        "subject": "Abstract",
        "description": "Desc",
        "price": "1999",
        "currency": "USD",
        "availability": "avail",
        "year": None,
        "image_urls": ["https://images.saatchiart.com/main.jpg"],
        "dimensions": {"height": 100, "width": 80, "depth": 2},
        "sku": "P1-U735695-A9336593-T1",
        "keywords": ["abstract"],
    }
    row = build_artwork_row(record, html_dir=Path("/data/saatchi_html"), artist_id_fk=735695)
    assert row["id"] == 9336593
    assert row["artist_id"] == 735695
    assert row["price"] == Decimal("1999")
    assert row["image_url"] == "https://images.saatchiart.com/main.jpg"
    assert row["html_path"] == "saatchi_html/def.html"
