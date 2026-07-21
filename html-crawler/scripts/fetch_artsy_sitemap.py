#!/usr/bin/env python3
"""Fetch Artsy artist/artwork URLs from sitemap indexes and select new/updated entities."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from proxy_pool import load_proxy_list  # noqa: E402
from etl.sitemap import (  # noqa: E402
    DEFAULT_ARTSY_INDEXES,
    build_lastmod_state_from_entries,
    diff_sitemap_entries,
    fetch_artsy_sitemap_entries,
    known_keys_from_sources,
    load_lastmod_state,
    save_lastmod_state,
    write_url_list,
)

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Artsy artist/artwork URLs from sitemap-artists.xml / sitemap-artworks.xml"
    )
    parser.add_argument(
        "--indexes",
        nargs="+",
        default=list(DEFAULT_ARTSY_INDEXES),
        help="Sitemap index URLs (default: artists + artworks)",
    )
    parser.add_argument("--concurrency", type=int, default=8, help="Parallel sitemap fetches")
    parser.add_argument(
        "--known",
        nargs="*",
        type=Path,
        default=(),
        help="Known crawl sources (results.jsonl / URL lists)",
    )
    parser.add_argument(
        "--known-db-url",
        default=None,
        help="Accepted for CLI parity; ignored until Artsy tables exist",
    )
    parser.add_argument(
        "--proxy-file",
        default=None,
        help="Proxy list file (host:port:user:pass). Also uses CRAWLER_PROXY env.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("state/artsy_sitemap_lastmod.json"),
        help="Persist lastmod per entity for update detection",
    )
    parser.add_argument(
        "--out-all",
        type=Path,
        default=Path("state/artsy_sitemap_urls.txt"),
        help="Write all entity URLs from sitemap",
    )
    parser.add_argument(
        "--out-new",
        type=Path,
        default=Path("state/artsy_urls_new.txt"),
        help="Write new + updated URLs to crawl",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("state/artsy_sitemap_diff.json"),
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

    proxies = load_proxy_list(args.proxy_file)
    proxy = proxies[0] if proxies else None
    if proxy:
        LOGGER.info("using proxy for artsy sitemap fetch")
    elif args.proxy_file:
        LOGGER.warning("proxy-file set but no valid proxies loaded")

    entries = fetch_artsy_sitemap_entries(
        args.indexes,
        concurrency=args.concurrency,
        proxy=proxy,
    )
    LOGGER.info("fetched entity entries=%s", len(entries))

    known_keys = known_keys_from_sources(
        known_paths=args.known,
        known_db_url=args.known_db_url,
        source="artsy",
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
