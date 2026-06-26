#!/usr/bin/env python3
"""Import Artsy extracted JSONL into artsy_* tables."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
    from psycopg import OperationalError
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover
    psycopg = None
    OperationalError = Exception  # type: ignore[misc, assignment]
    Jsonb = None

from etl.db_import import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_PROGRESS_EVERY,
    connect_db,
    log_progress,
    preload_ids,
)
from etl.versioning import (
    VersionOutcome,
    apply_versioned_upsert,
    preload_snapshots,
    tracked_fields_for,
)
from mapping_utils import iter_mapping_rows

LOGGER = logging.getLogger(__name__)

ENTITY_CONFIG: dict[str, dict[str, Any]] = {
    "artist": {
        "table": "artsy_artists",
        "sql": """
INSERT INTO public.artsy_artists (
  id, name, biography, image_url, profile_url, canonical_url, html_path, raw_json, updated_at
) VALUES (
  %(id)s, %(name)s, %(biography)s, %(image_url)s, %(profile_url)s, %(canonical_url)s, %(html_path)s, %(raw_json)s, now()
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  biography = EXCLUDED.biography,
  image_url = EXCLUDED.image_url,
  profile_url = EXCLUDED.profile_url,
  canonical_url = EXCLUDED.canonical_url,
  html_path = EXCLUDED.html_path,
  raw_json = EXCLUDED.raw_json,
  updated_at = now()
RETURNING (xmax = 0) AS inserted;
""",
    },
    "artwork": {
        "table": "artsy_artworks",
        "sql": """
INSERT INTO public.artsy_artworks (
  id, title, artist_name, artist_external_id, description, medium, year, price, currency,
  image_url, image_urls, canonical_url, html_path, raw_json, updated_at
) VALUES (
  %(id)s, %(title)s, %(artist_name)s, %(artist_external_id)s, %(description)s, %(medium)s, %(year)s,
  %(price)s, %(currency)s, %(image_url)s, %(image_urls)s, %(canonical_url)s, %(html_path)s, %(raw_json)s, now()
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  artist_name = EXCLUDED.artist_name,
  artist_external_id = EXCLUDED.artist_external_id,
  description = EXCLUDED.description,
  medium = EXCLUDED.medium,
  year = EXCLUDED.year,
  price = EXCLUDED.price,
  currency = EXCLUDED.currency,
  image_url = EXCLUDED.image_url,
  image_urls = EXCLUDED.image_urls,
  canonical_url = EXCLUDED.canonical_url,
  html_path = EXCLUDED.html_path,
  raw_json = EXCLUDED.raw_json,
  updated_at = now()
RETURNING (xmax = 0) AS inserted;
""",
    },
    "partner": {
        "table": "artsy_partners",
        "sql": """
INSERT INTO public.artsy_partners (
  id, name, description, image_url, profile_url, canonical_url, html_path, raw_json, updated_at
) VALUES (
  %(id)s, %(name)s, %(description)s, %(image_url)s, %(profile_url)s, %(canonical_url)s, %(html_path)s, %(raw_json)s, now()
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  image_url = EXCLUDED.image_url,
  profile_url = EXCLUDED.profile_url,
  canonical_url = EXCLUDED.canonical_url,
  html_path = EXCLUDED.html_path,
  raw_json = EXCLUDED.raw_json,
  updated_at = now()
RETURNING (xmax = 0) AS inserted;
""",
    },
    "show": {
        "table": "artsy_shows",
        "sql": """
INSERT INTO public.artsy_shows (
  id, name, description, start_date, end_date, canonical_url, html_path, raw_json, updated_at
) VALUES (
  %(id)s, %(name)s, %(description)s, %(start_date)s, %(end_date)s, %(canonical_url)s, %(html_path)s, %(raw_json)s, now()
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  start_date = EXCLUDED.start_date,
  end_date = EXCLUDED.end_date,
  canonical_url = EXCLUDED.canonical_url,
  html_path = EXCLUDED.html_path,
  raw_json = EXCLUDED.raw_json,
  updated_at = now()
RETURNING (xmax = 0) AS inserted;
""",
    },
    "fair": {
        "table": "artsy_fairs",
        "sql": """
INSERT INTO public.artsy_fairs (
  id, name, description, start_date, end_date, canonical_url, html_path, raw_json, updated_at
) VALUES (
  %(id)s, %(name)s, %(description)s, %(start_date)s, %(end_date)s, %(canonical_url)s, %(html_path)s, %(raw_json)s, now()
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  start_date = EXCLUDED.start_date,
  end_date = EXCLUDED.end_date,
  canonical_url = EXCLUDED.canonical_url,
  html_path = EXCLUDED.html_path,
  raw_json = EXCLUDED.raw_json,
  updated_at = now()
RETURNING (xmax = 0) AS inserted;
""",
    },
}

JUNCTION_SQL = """
INSERT INTO public.artsy_artwork_artist (artwork_id, artist_id)
VALUES (%(artwork_id)s, %(artist_id)s)
ON CONFLICT (artwork_id, artist_id) DO NOTHING;
"""


@dataclass(slots=True)
class ImportStats:
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


def storage_path(html_dir: Path, filename: str) -> str:
    return f"{html_dir.name}/{filename}"


def build_row(record: dict[str, Any], *, html_dir: Path) -> dict[str, Any]:
    entity_type = record.get("entity_type")
    external_id = record.get("external_id")
    if not external_id:
        raise ValueError("external_id is required")

    base = {
        "id": str(external_id),
        "canonical_url": _text_or_none(record.get("canonical_url") or record.get("url")),
        "html_path": storage_path(html_dir, str(record.get("source_file") or "")),
        "raw_json": Jsonb(record) if Jsonb is not None else record,
    }

    if entity_type == "artist":
        return {
            **base,
            "name": _text_or_none(record.get("name")),
            "biography": _text_or_none(record.get("biography")),
            "image_url": _text_or_none(record.get("image_url")),
            "profile_url": _text_or_none(record.get("url")),
        }
    if entity_type == "artwork":
        image_urls = record.get("image_urls") or []
        if not isinstance(image_urls, list):
            image_urls = []
        image_urls = [str(url) for url in image_urls if url]
        return {
            **base,
            "title": _text_or_none(record.get("title")),
            "artist_name": _text_or_none(record.get("artist_name")),
            "artist_external_id": _text_or_none(record.get("artist_external_id")),
            "description": _text_or_none(record.get("description")),
            "medium": _text_or_none(record.get("medium")),
            "year": _text_or_none(record.get("year")),
            "price": _text_or_none(record.get("price")),
            "currency": _text_or_none(record.get("currency")),
            "image_url": image_urls[0] if image_urls else None,
            "image_urls": image_urls or None,
        }
    if entity_type in {"partner", "show", "fair"}:
        row = {
            **base,
            "name": _text_or_none(record.get("name")),
            "description": _text_or_none(record.get("description")),
        }
        if entity_type == "partner":
            row["image_url"] = _text_or_none(record.get("image_url"))
            row["profile_url"] = _text_or_none(record.get("url"))
        else:
            row["start_date"] = _text_or_none(record.get("start_date"))
            row["end_date"] = _text_or_none(record.get("end_date"))
        return row
    raise ValueError(f"unsupported entity_type: {entity_type}")


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


def _mapping_filenames(mapping_file: Path | None) -> set[str] | None:
    if mapping_file is None:
        return None
    return {filename for _url, filename, _status in iter_mapping_rows(mapping_file)}


def _run_upsert(connection: Any, db_url: str, sql: str, row: dict[str, Any]) -> tuple[Any, bool]:
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, row)
            inserted = bool(cursor.fetchone()[0])
        return connection, inserted
    except OperationalError:
        try:
            connection.close()
        except Exception:
            pass
        connection = connect_db(db_url)
        with connection.cursor() as cursor:
            cursor.execute(sql, row)
            inserted = bool(cursor.fetchone()[0])
        return connection, inserted


def _collect_entity_ids(
    path: Path,
    *,
    mapping_filenames: set[str] | None,
    entity_type: str,
) -> set[str]:
    ids: set[str] = set()
    for record in iter_jsonl(path):
        if mapping_filenames is not None and str(record.get("source_file") or "") not in mapping_filenames:
            continue
        if str(record.get("entity_type") or "") != entity_type:
            continue
        external_id = record.get("external_id")
        if external_id is not None:
            ids.add(str(external_id))
    return ids


def _record_outcome(stats: ImportStats, outcome: VersionOutcome | str, *, inserted: bool) -> None:
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


def import_jsonl_file(
    connection: Any,
    path: Path,
    *,
    db_url: str,
    html_dir: Path,
    skip_existing: bool,
    sync_versions: bool,
    known_ids: dict[str, set[int | str]],
    known_snapshots: dict[str, dict[str, dict[str, Any]]],
    mapping_filenames: set[str] | None,
    batch_size: int,
    progress_every: int,
    sync_source: str = "weekly_cron",
) -> Any:
    stats = ImportStats()
    pending = 0

    for record in iter_jsonl(path):
        if mapping_filenames is not None and str(record.get("source_file") or "") not in mapping_filenames:
            continue
        stats.scanned += 1
        entity_type = str(record.get("entity_type") or "")
        config = ENTITY_CONFIG.get(entity_type)
        if config is None:
            stats.skipped += 1
            continue

        try:
            row = build_row(record, html_dir=html_dir)
        except (ValueError, TypeError) as exc:
            stats.failed += 1
            LOGGER.warning("row build failed: %s", exc)
            continue

        table = config["table"]
        known = known_ids.setdefault(table, set())
        entity_id = str(row["id"])
        if sync_versions:
            snapshots = known_snapshots.setdefault(table, {})
            tracked = tracked_fields_for("artsy", entity_type)
            try:
                with connection.cursor() as cursor:
                    outcome = apply_versioned_upsert(
                        cursor,
                        marketplace="artsy",
                        entity_type=entity_type,
                        row=row,
                        upsert_sql=config["sql"],
                        tracked_fields=tracked,
                        known_snapshots=snapshots,
                        sync_source=sync_source,
                    )
                    if entity_type == "artwork":
                        artist_id = row.get("artist_external_id")
                        if artist_id and str(artist_id) in known_ids.get("artsy_artists", set()):
                            cursor.execute(
                                JUNCTION_SQL,
                                {"artwork_id": entity_id, "artist_id": artist_id},
                            )
                pending += 1
                known.add(entity_id)
                _record_outcome(stats, outcome, inserted=False)
                if pending >= batch_size:
                    connection.commit()
                    pending = 0
            except Exception as exc:
                connection.rollback()
                pending = 0
                stats.failed += 1
                LOGGER.warning("import failed entity=%s id=%s error=%s", entity_type, entity_id, exc)
            log_progress(entity_type, stats, every=progress_every)
            continue

        if skip_existing and entity_id in known:
            stats.skipped += 1
            log_progress(entity_type, stats, every=progress_every)
            continue

        try:
            connection, inserted = _run_upsert(connection, db_url, config["sql"], row)
            pending += 1
            known.add(entity_id)
            _record_outcome(stats, "upsert", inserted=inserted)

            if entity_type == "artwork":
                artist_id = row.get("artist_external_id")
                if artist_id and artist_id in known_ids.get("artsy_artists", set()):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            JUNCTION_SQL,
                            {"artwork_id": entity_id, "artist_id": artist_id},
                        )
                    pending += 1

            if pending >= batch_size:
                connection.commit()
                pending = 0
        except Exception as exc:
            connection.rollback()
            pending = 0
            stats.failed += 1
            LOGGER.warning("import failed entity=%s id=%s error=%s", entity_type, entity_id, exc)

        log_progress(entity_type, stats, every=progress_every)

    if pending:
        connection.commit()

    LOGGER.info(
        "%s done scanned=%s inserted=%s updated=%s versioned=%s skipped=%s failed=%s",
        path.name,
        stats.scanned,
        stats.inserted,
        stats.updated,
        stats.versioned,
        stats.skipped,
        stats.failed,
    )
    return connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Artsy JSONL into artsy_* tables.")
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--html-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, default=Path("state/artsy"))
    parser.add_argument("--mapping-file", type=Path, default=None)
    parser.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--sync-versions",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Compare batch rows with DB, record version history on change (weekly cron)",
    )
    parser.add_argument("--sync-source", default="weekly_cron")
    parser.add_argument(
        "--state-suffix",
        default="",
        help="Import artsy_{entity}s{suffix}.jsonl from state-dir (e.g. _batch)",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--progress-every", type=int, default=DEFAULT_PROGRESS_EVERY)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if psycopg is None:
        raise SystemExit("psycopg is required")

    mapping_filenames = _mapping_filenames(args.mapping_file)
    sync_versions = args.sync_versions
    connection = connect_db(args.db_url)
    known_ids: dict[str, set[int | str]] = {}
    known_snapshots: dict[str, dict[str, dict[str, Any]]] = {}
    for entity, config in ENTITY_CONFIG.items():
        try:
            known_ids[config["table"]] = {str(value) for value in preload_ids(connection, config["table"])}
        except Exception as exc:
            LOGGER.warning("could not preload %s: %s", config["table"], exc)
            known_ids[config["table"]] = set()
    LOGGER.info("preloaded table counts=%s", {k: len(v) for k, v in known_ids.items()})

    if sync_versions:
        for entity in ENTITY_CONFIG:
            path = args.state_dir / f"artsy_{entity}s{args.state_suffix}.jsonl"
            if not path.is_file():
                continue
            table = ENTITY_CONFIG[entity]["table"]
            entity_ids = _collect_entity_ids(
                path,
                mapping_filenames=mapping_filenames,
                entity_type=entity,
            )
            if entity_ids:
                known_snapshots[table] = preload_snapshots(
                    connection,
                    table,
                    entity_ids,
                    tracked_fields_for("artsy", entity),
                )
                LOGGER.info("preloaded snapshots table=%s count=%s", table, len(known_snapshots[table]))

    try:
        for entity in ENTITY_CONFIG:
            path = args.state_dir / f"artsy_{entity}s{args.state_suffix}.jsonl"
            if not path.is_file():
                continue
            connection = import_jsonl_file(
                connection,
                path,
                db_url=args.db_url,
                html_dir=args.html_dir,
                skip_existing=args.skip_existing and not sync_versions,
                sync_versions=sync_versions,
                known_ids=known_ids,
                known_snapshots=known_snapshots,
                mapping_filenames=mapping_filenames,
                batch_size=args.batch_size,
                progress_every=args.progress_every,
                sync_source=args.sync_source,
            )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
