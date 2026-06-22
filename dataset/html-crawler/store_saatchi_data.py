#!/usr/bin/env python3
"""Parse local Saatchi HTML files and write artwork/artist JSONL extracts."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from etl.saatchi import (
    extract_artist_record,
    extract_artwork_record,
    route_saatchi_page,
)


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


def _process_file(args: tuple[str, str, str]) -> dict[str, Any]:
    file_path_str, entity_filter, _data_dir = args
    path = Path(file_path_str)
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
        page_type = route_saatchi_page(html)
        if page_type is None:
            return {"status": "skip", "source_file": path.name, "reason": "unknown_page_type"}
        if entity_filter != "all" and page_type != entity_filter:
            return {"status": "skip", "source_file": path.name, "reason": "entity_filter"}

        if page_type == "artwork":
            record, missing = extract_artwork_record(path)
        else:
            record, missing = extract_artist_record(path)

        if missing:
            return {
                "status": "missing",
                "source_file": path.name,
                "entity_type": page_type,
                "missing": missing,
            }
        return {"status": "ok", "entity_type": page_type, "record": record}
    except Exception as exc:
        return {"status": "error", "source_file": path.name, "error": str(exc)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract Saatchi artwork and artist metadata from HTML files."
    )
    parser.add_argument("--data-dir", required=True, help="Directory of sha1.html files")
    parser.add_argument(
        "--output-artworks",
        default="state/saatchi_artworks.jsonl",
        help="JSONL output for artwork records",
    )
    parser.add_argument(
        "--output-artists",
        default="state/saatchi_artists.jsonl",
        help="JSONL output for artist records",
    )
    parser.add_argument(
        "--failures",
        default="state/saatchi_parse_failures.jsonl",
        help="JSONL output for parse failures",
    )
    parser.add_argument(
        "--entity",
        choices=("all", "artwork", "artist"),
        default="all",
        help="Only extract matching page types",
    )
    parser.add_argument("--workers", type=int, default=None, help="Process pool size")
    parser.add_argument("--limit", type=int, default=0, help="Parse at most N files (0 = all)")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip source_file values already present in output JSONL files",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        raise SystemExit(f"data dir not found: {data_dir}")

    artworks_path = Path(args.output_artworks)
    artists_path = Path(args.output_artists)
    failures_path = Path(args.failures)
    artworks_path.parent.mkdir(parents=True, exist_ok=True)
    artists_path.parent.mkdir(parents=True, exist_ok=True)
    failures_path.parent.mkdir(parents=True, exist_ok=True)

    resume_keys: set[str] = set()
    if args.resume:
        resume_keys |= _load_resume_keys(artworks_path)
        resume_keys |= _load_resume_keys(artists_path)

    files: list[Path] = []
    with os.scandir(data_dir) as entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.endswith(".html"):
                continue
            if entry.name in resume_keys:
                continue
            files.append(Path(entry.path))
            if args.limit and len(files) >= args.limit:
                break

    workers = args.workers or os.cpu_count() or 4
    stats = {
        "scanned": 0,
        "artworks_ok": 0,
        "artists_ok": 0,
        "skipped": 0,
        "missing": 0,
        "failed": 0,
    }

    artwork_mode = "a" if args.resume and artworks_path.is_file() else "w"
    artist_mode = "a" if args.resume and artists_path.is_file() else "w"
    failure_mode = "a" if args.resume and failures_path.is_file() else "w"

    tasks = [(str(path), args.entity, str(data_dir)) for path in files]
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
                record = result["record"]
                line = json.dumps(record, ensure_ascii=False) + "\n"
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

            if stats["scanned"] % 5000 == 0:
                print(f"progress: {json.dumps(stats, ensure_ascii=False)}", flush=True)

    print("summary:", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
