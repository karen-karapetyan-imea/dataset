from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from etl.versioning import VersionOutcome, apply_versioned_upsert, tracked_fields_for


def test_apply_versioned_upsert_skips_unchanged() -> None:
    fields = tracked_fields_for("saatchi", "artwork")
    row = {
        "id": 1,
        "title": "Art",
        "price": Decimal("100"),
        "currency": "USD",
        "artist_id": None,
        "artist_name": None,
        "artist_profile_url": None,
        "category": None,
        "medium": None,
        "materials": None,
        "styles": None,
        "subject": None,
        "description": None,
        "availability": None,
        "artwork_year": None,
        "image_url": None,
        "image_urls": None,
        "dimensions": None,
        "sku": None,
        "keywords": None,
        "canonical_url": None,
        "html_path": "saatchi_data/a.html",
        "raw_json": {},
    }
    known = {
        "1": {
            field: (str(row[field]) if field == "price" else row.get(field))
            for field in fields
        }
    }
    known["1"]["price"] = "100"
    cursor = MagicMock()
    outcome = apply_versioned_upsert(
        cursor,
        marketplace="saatchi",
        entity_type="artwork",
        row=row,
        upsert_sql="UPSERT",
        tracked_fields=fields,
        known_snapshots=known,
    )
    assert outcome == VersionOutcome.SKIPPED
    cursor.execute.assert_not_called()


def test_apply_versioned_upsert_versions_on_price_change() -> None:
    fields = tracked_fields_for("saatchi", "artwork")
    row = {
        "id": 2,
        "title": "Art",
        "price": Decimal("90"),
        "currency": "USD",
        "artist_id": None,
        "artist_name": None,
        "artist_profile_url": None,
        "category": None,
        "medium": None,
        "materials": None,
        "styles": None,
        "subject": None,
        "description": None,
        "availability": None,
        "artwork_year": None,
        "image_url": None,
        "image_urls": None,
        "dimensions": None,
        "sku": None,
        "keywords": None,
        "canonical_url": None,
        "html_path": "saatchi_data/a.html",
        "raw_json": {},
    }
    known = {
        "2": {field: None for field in fields},
    }
    known["2"]["price"] = "100"
    known["2"]["title"] = "Art"
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, (3,)]
    outcome = apply_versioned_upsert(
        cursor,
        marketplace="saatchi",
        entity_type="artwork",
        row=row,
        upsert_sql="UPSERT",
        tracked_fields=fields,
        known_snapshots=known,
    )
    assert outcome == VersionOutcome.VERSIONED
    assert cursor.execute.call_count == 3
