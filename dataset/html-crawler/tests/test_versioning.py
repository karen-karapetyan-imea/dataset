from __future__ import annotations

from decimal import Decimal

from etl.versioning import (
    diff_snapshots,
    normalize_value,
    snapshot_from_row,
    tracked_fields_for,
)


def test_normalize_decimal() -> None:
    assert normalize_value(Decimal("1999.00")) == "1999.00"


def test_diff_snapshots_detects_price_change() -> None:
    fields = tracked_fields_for("saatchi", "artwork")
    old = snapshot_from_row({"price": Decimal("2000"), "currency": "USD", "title": "A"}, fields)
    new = snapshot_from_row({"price": Decimal("1800"), "currency": "USD", "title": "A"}, fields)
    changed = diff_snapshots(old, new, fields)
    assert "price" in changed
    assert "currency" not in changed
    assert "title" not in changed


def test_diff_snapshots_no_change() -> None:
    fields = tracked_fields_for("artsper", "artwork")
    row = {
        "artwork_title": "Sunset",
        "price": Decimal("1200"),
        "currency": "EUR",
        "artist_name": "Jane",
        "category": "Painting",
        "medium": "Oil",
        "artwork_year": 2020,
        "artwork_cover_url": "https://example.com/a.jpg",
        "artist_slug": "https://artsper.com/a",
        "path": "artsper_data/x.html",
    }
    snapshot = snapshot_from_row(row, fields)
    assert diff_snapshots(snapshot, snapshot, fields) == []


def test_tracked_fields_cover_artsy_entities() -> None:
    for entity in ("artist", "artwork", "partner", "show", "fair"):
        fields = tracked_fields_for("artsy", entity)
        assert fields
        assert "id" not in fields
