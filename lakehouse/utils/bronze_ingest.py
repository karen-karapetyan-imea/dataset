"""Shared Bronze ingestion logic."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from lakehouse.schemas.bronze import BRONZE_ARROW_SCHEMA
from lakehouse.utils.compression import compress_html
from lakehouse.utils.storage import (
    bronze_partition_path,
    crawl_date_from_timestamp,
    next_part_path,
    parse_crawl_timestamp,
    sha1_url,
    sniff_content_type,
)

LOGGER = logging.getLogger(__name__)


def iter_mapping_rows(mapping_file: Path) -> Iterator[dict[str, Any]]:
    with mapping_file.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            yield row


def build_bronze_record(
    row: dict[str, Any],
    *,
    source: str,
    html_dir: Path,
    crawl_job_id: str,
    crawl_date_override: str | None = None,
    html_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    url = str(row.get("url") or "").strip()
    filename = str(row.get("filename") or f"{sha1_url(url)}.html").strip()
    crawl_ts = parse_crawl_timestamp(str(row.get("timestamp") or ""))
    crawl_date = crawl_date_override or crawl_date_from_timestamp(crawl_ts)

    html_bytes: bytes | None = None
    content_length: int | None = None
    search_dirs = html_dirs or [html_dir]
    for directory in search_dirs:
        candidate = directory / filename
        if candidate.is_file():
            html_bytes = candidate.read_bytes()
            content_length = candidate.stat().st_size
            break

    compressed = compress_html(html_bytes) if html_bytes is not None else None

    return {
        "url": url,
        "url_sha1": sha1_url(url),
        "source": source,
        "crawl_timestamp": crawl_ts,
        "crawl_date": crawl_date,
        "status_code": int(row.get("status_code") or 0),
        "response_time_ms": int(row.get("duration_ms") or 0),
        "headers_json": row.get("headers_json"),
        "content_type": row.get("content_type") or sniff_content_type(html_bytes),
        "content_length": content_length,
        "html": compressed,
        "proxy_id": row.get("proxy_id"),
        "crawl_job_id": crawl_job_id,
        "error_message": str(row.get("error") or ""),
        "is_blocked": bool(row.get("block_detected") or False),
    }


def write_bronze_batch(
    records: list[dict[str, Any]],
    *,
    source: str,
    crawl_date: str,
    data_root: Path,
) -> Path:
    partition_dir = bronze_partition_path(source, crawl_date, data_root)
    output_path = next_part_path(partition_dir)

    table_records = []
    for record in records:
        table_records.append({key: record[key] for key in BRONZE_ARROW_SCHEMA.names})

    table = pa.Table.from_pylist(table_records, schema=BRONZE_ARROW_SCHEMA)
    pq.write_table(table, output_path, compression="zstd")
    LOGGER.info("Wrote %s bronze rows to %s", len(records), output_path)
    return output_path


def ingest_mapping_to_bronze(
    *,
    mapping_file: Path,
    html_dir: Path,
    source: str,
    crawl_date: str | None,
    crawl_job_id: str,
    data_root: Path,
    batch_size: int = 10_000,
    html_dirs: list[Path] | None = None,
) -> dict[str, int]:
    stats = {"rows": 0, "partitions": 0, "batches": 0}
    batch_by_partition: dict[str, list[dict[str, Any]]] = {}

    for row in iter_mapping_rows(mapping_file):
        record = build_bronze_record(
            row,
            source=source,
            html_dir=html_dir,
            crawl_job_id=crawl_job_id,
            crawl_date_override=crawl_date,
            html_dirs=html_dirs,
        )
        partition_key = f"{record['source']}:{record['crawl_date']}"
        batch_by_partition.setdefault(partition_key, []).append(record)
        stats["rows"] += 1

        if len(batch_by_partition[partition_key]) >= batch_size:
            write_bronze_batch(
                batch_by_partition[partition_key],
                source=record["source"],
                crawl_date=record["crawl_date"],
                data_root=data_root,
            )
            stats["batches"] += 1
            stats["partitions"] += 1
            batch_by_partition[partition_key] = []

        if stats["rows"] % 50_000 == 0:
            LOGGER.info("Processed %s mapping rows", stats["rows"])

    for partition_key, records in batch_by_partition.items():
        if not records:
            continue
        source_key, date_key = partition_key.split(":", 1)
        write_bronze_batch(records, source=source_key, crawl_date=date_key, data_root=data_root)
        stats["batches"] += 1
        stats["partitions"] += 1

    return stats
