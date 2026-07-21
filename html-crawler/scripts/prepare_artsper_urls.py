#!/usr/bin/env python3
"""Filter Katana URL dumps and diff against known Artsper crawl/import state."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.url_registry import (  # noqa: E402
    diff_artsper_urls,
    load_entity_keys_from_db,
    write_url_list,
)

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filter Artsper artist/artwork URLs from Katana output and "
            "keep only entities not already crawled/imported."
        )
    )
    parser.add_argument(
        "incoming",
        nargs="+",
        type=Path,
        help="Katana output file(s): plain text or JSONL",
    )
    parser.add_argument(
        "--known",
        nargs="*",
        type=Path,
        default=(),
        help="Known URL sources (e.g. results.jsonl, urls_artsper.txt)",
    )
    parser.add_argument(
        "--known-db-url",
        default=None,
        help="Also treat catalog_artists/catalog_artworks external_id as known",
    )
    parser.add_argument(
        "--out-new",
        type=Path,
        default=Path("state/urls_new.txt"),
        help="Write new entity URLs here (default: state/urls_new.txt)",
    )
    parser.add_argument(
        "--out-known",
        type=Path,
        default=None,
        help="Optional: write already-known entity URLs",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("state/url_diff.json"),
        help="JSON diff report (default: state/url_diff.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats only; do not write output files",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    known_keys = None
    if args.known_db_url:
        known_keys = load_entity_keys_from_db(args.known_db_url)
        LOGGER.info("loaded known entities from db count=%s", len(known_keys))

    result = diff_artsper_urls(
        args.incoming,
        known_paths=args.known,
        known_entity_keys=known_keys,
    )
    stats = result.stats
    LOGGER.info(
        "diff incoming_lines=%s entity_urls=%s known=%s new=%s invalid=%s",
        stats.incoming_lines,
        stats.entity_urls,
        stats.known_entities,
        stats.new_entities,
        stats.invalid_urls,
    )

    if not args.dry_run:
        write_url_list(args.out_new, result.new_urls)
        LOGGER.info("wrote new urls count=%s path=%s", len(result.new_urls), args.out_new)
        if args.out_known is not None:
            write_url_list(args.out_known, result.known_urls)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result.to_report(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        LOGGER.info("wrote report path=%s", args.report)

    if stats.new_entities == 0:
        LOGGER.info("no new Artsper entities to crawl")


if __name__ == "__main__":
    main()
