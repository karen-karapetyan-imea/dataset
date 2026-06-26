"""Entity version history for marketplace incremental imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

try:
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover
    Jsonb = None  # type: ignore[misc, assignment]

VERSION_TRACKED_FIELDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("saatchi", "artist"): (
        "user_name",
        "artist_name",
        "first_name",
        "last_name",
        "profile_image_url",
        "biography",
        "education",
        "exhibitions",
        "country",
        "city",
        "state",
        "profile_url",
        "canonical_url",
        "joined_date",
    ),
    ("saatchi", "artwork"): (
        "artist_id",
        "title",
        "artist_name",
        "artist_profile_url",
        "category",
        "medium",
        "materials",
        "styles",
        "subject",
        "description",
        "price",
        "currency",
        "availability",
        "artwork_year",
        "image_url",
        "image_urls",
        "dimensions",
        "sku",
        "keywords",
        "canonical_url",
    ),
    ("artsper", "artist"): (
        "artist_name",
        "profile_image_url",
        "biography",
        "artist_slug",
        "path",
    ),
    ("artsper", "artwork"): (
        "artwork_title",
        "artwork_year",
        "artist_name",
        "category",
        "medium",
        "price",
        "currency",
        "artwork_cover_url",
        "artist_slug",
        "path",
    ),
    ("artsy", "artist"): (
        "name",
        "biography",
        "image_url",
        "profile_url",
        "canonical_url",
    ),
    ("artsy", "artwork"): (
        "title",
        "artist_name",
        "artist_external_id",
        "description",
        "medium",
        "year",
        "price",
        "currency",
        "image_url",
        "image_urls",
        "canonical_url",
    ),
    ("artsy", "partner"): (
        "name",
        "description",
        "image_url",
        "profile_url",
        "canonical_url",
    ),
    ("artsy", "show"): (
        "name",
        "description",
        "start_date",
        "end_date",
        "canonical_url",
    ),
    ("artsy", "fair"): (
        "name",
        "description",
        "start_date",
        "end_date",
        "canonical_url",
    ),
}

INSERT_VERSION_SQL = """
INSERT INTO public.marketplace_entity_versions (
  marketplace, entity_type, entity_id, version_no,
  previous_snapshot, current_snapshot, changed_fields, sync_source
) VALUES (
  %(marketplace)s, %(entity_type)s, %(entity_id)s, %(version_no)s,
  %(previous_snapshot)s, %(current_snapshot)s, %(changed_fields)s, %(sync_source)s
);
"""

MAX_VERSION_SQL = """
SELECT COALESCE(MAX(version_no), 0)
FROM public.marketplace_entity_versions
WHERE marketplace = %s AND entity_type = %s AND entity_id = %s;
"""


class VersionOutcome(str, Enum):
    INSERTED = "inserted"
    VERSIONED = "versioned"
    SKIPPED = "skipped"


@dataclass(slots=True)
class VersionImportStats:
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    versioned: int = 0
    skipped: int = 0
    failed: int = 0


def tracked_fields_for(marketplace: str, entity_type: str) -> tuple[str, ...]:
    key = (marketplace, entity_type)
    if key not in VERSION_TRACKED_FIELDS:
        raise KeyError(f"no tracked fields for {marketplace}/{entity_type}")
    return VERSION_TRACKED_FIELDS[key]


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): normalize_value(v) for k, v in sorted(value.items())}
    return value


def snapshot_from_row(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: normalize_value(row.get(field)) for field in fields}


def diff_snapshots(
    old: dict[str, Any],
    new: dict[str, Any],
    fields: tuple[str, ...],
) -> list[str]:
    changed: list[str] = []
    for field in fields:
        if old.get(field) != new.get(field):
            changed.append(field)
    return changed


def preload_snapshots(
    connection: Any,
    table: str,
    entity_ids: set[str],
    fields: tuple[str, ...],
    *,
    schema: str = "public",
) -> dict[str, dict[str, Any]]:
    if not entity_ids:
        return {}
    columns = ["id", *fields]
    col_sql = ", ".join(columns)
    sql = f"SELECT {col_sql} FROM {schema}.{table} WHERE id::text = ANY(%s)"
    snapshots: dict[str, dict[str, Any]] = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, (list(entity_ids),))
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row, strict=True))
            entity_id = str(row_dict.pop("id"))
            snapshots[entity_id] = snapshot_from_row(row_dict, fields)
    return snapshots


def max_version_no(
    cursor: Any,
    *,
    marketplace: str,
    entity_type: str,
    entity_id: str,
) -> int:
    cursor.execute(MAX_VERSION_SQL, (marketplace, entity_type, entity_id))
    result = cursor.fetchone()
    return int(result[0]) if result else 0


def insert_version_row(
    cursor: Any,
    *,
    marketplace: str,
    entity_type: str,
    entity_id: str,
    version_no: int,
    previous_snapshot: dict[str, Any],
    current_snapshot: dict[str, Any],
    changed_fields: list[str],
    sync_source: str = "weekly_cron",
) -> None:
    prev_payload = Jsonb(previous_snapshot) if Jsonb is not None else previous_snapshot
    curr_payload = Jsonb(current_snapshot) if Jsonb is not None else current_snapshot
    cursor.execute(
        INSERT_VERSION_SQL,
        {
            "marketplace": marketplace,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "version_no": version_no,
            "previous_snapshot": prev_payload,
            "current_snapshot": curr_payload,
            "changed_fields": changed_fields,
            "sync_source": sync_source,
        },
    )


def apply_versioned_upsert(
    cursor: Any,
    *,
    marketplace: str,
    entity_type: str,
    row: dict[str, Any],
    upsert_sql: str,
    tracked_fields: tuple[str, ...],
    known_snapshots: dict[str, dict[str, Any]],
    sync_source: str = "weekly_cron",
) -> VersionOutcome:
    entity_id = str(row["id"])
    new_snapshot = snapshot_from_row(row, tracked_fields)
    old_snapshot = known_snapshots.get(entity_id)

    if old_snapshot is not None:
        changed_fields = diff_snapshots(old_snapshot, new_snapshot, tracked_fields)
        if not changed_fields:
            return VersionOutcome.SKIPPED

    cursor.execute(upsert_sql, row)
    cursor.fetchone()

    if old_snapshot is None:
        insert_version_row(
            cursor,
            marketplace=marketplace,
            entity_type=entity_type,
            entity_id=entity_id,
            version_no=1,
            previous_snapshot={},
            current_snapshot=new_snapshot,
            changed_fields=list(tracked_fields),
            sync_source=sync_source,
        )
        known_snapshots[entity_id] = new_snapshot
        return VersionOutcome.INSERTED

    version_no = max_version_no(
        cursor,
        marketplace=marketplace,
        entity_type=entity_type,
        entity_id=entity_id,
    ) + 1
    insert_version_row(
        cursor,
        marketplace=marketplace,
        entity_type=entity_type,
        entity_id=entity_id,
        version_no=version_no,
        previous_snapshot=old_snapshot,
        current_snapshot=new_snapshot,
        changed_fields=changed_fields,
        sync_source=sync_source,
    )
    known_snapshots[entity_id] = new_snapshot
    return VersionOutcome.VERSIONED
