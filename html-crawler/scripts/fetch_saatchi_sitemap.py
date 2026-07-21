#!/usr/bin/env python3
"""Fetch Saatchi URLs from sitemap.xml and select new/updated entities only."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.sitemap import (  # noqa: E402
    DEFAULT_SAATCHI_INDEX,
    build_lastmod_state_from_entries,
    diff_sitemap_entries,
    fetch_saatchi_sitemap_entries,
    known_keys_from_sources,
    load_lastmod_state,
    save_lastmod_state,
    write_url_list,
)

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Saatchi artist/artwork URLs from sitemap.xml")
    parser.add_argument("--index", default=DEFAULT_SAATCHI_INDEX, help="Sitemap index URL")
    parser.add_argument("--concurrency", type=int, default=3, help="Parallel child-sitemap fetches (default 3)")
    parser.add_argument("--known", nargs="*", type=Path, default=(), help="Known crawl sources (results.jsonl)")
    parser.add_argument("--known-db-url", default=None, help="Also treat saatchi_* table ids as known")
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("state/saatchi_sitemap_lastmod.json"),
        help="Persist lastmod per entity for update detection",
    )
    parser.add_argument(
        "--out-all",
        type=Path,
        default=Path("state/urls_saatchiart.txt"),
        help="Write all entity URLs from sitemap",
    )
    parser.add_argument(
        "--out-new",
        type=Path,
        default=Path("state/urls_saatchi_new.txt"),
        help="Write new + updated URLs to crawl",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("state/saatchi_sitemap_diff.json"),
        help="JSON report of new vs updated vs unchanged",
    )
    parser.add_argument(
        "--no-updates",
        action="store_true",
        help="Only crawl entities never seen before (skip lastmod updates)",
    )
    parser.add_argument(
        "--update-state",
        action="store_true",
        help="Refresh lastmod state file from this sitemap fetch",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch + report only")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    entries = fetch_saatchi_sitemap_entries(args.index, concurrency=args.concurrency)
    LOGGER.info("fetched entity entries=%s", len(entries))

    known_keys = known_keys_from_sources(
        known_paths=args.known,
        known_db_url=args.known_db_url,
        source="saatchi",
    )
    LOGGER.info("known entities=%s", len(known_keys))

    lastmod_state = load_lastmod_state(args.state)
    result = diff_sitemap_entries(
        entries,
        known_entity_keys=known_keys,
        lastmod_state=lastmod_state,
        include_updates=not args.no_updates,
    )

    crawl_urls = [entry.url for entry in result.to_crawl]
    all_urls = sorted({entry.url for entry in entries})

    LOGGER.info(
        "diff entity_urls=%s new=%s updated=%s unchanged=%s to_crawl=%s",
        result.stats.entity_urls,
        result.stats.new_entities,
        result.stats.updated_entities,
        result.stats.unchanged_entities,
        len(crawl_urls),
    )

    if not args.dry_run:
        write_url_list(args.out_all, all_urls)
        write_url_list(args.out_new, crawl_urls)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result.to_report(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.update_state:
            save_lastmod_state(args.state, build_lastmod_state_from_entries(entries))
            LOGGER.info("updated lastmod state path=%s", args.state)

    if len(crawl_urls) == 0:
        LOGGER.info("nothing new or updated in sitemap")


if __name__ == "__main__":
    main()
