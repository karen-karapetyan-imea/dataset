"""Shared helpers for recording entity change history.

The importers compare a subset of tracked fields and write one history row per
changed field (and one `created` row on first insert).
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

try:
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover
    Jsonb = None


TRACKED_FIELDS: dict[tuple[str, str], list[str]] = {
    # Saatchi Art
    ("saatchi", "artwork"): [
        "price",
        "currency",
        "availability",
        "title",
        "category",
        "medium",
        "image_url",
        "artist_name",
        "description",
    ],
    ("saatchi", "artist"): [
        "artist_name",
        "biography",
        "profile_image_url",
        "country",
        "city",
        "state",
    ],
    # Artsper legacy tables
    ("artsper", "artwork"): [
        "price",
        "currency",
        "artwork_title",
        "artwork_year",
        "category",
        "medium",
        "artwork_cover_url",
        "artist_name",
    ],
    ("artsper", "artist"): [
        "artist_name",
        "biography",
        "profile_image_url",
    ],
    # Placeholder for future "artsy" importer.
    ("artsy", "artwork"): [
        "price",
        "currency",
        "availability",
        "title",
        "category",
        "medium",
        "image_url",
    ],
    ("artsy", "artist"): [
        "artist_name",
        "biography",
        "profile_image_url",
    ],
}


def _normalize_decimal(value: Decimal) -> Decimal:
    # History comparisons should not trigger on numeric scale differences
    # like `1200` vs `1200.00`.
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def serialize_value(value: Any) -> str | None:
    """Convert a DB/Python value into a stable string for diff + storage."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(_normalize_decimal(value))
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=True)
    return str(value)


def diff_tracked_fields(
    old_row: dict[str, Any] | None,
    new_row: dict[str, Any],
    fields: Iterable[str],
) -> list[tuple[str, str | None, str | None]]:
    changes: list[tuple[str, str | None, str | None]] = []
    for field in fields:
        old_val = old_row.get(field) if old_row is not None else None
        new_val = new_row.get(field)
        old_ser = serialize_value(old_val)
        new_ser = serialize_value(new_val)
        if old_ser != new_ser:
            changes.append((field, old_ser, new_ser))
    return changes


def activity_code_for_field(field: str) -> str:
    field_to_code = {
        "price": "price_changed",
        "currency": "currency_changed",
        "availability": "availability_changed",
        "title": "title_changed",
        "artwork_title": "title_changed",
        "category": "category_changed",
        "medium": "medium_changed",
        "image_url": "image_changed",
        "artwork_cover_url": "image_changed",
        "artist_name": "artist_name_changed",
        "biography": "biography_changed",
        "profile_image_url": "profile_image_changed",
        "country": "country_changed",
        "city": "city_changed",
        "state": "state_changed",
        "description": "description_changed",
        "artwork_year": "artwork_year_changed",
        "year": "year_changed",
    }
    return field_to_code.get(field, f"{field}_changed")


def _label_from_code(code: str) -> str:
    return code.replace("_", " ").strip().title()


def _maybe_jsonb(value: Any) -> Any:
    if value is None:
        return None
    if Jsonb is None:
        return value
    return Jsonb(value)


def ensure_activity_type_id(cursor: Any, code: str, label: str | None = None) -> int:
    """Get an activity type id, inserting the activity code if missing."""
    cursor.execute(
        """
        INSERT INTO public.activity_types (code, label)
        VALUES (%(code)s, %(label)s)
        ON CONFLICT (code) DO UPDATE SET code = EXCLUDED.code
        RETURNING id
        """,
        {"code": code, "label": label or _label_from_code(code)},
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"activity_types insert failed code={code!r}")
    return int(row[0])


def record_history_event(
    cursor: Any,
    *,
    source: str,
    entity_type: str,
    entity_id: int,
    activity_code: str,
    field_name: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    activity_type_id = ensure_activity_type_id(cursor, activity_code)
    cursor.execute(
        """
        INSERT INTO public.entity_history (
          source, entity_type, entity_id,
          activity_type_id, field_name, old_value, new_value,
          metadata
        ) VALUES (
          %(source)s, %(entity_type)s, %(entity_id)s,
          %(activity_type_id)s, %(field_name)s, %(old_value)s, %(new_value)s,
          %(metadata)s
        )
        """,
        {
            "source": source,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "activity_type_id": activity_type_id,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "metadata": _maybe_jsonb(metadata) if metadata is not None else None,
        },
    )


def upsert_with_history(
    cursor: Any,
    *,
    source: str,
    entity_type: str,
    entity_id: int,
    tracked_fields: list[str],
    select_sql: str,
    upsert_sql: str,
    row: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Upsert a row and record entity_history changes (if any).

    Returns:
      True if the upsert inserted a new row, False if it updated an existing row.
    """
    cursor.execute(select_sql, (entity_id,))
    old_tuple = cursor.fetchone()
    old_row = dict(zip(tracked_fields, old_tuple)) if old_tuple else None

    cursor.execute(upsert_sql, row)
    result = cursor.fetchone()
    inserted = bool(result[0]) if result else False

    if inserted:
        record_history_event(
            cursor,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            activity_code="created",
            metadata=metadata,
        )
        return True

    if old_row is None:
        # Shouldn't happen unless the SELECT and UPSERT disagree.
        return False

    changes = diff_tracked_fields(old_row, row, tracked_fields)
    for field_name, old_value, new_value in changes:
        if old_value == new_value:
            continue
        record_history_event(
            cursor,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            activity_code=activity_code_for_field(field_name),
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata,
        )
    return False

