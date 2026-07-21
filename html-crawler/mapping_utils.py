"""Helpers for mapping crawl results to HTML files on disk."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterator

from etl.url_registry import html_filename_for_url


def iter_mapping_rows(mapping_file: Path) -> Iterator[tuple[str, str, int]]:
    """Yield (url, filename, status_code) from JSONL or CSV mapping files."""
    suffix = mapping_file.suffix.lower()
    if suffix == ".jsonl":
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
                filename = str(row.get("filename") or html_filename_for_url(url)).strip()
                status_code = int(row.get("status_code") or 0)
                yield url, filename, status_code
        return

    with mapping_file.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            filename = str(row.get("filename") or html_filename_for_url(url)).strip()
            try:
                status_code = int(row.get("status_code") or 0)
            except ValueError:
                status_code = 0
            yield url, filename, status_code


def iter_url_list_rows(
    urls_file: Path,
    html_dir: Path,
    *,
    require_html: bool = True,
) -> Iterator[tuple[str, str, int]]:
    """Yield (url, filename, 200) for URLs whose HTML file exists."""
    with urls_file.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            url = line.strip()
            if not url or url.startswith("#"):
                continue
            filename = html_filename_for_url(url)
            html_path = html_dir / filename
            if require_html and not html_path.is_file():
                continue
            yield url, filename, 200
