#!/usr/bin/env python3
"""Parse local Artsy HTML files and write entity JSONL extracts."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from etl.artsy import EXTRACTORS, route_artsy_page
from mapping_utils import iter_mapping_rows


def _load_resume_keys(*paths: Path) -> set[str]:
    keys: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
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


def _process_file(args: tuple[str, str, str, str]) -> dict[str, Any]:
    file_path_str, entity_filter, data_dir, default_url = args
    path = Path(file_path_str)
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
        page_type = route_artsy_page(html, default_url or None)
        if page_type is None:
            return {"status": "skip", "source_file": path.name, "reason": "unknown_page_type"}
        if entity_filter != "all" and page_type != entity_filter:
            return {"status": "skip", "source_file": path.name, "reason": "entity_filter"}

        extractor = EXTRACTORS.get(page_type)
        if extractor is None:
            return {"status": "skip", "source_file": path.name, "reason": "no_extractor"}
        record, missing = extractor(path, default_url or None)
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
    parser = argparse.ArgumentParser(description="Extract Artsy metadata from HTML files.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--state-dir", default="state/artsy")
    parser.add_argument(
        "--entity",
        choices=("all", "artwork", "artist", "partner", "show", "fair"),
        default="all",
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=None,
        help="Only extract HTML filenames listed in crawl results JSONL",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="With --mapping-file, re-extract mapped files even if already in JSONL",
    )
    parser.add_argument(
        "--output-suffix",
        default="",
        help="Write to artsy_{entity}s{suffix}.jsonl (e.g. _batch)",
    )
    return parser


def _output_path(state_dir: Path, entity: str, suffix: str = "") -> Path:
    return state_dir / f"artsy_{entity}s{suffix}.jsonl"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    entity_types = (
        ["artwork", "artist", "partner", "show", "fair"]
        if args.entity == "all"
        else [args.entity]
    )
    outputs = {entity: _output_path(state_dir, entity, args.output_suffix) for entity in entity_types}
    failures_path = state_dir / f"artsy_parse_failures{args.output_suffix}.jsonl"

    resume_keys: set[str] = set()
    if args.resume:
        resume_keys = _load_resume_keys(*outputs.values())

    mapping_filenames: set[str] | None = None
    if args.mapping_file is not None:
        mapping_filenames = {filename for _url, filename, _status in iter_mapping_rows(args.mapping_file)}

    files: list[Path] = []
    if mapping_filenames is not None:
        for filename in sorted(mapping_filenames):
            path = data_dir / filename
            if not path.is_file():
                continue
            if args.resume and not args.refresh and path.name in resume_keys:
                continue
            files.append(path)
            if args.limit and len(files) >= args.limit:
                break
    else:
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
        "ok": 0,
        "skipped": 0,
        "missing": 0,
        "failed": 0,
    }

    batch_mode = mapping_filenames is not None
    handles = {
        entity: outputs[entity].open(
            "w" if batch_mode else ("a" if args.resume and outputs[entity].is_file() else "w"),
            encoding="utf-8",
        )
        for entity in entity_types
    }
    failure_mode = "w" if batch_mode else ("a" if args.resume and failures_path.is_file() else "w")

    tasks = [(str(path), args.entity, str(data_dir), "") for path in files]
    with (
        failures_path.open(failure_mode, encoding="utf-8") as failures_out,
        ProcessPoolExecutor(max_workers=max(1, workers)) as pool,
    ):
        futures = [pool.submit(_process_file, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            stats["scanned"] += 1
            status = result.get("status")
            if status == "ok":
                entity_type = result["entity_type"]
                handles[entity_type].write(json.dumps(result["record"], ensure_ascii=False) + "\n")
                stats["ok"] += 1
            elif status in {"missing", "error"}:
                stats["missing" if status == "missing" else "failed"] += 1
                failures_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            else:
                stats["skipped"] += 1

            if stats["scanned"] % 5000 == 0:
                print(f"progress: {json.dumps(stats, ensure_ascii=False)}", flush=True)

    for handle in handles.values():
        handle.close()

    print("summary:", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
