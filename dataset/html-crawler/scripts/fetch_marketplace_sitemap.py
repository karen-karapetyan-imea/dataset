#!/usr/bin/env python3
"""Fetch marketplace URLs from sitemap.xml and select new/updated entities only."""

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
    DEFAULT_ARTSPER_INDEX,
    DEFAULT_ARTSY_SITEMAPS,
    DEFAULT_SAATCHI_INDEX,
    build_lastmod_state_from_entries,
    diff_sitemap_entries,
    fetch_artsper_sitemap_entries,
    fetch_artsy_sitemap_entries,
    fetch_saatchi_sitemap_entries,
    known_keys_from_sources,
    load_lastmod_state,
    save_lastmod_state,
    write_url_list,
)

LOGGER = logging.getLogger(__name__)

_FETCHERS = {
    "artsper": lambda args: fetch_artsper_sitemap_entries(args.index, concurrency=args.concurrency),
    "saatchi": lambda args: fetch_saatchi_sitemap_entries(args.index, concurrency=args.concurrency),
    "artsy": lambda args: fetch_artsy_sitemap_entries(args.artsy_sitemaps, concurrency=args.concurrency),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch marketplace URLs from sitemap and diff against known state.")
    parser.add_argument("--source", choices=("artsper", "saatchi", "artsy"), default="artsper")
    parser.add_argument("--index", default=None, help="Sitemap index URL (artsper/saatchi)")
    parser.add_argument(
        "--artsy-sitemaps",
        nargs="*",
        default=list(DEFAULT_ARTSY_SITEMAPS),
        help="Artsy sitemap URLs",
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--known", nargs="*", type=Path, default=())
    parser.add_argument("--known-db-url", default=None)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--snapshot", type=Path, default=None, help="Persist full entry snapshot JSON")
    parser.add_argument("--out-all", type=Path, default=None)
    parser.add_argument("--out-new", type=Path, default=Path("state/urls_new.txt"))
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--no-updates", action="store_true")
    parser.add_argument("--update-state", action="store_true")
    parser.add_argument(
        "--update-state-only",
        action="store_true",
        help="Refresh lastmod state from --snapshot without fetching sitemap",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _default_paths(source: str) -> dict[str, Path]:
    prefix = Path(f"state/{source}")
    return {
        "state": prefix / "sitemap_lastmod.json",
        "out_all": prefix / "sitemap_urls.txt",
        "report": prefix / "sitemap_diff.json",
        "snapshot": prefix / "sitemap_entries.snapshot.json",
    }


def _default_index(source: str) -> str:
    if source == "saatchi":
        return DEFAULT_SAATCHI_INDEX
    return DEFAULT_ARTSPER_INDEX


def _load_snapshot(path: Path) -> list[dict[str, str | None]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _save_snapshot(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "entries": [
            {
                "url": entry.url,
                "lastmod": entry.lastmod,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
            }
            for entry in entries
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    defaults = _default_paths(args.source)
    state_path = args.state or defaults["state"]
    out_all = args.out_all or defaults["out_all"]
    report_path = args.report or defaults["report"]
    snapshot_path = args.snapshot or defaults["snapshot"]

    if args.update_state_only:
        if not snapshot_path.is_file():
            raise SystemExit(f"snapshot not found: {snapshot_path}")
        from etl.sitemap import SitemapEntry

        raw_entries = _load_snapshot(snapshot_path)
        entries = [
            SitemapEntry(
                url=str(item["url"]),
                lastmod=item.get("lastmod"),
                entity_type=str(item["entity_type"]),
                entity_id=str(item["entity_id"]),
            )
            for item in raw_entries
        ]
        save_lastmod_state(state_path, build_lastmod_state_from_entries(entries))
        LOGGER.info("updated lastmod state from snapshot path=%s entries=%s", state_path, len(entries))
        return

    if args.index is None:
        args.index = _default_index(args.source)

    entries = _FETCHERS[args.source](args)
    LOGGER.info("fetched entity entries=%s source=%s", len(entries), args.source)

    known_keys = known_keys_from_sources(
        known_paths=args.known,
        known_db_url=args.known_db_url,
        source=args.source,
    )
    LOGGER.info("known entities=%s", len(known_keys))

    lastmod_state = load_lastmod_state(state_path)
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
        write_url_list(out_all, all_urls)
        write_url_list(args.out_new, crawl_urls)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(result.to_report(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _save_snapshot(snapshot_path, entries)
        if args.update_state:
            save_lastmod_state(state_path, build_lastmod_state_from_entries(entries))
            LOGGER.info("updated lastmod state path=%s", state_path)

    if len(crawl_urls) == 0:
        LOGGER.info("nothing new or updated in sitemap")


if __name__ == "__main__":
    main()
