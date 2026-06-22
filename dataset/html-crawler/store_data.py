#!/usr/bin/env python3
"""Parse local Artsper HTML files and write artwork/artist JSONL extracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from etl.artsper import extract_artist_record, extract_artwork_record
from etl.urls import artsper_entity_from_url


def _process_file(args: tuple[str, str]) -> dict[str, Any]:
    file_path_str, page_url = args
    path = Path(file_path_str)
    try:
        entity = artsper_entity_from_url(page_url)
        if entity is None:
            return {"status": "skip", "source_file": path.name, "reason": "unknown_url"}
        entity_type, _external_id = entity
        if entity_type == "artwork":
            record, missing = extract_artwork_record(path, page_url)
        else:
            record, missing = extract_artist_record(path, page_url)
        if missing:
            return {
                "status": "missing",
                "source_file": path.name,
                "entity_type": entity_type,
                "missing": missing,
            }
        record["entity_type"] = entity_type
        return {"status": "ok", "entity_type": entity_type, "record": record}
    except Exception as exc:
        return {"status": "error", "source_file": path.name, "error": str(exc)}


def _load_resume_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.is_file():
        return keys
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            source_file = row.get("source_file")
            if source_file:
                keys.add(str(source_file))
    return keys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract Artsper metadata from HTML files.")
    parser.add_argument("--data-dir", required=True, help="Directory of sha1.html files")
    parser.add_argument("--urls-file", required=True, help="URL list matching HTML files")
    parser.add_argument("--output-artworks", default="state/artsper_artworks.jsonl")
    parser.add_argument("--output-artists", default="state/artsper_artists.jsonl")
    parser.add_argument("--failures", default="state/artsper_parse_failures.jsonl")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    urls_file = Path(args.urls_file)
    if not data_dir.is_dir():
        raise SystemExit(f"data dir not found: {data_dir}")
    if not urls_file.is_file():
        raise SystemExit(f"urls file not found: {urls_file}")

    artworks_path = Path(args.output_artworks)
    artists_path = Path(args.output_artists)
    failures_path = Path(args.failures)
    for path in (artworks_path, artists_path, failures_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    resume_keys: set[str] = set()
    if args.resume:
        resume_keys |= _load_resume_keys(artworks_path)
        resume_keys |= _load_resume_keys(artists_path)

    tasks: list[tuple[str, str]] = []
    with urls_file.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            url = line.strip()
            if not url or url.startswith("#"):
                continue
            filename = hashlib.sha1(url.encode()).hexdigest() + ".html"
            if filename in resume_keys:
                continue
            html_path = data_dir / filename
            if not html_path.is_file():
                continue
            tasks.append((str(html_path), url))
            if args.limit and len(tasks) >= args.limit:
                break

    workers = args.workers or os.cpu_count() or 4
    stats = {"scanned": 0, "artworks_ok": 0, "artists_ok": 0, "skipped": 0, "missing": 0, "failed": 0}

    artwork_mode = "a" if args.resume and artworks_path.is_file() else "w"
    artist_mode = "a" if args.resume and artists_path.is_file() else "w"
    failure_mode = "a" if args.resume and failures_path.is_file() else "w"

    with (
        artworks_path.open(artwork_mode, encoding="utf-8") as artworks_out,
        artists_path.open(artist_mode, encoding="utf-8") as artists_out,
        failures_path.open(failure_mode, encoding="utf-8") as failures_out,
        ProcessPoolExecutor(max_workers=max(1, workers)) as pool,
    ):
        futures = [pool.submit(_process_file, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            stats["scanned"] += 1
            status = result.get("status")
            if status == "ok":
                line = json.dumps(result["record"], ensure_ascii=False) + "\n"
                if result["entity_type"] == "artwork":
                    artworks_out.write(line)
                    stats["artworks_ok"] += 1
                else:
                    artists_out.write(line)
                    stats["artists_ok"] += 1
            elif status == "missing":
                stats["missing"] += 1
                failures_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            elif status == "error":
                stats["failed"] += 1
                failures_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            else:
                stats["skipped"] += 1

    print("summary:", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
