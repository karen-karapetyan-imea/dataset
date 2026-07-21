#!/usr/bin/env python3
"""Import Saatchi extracted JSONL into saatchi_artists / saatchi_artworks tables."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover
    psycopg = None
    Jsonb = None

from etl.history import TRACKED_FIELDS, upsert_with_history

LOGGER = logging.getLogger(__name__)

UPSERT_ARTIST_SQL = """
INSERT INTO public.saatchi_artists (
  id, user_name, artist_name, first_name, last_name, profile_image_url,
  biography, education, exhibitions, country, city, state,
  profile_url, canonical_url, joined_date, html_path, raw_json, updated_at
) VALUES (
  %(id)s, %(user_name)s, %(artist_name)s, %(first_name)s, %(last_name)s, %(profile_image_url)s,
  %(biography)s, %(education)s, %(exhibitions)s, %(country)s, %(city)s, %(state)s,
  %(profile_url)s, %(canonical_url)s, %(joined_date)s, %(html_path)s, %(raw_json)s, now()
)
ON CONFLICT (id) DO UPDATE SET
  user_name = EXCLUDED.user_name,
  artist_name = EXCLUDED.artist_name,
  first_name = EXCLUDED.first_name,
  last_name = EXCLUDED.last_name,
  profile_image_url = EXCLUDED.profile_image_url,
  biography = EXCLUDED.biography,
  education = EXCLUDED.education,
  exhibitions = EXCLUDED.exhibitions,
  country = EXCLUDED.country,
  city = EXCLUDED.city,
  state = EXCLUDED.state,
  profile_url = EXCLUDED.profile_url,
  canonical_url = EXCLUDED.canonical_url,
  joined_date = EXCLUDED.joined_date,
  html_path = EXCLUDED.html_path,
  raw_json = EXCLUDED.raw_json,
  updated_at = now()
RETURNING (xmax = 0) AS inserted;
"""

UPSERT_ARTWORK_SQL = """
INSERT INTO public.saatchi_artworks (
  id, artist_id, title, artist_name, artist_profile_url, category, medium,
  materials, styles, subject, description, price, currency, availability,
  artwork_year, image_url, image_urls, dimensions, sku, keywords,
  canonical_url, html_path, raw_json, updated_at
) VALUES (
  %(id)s, %(artist_id)s, %(title)s, %(artist_name)s, %(artist_profile_url)s, %(category)s, %(medium)s,
  %(materials)s, %(styles)s, %(subject)s, %(description)s, %(price)s, %(currency)s, %(availability)s,
  %(artwork_year)s, %(image_url)s, %(image_urls)s, %(dimensions)s, %(sku)s, %(keywords)s,
  %(canonical_url)s, %(html_path)s, %(raw_json)s, now()
)
ON CONFLICT (id) DO UPDATE SET
  artist_id = EXCLUDED.artist_id,
  title = EXCLUDED.title,
  artist_name = EXCLUDED.artist_name,
  artist_profile_url = EXCLUDED.artist_profile_url,
  category = EXCLUDED.category,
  medium = EXCLUDED.medium,
  materials = EXCLUDED.materials,
  styles = EXCLUDED.styles,
  subject = EXCLUDED.subject,
  description = EXCLUDED.description,
  price = EXCLUDED.price,
  currency = EXCLUDED.currency,
  availability = EXCLUDED.availability,
  artwork_year = EXCLUDED.artwork_year,
  image_url = EXCLUDED.image_url,
  image_urls = EXCLUDED.image_urls,
  dimensions = EXCLUDED.dimensions,
  sku = EXCLUDED.sku,
  keywords = EXCLUDED.keywords,
  canonical_url = EXCLUDED.canonical_url,
  html_path = EXCLUDED.html_path,
  raw_json = EXCLUDED.raw_json,
  updated_at = now()
RETURNING (xmax = 0) AS inserted;
"""

ARTIST_EXISTS_SQL = "SELECT 1 FROM public.saatchi_artists WHERE id = %s LIMIT 1;"
ARTWORK_EXISTS_SQL = "SELECT 1 FROM public.saatchi_artworks WHERE id = %s LIMIT 1;"


@dataclass(slots=True)
class SaatchiImportStats:
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _parse_price(value: Any) -> Decimal | None:
    text = _text_or_none(value)
    if not text:
        return None
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


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


def _parse_joined_date(value: Any) -> date | None:
    text = _text_or_none(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text.replace("Z", "+0000"), fmt).date()
        except ValueError:
            continue
    return None


def storage_path(html_dir: Path, filename: str) -> str:
    return f"{html_dir.name}/{filename}"


def build_artist_row(record: dict[str, Any], *, html_dir: Path) -> dict[str, Any]:
    artist_id = record.get("artist_external_id")
    if artist_id is None:
        raise ValueError("artist_external_id is required")
    return {
        "id": int(artist_id),
        "user_name": _text_or_none(record.get("user_name")),
        "artist_name": _text_or_none(record.get("name")),
        "first_name": _text_or_none(record.get("first_name")),
        "last_name": _text_or_none(record.get("last_name")),
        "profile_image_url": _text_or_none(record.get("profile_image_url")),
        "biography": _text_or_none(record.get("biography")),
        "education": _text_or_none(record.get("education")),
        "exhibitions": _text_or_none(record.get("exhibitions")),
        "country": _text_or_none(record.get("country")),
        "city": _text_or_none(record.get("city")),
        "state": _text_or_none(record.get("state")),
        "profile_url": _text_or_none(record.get("url")),
        "canonical_url": _text_or_none(record.get("canonical_url")),
        "joined_date": _parse_joined_date(record.get("joined_date")),
        "html_path": storage_path(html_dir, str(record.get("source_file") or "")),
        "raw_json": Jsonb(record) if Jsonb is not None else record,
    }


def build_artwork_row(
    record: dict[str, Any],
    *,
    html_dir: Path,
    artist_id_fk: int | None,
) -> dict[str, Any]:
    artwork_id = record.get("artwork_id")
    if artwork_id is None:
        raise ValueError("artwork_id is required")
    image_urls = record.get("image_urls") or []
    if not isinstance(image_urls, list):
        image_urls = []
    image_urls = [str(url) for url in image_urls if url]
    materials = record.get("materials") or []
    styles = record.get("styles") or []
    keywords = record.get("keywords") or []
    dimensions = record.get("dimensions")
    return {
        "id": int(artwork_id),
        "artist_id": artist_id_fk,
        "title": _text_or_none(record.get("title")),
        "artist_name": _text_or_none(record.get("artist")),
        "artist_profile_url": _text_or_none(record.get("artist_url")),
        "category": _text_or_none(record.get("artform")),
        "medium": _text_or_none(record.get("medium")),
        "materials": materials if isinstance(materials, list) else None,
        "styles": styles if isinstance(styles, list) else None,
        "subject": _text_or_none(record.get("subject")),
        "description": _text_or_none(record.get("description")),
        "price": _parse_price(record.get("price")),
        "currency": _text_or_none(record.get("currency")),
        "availability": _text_or_none(record.get("availability")),
        "artwork_year": _parse_year(record.get("year")),
        "image_url": image_urls[0] if image_urls else None,
        "image_urls": image_urls or None,
        "dimensions": Jsonb(dimensions) if dimensions and Jsonb is not None else dimensions,
        "sku": _text_or_none(record.get("sku")),
        "keywords": keywords if isinstance(keywords, list) else None,
        "canonical_url": _text_or_none(record.get("url")),
        "html_path": storage_path(html_dir, str(record.get("source_file") or "")),
        "raw_json": Jsonb(record) if Jsonb is not None else record,
    }


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _exists(cursor: Any, sql: str, entity_id: int) -> bool:
    cursor.execute(sql, (entity_id,))
    return cursor.fetchone() is not None


def _resolve_artist_fk(cursor: Any, artist_external_id: Any) -> int | None:
    text = _text_or_none(artist_external_id)
    if not text:
        return None
    try:
        artist_id = int(text)
    except ValueError:
        return None
    if _exists(cursor, ARTIST_EXISTS_SQL, artist_id):
        return artist_id
    return None


def import_artists(
    connection: Any,
    records: Iterator[dict[str, Any]],
    *,
    html_dir: Path,
    skip_existing: bool,
    stats: SaatchiImportStats,
) -> None:
    tracked_fields = TRACKED_FIELDS[("saatchi", "artist")]
    select_sql = f"SELECT {', '.join(tracked_fields)} FROM public.saatchi_artists WHERE id = %s"

    for record in records:
        stats.scanned += 1
        try:
            row = build_artist_row(record, html_dir=html_dir)
        except (ValueError, TypeError) as exc:
            stats.failed += 1
            LOGGER.warning("artist row build failed: %s", exc)
            continue
        try:
            with connection.cursor() as cursor:
                if skip_existing and _exists(cursor, ARTIST_EXISTS_SQL, row["id"]):
                    stats.skipped += 1
                    continue
                inserted = upsert_with_history(
                    cursor,
                    source="saatchi",
                    entity_type="artist",
                    entity_id=row["id"],
                    tracked_fields=tracked_fields,
                    select_sql=select_sql,
                    upsert_sql=UPSERT_ARTIST_SQL,
                    row=row,
                    metadata={
                        "html_path": row.get("html_path"),
                        "profile_url": row.get("profile_url"),
                        "canonical_url": row.get("canonical_url"),
                    },
                )
            connection.commit()
            if inserted:
                stats.inserted += 1
            else:
                stats.updated += 1
        except Exception as exc:
            connection.rollback()
            stats.failed += 1
            LOGGER.warning("artist import failed id=%s error=%s", row.get("id"), exc)


def import_artworks(
    connection: Any,
    records: Iterator[dict[str, Any]],
    *,
    html_dir: Path,
    skip_existing: bool,
    stats: SaatchiImportStats,
) -> None:
    tracked_fields = TRACKED_FIELDS[("saatchi", "artwork")]
    select_sql = (
        f"SELECT {', '.join(tracked_fields)} FROM public.saatchi_artworks WHERE id = %s"
    )

    for record in records:
        stats.scanned += 1
        try:
            with connection.cursor() as cursor:
                artist_fk = _resolve_artist_fk(cursor, record.get("artist_external_id"))
                row = build_artwork_row(record, html_dir=html_dir, artist_id_fk=artist_fk)
                if skip_existing and _exists(cursor, ARTWORK_EXISTS_SQL, row["id"]):
                    stats.skipped += 1
                    continue
                inserted = upsert_with_history(
                    cursor,
                    source="saatchi",
                    entity_type="artwork",
                    entity_id=row["id"],
                    tracked_fields=tracked_fields,
                    select_sql=select_sql,
                    upsert_sql=UPSERT_ARTWORK_SQL,
                    row=row,
                    metadata={
                        "html_path": row.get("html_path"),
                        "canonical_url": row.get("canonical_url"),
                        "artist_profile_url": row.get("artist_profile_url"),
                    },
                )
            connection.commit()
            if inserted:
                stats.inserted += 1
            else:
                stats.updated += 1
        except Exception as exc:
            connection.rollback()
            stats.failed += 1
            LOGGER.warning("artwork import failed id=%s error=%s", record.get("artwork_id"), exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Saatchi JSONL into saatchi_* tables.")
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--html-dir", type=Path, required=True)
    parser.add_argument("--artists-jsonl", type=Path, default=None)
    parser.add_argument("--artworks-jsonl", type=Path, default=None)
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if psycopg is None:
        raise SystemExit("psycopg is required")
    if not args.artists_jsonl and not args.artworks_jsonl:
        raise SystemExit("Provide --artists-jsonl and/or --artworks-jsonl")

    connection = psycopg.connect(args.db_url)
    try:
        if args.artists_jsonl:
            if not args.artists_jsonl.is_file():
                raise SystemExit(f"artists jsonl not found: {args.artists_jsonl}")
            records = iter_jsonl(args.artists_jsonl)
            if args.limit is not None:
                records = (row for index, row in enumerate(records) if index < args.limit)
            artist_stats = SaatchiImportStats()
            import_artists(
                connection,
                records,
                html_dir=args.html_dir,
                skip_existing=args.skip_existing,
                stats=artist_stats,
            )
            LOGGER.info(
                "artists done scanned=%s inserted=%s updated=%s skipped=%s failed=%s",
                artist_stats.scanned,
                artist_stats.inserted,
                artist_stats.updated,
                artist_stats.skipped,
                artist_stats.failed,
            )

        if args.artworks_jsonl:
            if not args.artworks_jsonl.is_file():
                raise SystemExit(f"artworks jsonl not found: {args.artworks_jsonl}")
            records = iter_jsonl(args.artworks_jsonl)
            if args.limit is not None:
                records = (row for index, row in enumerate(records) if index < args.limit)
            artwork_stats = SaatchiImportStats()
            import_artworks(
                connection,
                records,
                html_dir=args.html_dir,
                skip_existing=args.skip_existing,
                stats=artwork_stats,
            )
            LOGGER.info(
                "artworks done scanned=%s inserted=%s updated=%s skipped=%s failed=%s",
                artwork_stats.scanned,
                artwork_stats.inserted,
                artwork_stats.updated,
                artwork_stats.skipped,
                artwork_stats.failed,
            )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
