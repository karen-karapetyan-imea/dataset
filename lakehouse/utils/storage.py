"""Path helpers and storage utilities for the local lakehouse."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
LAKEHOUSE_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATA_ROOT = Path(
    os.environ.get("LAKEHOUSE_DATA_ROOT", str(REPO_ROOT))
).resolve()
DEFAULT_HTML_CRAWLER_ROOT = Path(
    os.environ.get("HTML_CRAWLER_ROOT", str(REPO_ROOT / "html-crawler"))
).resolve()

SOURCE_HOSTS = {
    "saatchiart.com": "saatchi",
    "www.saatchiart.com": "saatchi",
    "artsper.com": "artsper",
    "www.artsper.com": "artsper",
    "artsy.net": "artsy",
    "www.artsy.net": "artsy",
}


def data_root() -> Path:
    return DEFAULT_DATA_ROOT


def html_crawler_root() -> Path:
    return DEFAULT_HTML_CRAWLER_ROOT


def sha1_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def infer_source(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    return SOURCE_HOSTS.get(host)


def parse_crawl_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def crawl_date_from_timestamp(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).date().isoformat()


def bronze_partition_path(source: str, crawl_date: str, data_root: Path | None = None) -> Path:
    root = data_root or DEFAULT_DATA_ROOT
    return root / "bronze" / f"source={source}" / f"crawl_date={crawl_date}"


def silver_artworks_path(data_root: Path | None = None) -> Path:
    return (data_root or DEFAULT_DATA_ROOT) / "silver" / "artworks"


def silver_artists_path(data_root: Path | None = None) -> Path:
    return (data_root or DEFAULT_DATA_ROOT) / "silver" / "artists"


def silver_failures_path(source: str, crawl_date: str, data_root: Path | None = None) -> Path:
    root = data_root or DEFAULT_DATA_ROOT
    return root / "silver" / "_failures" / f"source={source}" / f"crawl_date={crawl_date}"


def gold_table_path(table_name: str, data_root: Path | None = None) -> Path:
    return (data_root or DEFAULT_DATA_ROOT) / "gold" / table_name


def next_part_path(partition_dir: Path, prefix: str = "part") -> Path:
    partition_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(partition_dir.glob(f"{prefix}-*.parquet"))
    if not existing:
        return partition_dir / f"{prefix}-00000.parquet"
    last = existing[-1].stem
    match = re.search(r"(\d+)$", last)
    next_idx = int(match.group(1)) + 1 if match else len(existing)
    return partition_dir / f"{prefix}-{next_idx:05d}.parquet"


def sniff_content_type(data: bytes | None) -> str | None:
    if not data:
        return None
    sample = data[:256].lstrip()
    if sample.startswith(b"<!DOCTYPE") or sample.startswith(b"<html") or sample.startswith(b"<HTML"):
        return "text/html"
    return "application/octet-stream"


def ensure_lakehouse_paths() -> None:
    root = data_root()
    for sub in ("bronze", "silver", "gold"):
        (root / sub).mkdir(parents=True, exist_ok=True)
