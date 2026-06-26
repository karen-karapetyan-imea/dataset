#!/usr/bin/env python3
"""Import Artsper HTML into legacy arts_artists / arts_artworks tables."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

from etl.artsper import extract_artist_record, extract_artwork_record
from etl.urls import artsper_entity_from_url
from etl.versioning import (
    VersionOutcome,
    apply_versioned_upsert,
    preload_snapshots,
    tracked_fields_for,
)
from mapping_utils import iter_mapping_rows, iter_url_list_rows

LOGGER = logging.getLogger(__name__)

UPSERT_ARTIST_SQL = """
INSERT INTO public.arts_artists (
  id, artist_name, profile_image_url, biography, artist_slug, path
) VALUES (
  %(id)s, %(artist_name)s, %(profile_image_url)s, %(biography)s, %(artist_slug)s, %(path)s
)
ON CONFLICT (id) DO UPDATE SET
  artist_name = EXCLUDED.artist_name,
  profile_image_url = EXCLUDED.profile_image_url,
  biography = EXCLUDED.biography,
  artist_slug = EXCLUDED.artist_slug,
  path = EXCLUDED.path
RETURNING (xmax = 0) AS inserted;
"""

UPSERT_ARTWORK_SQL = """
INSERT INTO public.arts_artworks (
  id, artwork_title, artwork_year, artist_name, category, medium,
  price, currency, artwork_cover_url, artist_slug, path
) VALUES (
  %(id)s, %(artwork_title)s, %(artwork_year)s, %(artist_name)s, %(category)s, %(medium)s,
  %(price)s, %(currency)s, %(artwork_cover_url)s, %(artist_slug)s, %(path)s
)
ON CONFLICT (id) DO UPDATE SET
  artwork_title = EXCLUDED.artwork_title,
  artwork_year = EXCLUDED.artwork_year,
  artist_name = EXCLUDED.artist_name,
  category = EXCLUDED.category,
  medium = EXCLUDED.medium,
  price = EXCLUDED.price,
  currency = EXCLUDED.currency,
  artwork_cover_url = EXCLUDED.artwork_cover_url,
  artist_slug = EXCLUDED.artist_slug,
  path = EXCLUDED.path
RETURNING (xmax = 0) AS inserted;
"""

ARTIST_EXISTS_SQL = "SELECT 1 FROM public.arts_artists WHERE id = %s LIMIT 1;"
ARTWORK_EXISTS_SQL = "SELECT 1 FROM public.arts_artworks WHERE id = %s LIMIT 1;"


@dataclass(slots=True)
class LegacyImportStats:
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    versioned: int = 0
    skipped: int = 0
    failed: int = 0


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _parse_year(value: Any) -> int | None:
    text = _text_or_none(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits[:4])
    except ValueError:
        return None


def _parse_price(value: Any) -> Decimal | None:
    text = _text_or_none(value)
    if not text:
        return None
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def storage_path(html_dir: Path, filename: str) -> str:
    """Legacy path column, e.g. artsper_data/<sha1>.html."""
    return f"{html_dir.name}/{filename}"


def build_artist_row(
    entity_id: str,
    record: dict[str, Any],
    *,
    html_dir: Path,
    filename: str,
) -> dict[str, Any]:
    page_url = _text_or_none(record.get("url"))
    return {
        "id": int(entity_id),
        "artist_name": _text_or_none(record.get("name")),
        "profile_image_url": _text_or_none(record.get("image_url")),
        "biography": _text_or_none(record.get("about_text")),
        "artist_slug": page_url,
        "path": storage_path(html_dir, filename),
    }


def build_artwork_row(
    entity_id: str,
    record: dict[str, Any],
    *,
    html_dir: Path,
    filename: str,
) -> dict[str, Any]:
    images = record.get("image_urls") or []
    image_url = images[0] if images else None
    page_url = _text_or_none(record.get("url"))
    artist_url = None
    artist_external_id = _text_or_none(record.get("artist_external_id"))
    if artist_external_id and page_url:
        entity = artsper_entity_from_url(page_url)
        if entity and entity[0] == "artwork":
            # Best-effort artist page URL from creator is stored separately when present.
            pass
    creator_url = record.get("artist_url")
    if isinstance(creator_url, str):
        artist_url = creator_url
    return {
        "id": int(entity_id),
        "artwork_title": _text_or_none(record.get("title")),
        "artwork_year": _parse_year(record.get("year")),
        "artist_name": _text_or_none(record.get("artist")),
        "category": _text_or_none(record.get("artform")),
        "medium": _text_or_none(record.get("medium")),
        "price": _parse_price(record.get("price")),
        "currency": _text_or_none(record.get("currency")),
        "artwork_cover_url": _text_or_none(image_url),
        "artist_slug": artist_url,
        "path": storage_path(html_dir, filename),
    }


def _legacy_exists(cursor: Any, entity_type: str, entity_id: int) -> bool:
    sql = ARTIST_EXISTS_SQL if entity_type == "artist" else ARTWORK_EXISTS_SQL
    cursor.execute(sql, (entity_id,))
    return cursor.fetchone() is not None


def upsert_row(cursor: Any, entity_type: str, row: dict[str, Any]) -> str:
    sql = UPSERT_ARTIST_SQL if entity_type == "artist" else UPSERT_ARTWORK_SQL
    cursor.execute(sql, row)
    result = cursor.fetchone()
    inserted = bool(result[0]) if result else False
    return "inserted" if inserted else "updated"


def _collect_legacy_ids(
    row_iter: Iterator[tuple[str, str, int]],
) -> tuple[set[str], set[str]]:
    artist_ids: set[str] = set()
    artwork_ids: set[str] = set()
    for url, _filename, _status in row_iter:
        entity = artsper_entity_from_url(url)
        if entity is None:
            continue
        entity_type, external_id = entity
        if entity_type == "artist":
            artist_ids.add(str(external_id))
        else:
            artwork_ids.add(str(external_id))
    return artist_ids, artwork_ids


def _record_outcome(stats: LegacyImportStats, outcome: VersionOutcome | str, *, inserted: bool) -> None:
    if isinstance(outcome, VersionOutcome):
        if outcome == VersionOutcome.INSERTED:
            stats.inserted += 1
        elif outcome == VersionOutcome.VERSIONED:
            stats.versioned += 1
        else:
            stats.skipped += 1
        return
    if inserted:
        stats.inserted += 1
    else:
        stats.updated += 1


def process_row(
    connection: Any | None,
    *,
    url: str,
    html_path: Path,
    html_dir: Path,
    dry_run: bool,
    skip_existing: bool,
    sync_versions: bool,
    stats: LegacyImportStats,
    artist_snapshots: dict[str, dict[str, Any]],
    artwork_snapshots: dict[str, dict[str, Any]],
    sync_source: str = "weekly_cron",
) -> None:
    stats.scanned += 1
    if not html_path.is_file() or html_path.stat().st_size == 0:
        stats.skipped += 1
        return

    entity = artsper_entity_from_url(url)
    if entity is None:
        stats.skipped += 1
        return
    entity_type, external_id = entity

    if entity_type == "artwork":
        record, missing = extract_artwork_record(html_path, url)
        if missing:
            stats.skipped += 1
            return
        row = build_artwork_row(external_id, record, html_dir=html_dir, filename=html_path.name)
    else:
        record, missing = extract_artist_record(html_path, url)
        if missing:
            stats.skipped += 1
            return
        row = build_artist_row(external_id, record, html_dir=html_dir, filename=html_path.name)

    if dry_run:
        stats.inserted += 1
        return

    assert connection is not None
    try:
        if sync_versions:
            tracked = tracked_fields_for("artsper", entity_type)
            snapshots = artist_snapshots if entity_type == "artist" else artwork_snapshots
            upsert_sql = UPSERT_ARTIST_SQL if entity_type == "artist" else UPSERT_ARTWORK_SQL
            with connection.cursor() as cursor:
                outcome = apply_versioned_upsert(
                    cursor,
                    marketplace="artsper",
                    entity_type=entity_type,
                    row=row,
                    upsert_sql=upsert_sql,
                    tracked_fields=tracked,
                    known_snapshots=snapshots,
                    sync_source=sync_source,
                )
            connection.commit()
            _record_outcome(stats, outcome, inserted=False)
            return

        with connection.cursor() as cursor:
            if skip_existing and _legacy_exists(cursor, entity_type, int(external_id)):
                stats.skipped += 1
                return
            outcome = upsert_row(cursor, entity_type, row)
        connection.commit()
        _record_outcome(stats, outcome, inserted=(outcome == "inserted"))
    except Exception as exc:
        connection.rollback()
        stats.failed += 1
        LOGGER.warning("legacy import failed url=%s error=%s", url, exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Artsper HTML into arts_artists / arts_artworks."
    )
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--html-dir", type=Path, default=Path("artsper_data"))
    parser.add_argument("--mapping-file", type=Path, default=None)
    parser.add_argument("--urls-file", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip rows whose Artsper id already exists in legacy tables (default: true).",
    )
    parser.add_argument(
        "--sync-versions",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Compare batch rows with DB, record version history on change (weekly cron)",
    )
    parser.add_argument("--sync-source", default="weekly_cron")
    parser.add_argument(
        "--status-ok-only",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if psycopg is None:
        raise SystemExit("psycopg is required")

    if args.urls_file is not None:
        if not args.urls_file.is_file():
            raise SystemExit(f"URLs file not found: {args.urls_file}")
        row_iter: Iterator[tuple[str, str, int]] = iter_url_list_rows(
            args.urls_file, args.html_dir, require_html=True
        )
    elif args.mapping_file is not None:
        if not args.mapping_file.is_file():
            raise SystemExit(f"Mapping file not found: {args.mapping_file}")
        row_iter = iter_mapping_rows(args.mapping_file)
    else:
        raise SystemExit("Provide --mapping-file or --urls-file")

    sync_versions = args.sync_versions
    artist_snapshots: dict[str, dict[str, Any]] = {}
    artwork_snapshots: dict[str, dict[str, Any]] = {}
    if sync_versions and not args.dry_run:
        artist_ids, artwork_ids = _collect_legacy_ids(list(row_iter))
        connection_pre = psycopg.connect(args.db_url)
        try:
            if artist_ids:
                artist_snapshots = preload_snapshots(
                    connection_pre,
                    "arts_artists",
                    artist_ids,
                    tracked_fields_for("artsper", "artist"),
                )
            if artwork_ids:
                artwork_snapshots = preload_snapshots(
                    connection_pre,
                    "arts_artworks",
                    artwork_ids,
                    tracked_fields_for("artsper", "artwork"),
                )
        finally:
            connection_pre.close()
        LOGGER.info(
            "preloaded snapshots artists=%s artworks=%s",
            len(artist_snapshots),
            len(artwork_snapshots),
        )
        if args.urls_file is not None:
            row_iter = iter_url_list_rows(args.urls_file, args.html_dir, require_html=True)
        else:
            row_iter = iter_mapping_rows(args.mapping_file)

    connection = None if args.dry_run else psycopg.connect(args.db_url)
    stats = LegacyImportStats()
    try:
        count = 0
        for url, filename, status_code in row_iter:
            if args.status_ok_only and status_code != 200:
                continue
            if args.limit is not None and count >= args.limit:
                break
            count += 1
            process_row(
                connection,
                url=url,
                html_path=args.html_dir / filename,
                html_dir=args.html_dir,
                dry_run=args.dry_run,
                skip_existing=args.skip_existing and not sync_versions,
                sync_versions=sync_versions,
                stats=stats,
                artist_snapshots=artist_snapshots,
                artwork_snapshots=artwork_snapshots,
                sync_source=args.sync_source,
            )
            if count % 500 == 0:
                LOGGER.info(
                    "progress scanned=%s inserted=%s updated=%s versioned=%s skipped=%s failed=%s",
                    stats.scanned,
                    stats.inserted,
                    stats.updated,
                    stats.versioned,
                    stats.skipped,
                    stats.failed,
                )
    finally:
        if connection is not None:
            connection.close()
    LOGGER.info(
        "done scanned=%s inserted=%s updated=%s versioned=%s skipped=%s failed=%s",
        stats.scanned,
        stats.inserted,
        stats.updated,
        stats.versioned,
        stats.skipped,
        stats.failed,
    )


if __name__ == "__main__":
    main()
