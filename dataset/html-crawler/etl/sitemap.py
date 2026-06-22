from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

import httpx

from etl.url_registry import entity_key_from_url, load_entity_keys, normalize_url

LOGGER = logging.getLogger(__name__)

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
DEFAULT_INDEX = "https://www.artsper.com/sitemap.xml"
_ARTSPER_CHILD_RE = ("artist", "artwork")


def _tag(local: str) -> str:
    return f"{{{SITEMAP_NS}}}{local}"


def parse_lastmod(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_url_entries(xml_bytes: bytes) -> list[tuple[str, str | None]]:
    root = ET.fromstring(xml_bytes)
    entries: list[tuple[str, str | None]] = []
    for url_el in root.findall(f".//{_tag('url')}"):
        loc_el = url_el.find(_tag("loc"))
        if loc_el is None or not loc_el.text:
            continue
        lastmod_el = url_el.find(_tag("lastmod"))
        lastmod = lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else None
        entries.append((loc_el.text.strip(), lastmod))
    return entries


def parse_child_sitemap_locs(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    locs: list[str] = []
    for sm_el in root.findall(f".//{_tag('sitemap')}"):
        loc_el = sm_el.find(_tag("loc"))
        if loc_el is not None and loc_el.text:
            locs.append(loc_el.text.strip())
    if locs:
        return locs
    return [url for url, _ in parse_url_entries(xml_bytes)]


def filter_artsper_child_sitemaps(urls: Iterable[str]) -> list[str]:
    selected: list[str] = []
    for url in urls:
        lower = url.lower()
        if any(token in lower for token in _ARTSPER_CHILD_RE):
            selected.append(url)
    return selected


@dataclass(slots=True)
class SitemapEntry:
    url: str
    lastmod: str | None
    entity_type: str
    entity_id: str

    @property
    def entity_key(self) -> tuple[str, str]:
        return (self.entity_type, self.entity_id)


@dataclass(slots=True)
class SitemapFetchStats:
    child_sitemaps: int = 0
    total_urls: int = 0
    entity_urls: int = 0
    new_entities: int = 0
    updated_entities: int = 0
    unchanged_entities: int = 0


@dataclass(slots=True)
class SitemapDiffResult:
    to_crawl: list[SitemapEntry] = field(default_factory=list)
    new_urls: list[str] = field(default_factory=list)
    updated_urls: list[str] = field(default_factory=list)
    stats: SitemapFetchStats = field(default_factory=SitemapFetchStats)

    def to_report(self) -> dict[str, Any]:
        return {
            "stats": {
                "child_sitemaps": self.stats.child_sitemaps,
                "total_urls": self.stats.total_urls,
                "entity_urls": self.stats.entity_urls,
                "new_entities": self.stats.new_entities,
                "updated_entities": self.stats.updated_entities,
                "unchanged_entities": self.stats.unchanged_entities,
                "to_crawl": len(self.to_crawl),
            },
            "new_urls_sample": self.new_urls[:50],
            "updated_urls_sample": self.updated_urls[:50],
        }


def load_lastmod_state(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    entities = payload.get("entities")
    if isinstance(entities, dict):
        return {str(k): str(v) for k, v in entities.items() if v}
    return {}


def save_lastmod_state(path: Path, entities: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "entities": dict(sorted(entities.items())),
        "last_fetch_at": datetime.now().astimezone().isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _entity_state_key(entity_type: str, entity_id: str) -> str:
    return f"{entity_type}:{entity_id}"


def fetch_sitemap_bytes(client: httpx.Client, url: str) -> bytes:
    response = client.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def fetch_artsper_sitemap_entries(
    index_url: str = DEFAULT_INDEX,
    *,
    concurrency: int = 8,
    client: httpx.Client | None = None,
) -> list[SitemapEntry]:
    own_client = client is None
    http = client or httpx.Client(http2=True, headers={"User-Agent": "artsper-sitemap-fetch/1.0"})
    try:
        index_xml = fetch_sitemap_bytes(http, index_url)
        child_urls = filter_artsper_child_sitemaps(parse_child_sitemap_locs(index_xml))
        LOGGER.info("artsper sitemap child maps=%s", len(child_urls))

        entries: list[SitemapEntry] = []
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {pool.submit(fetch_sitemap_bytes, http, child_url): child_url for child_url in child_urls}
            for future in as_completed(futures):
                child_url = futures[future]
                try:
                    xml_bytes = future.result()
                except Exception as exc:
                    LOGGER.warning("child sitemap failed url=%s error=%s", child_url, exc)
                    continue
                for url, lastmod in parse_url_entries(xml_bytes):
                    normalized = normalize_url(url)
                    key = entity_key_from_url(normalized)
                    if key is None:
                        continue
                    entity_type, entity_id = key
                    entries.append(
                        SitemapEntry(
                            url=normalized,
                            lastmod=lastmod,
                            entity_type=entity_type,
                            entity_id=entity_id,
                        )
                    )
        return entries
    finally:
        if own_client:
            http.close()


def diff_sitemap_entries(
    entries: Iterable[SitemapEntry],
    *,
    known_entity_keys: set[tuple[str, str]] | None = None,
    lastmod_state: dict[str, str] | None = None,
    include_updates: bool = True,
) -> SitemapDiffResult:
    known = known_entity_keys or set()
    state = lastmod_state or {}
    result = SitemapDiffResult()
    best_by_key: dict[tuple[str, str], SitemapEntry] = {}

    for entry in entries:
        result.stats.total_urls += 1
        key = entry.entity_key
        current = best_by_key.get(key)
        if current is None:
            best_by_key[key] = entry
            continue
        current_dt = parse_lastmod(current.lastmod)
        entry_dt = parse_lastmod(entry.lastmod)
        if entry_dt and (current_dt is None or entry_dt > current_dt):
            best_by_key[key] = entry

    result.stats.entity_urls = len(best_by_key)

    for key, entry in sorted(best_by_key.items(), key=lambda item: item[1].url):
        state_key = _entity_state_key(*key)
        stored_lastmod = state.get(state_key)
        entry_lastmod = entry.lastmod

        if key not in known:
            result.stats.new_entities += 1
            result.new_urls.append(entry.url)
            result.to_crawl.append(entry)
            continue

        if not include_updates:
            result.stats.unchanged_entities += 1
            continue

        if entry_lastmod and stored_lastmod:
            entry_dt = parse_lastmod(entry_lastmod)
            stored_dt = parse_lastmod(stored_lastmod)
            if entry_dt and stored_dt and entry_dt > stored_dt:
                result.stats.updated_entities += 1
                result.updated_urls.append(entry.url)
                result.to_crawl.append(entry)
                continue
        result.stats.unchanged_entities += 1

    return result


def build_lastmod_state_from_entries(entries: Iterable[SitemapEntry]) -> dict[str, str]:
    state: dict[str, str] = {}
    for entry in entries:
        if not entry.lastmod:
            continue
        state_key = _entity_state_key(entry.entity_type, entry.entity_id)
        current = state.get(state_key)
        if current is None or (parse_lastmod(entry.lastmod) or datetime.min) > (parse_lastmod(current) or datetime.min):
            state[state_key] = entry.lastmod
    return state


def write_url_list(path: Path, urls: Iterable[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for url in urls:
            handle.write(url + "\n")
            count += 1
    return count


def known_keys_from_sources(
    *,
    known_paths: Iterable[Path] | None = None,
    known_db_url: str | None = None,
    source: str = "artsper",
) -> set[tuple[str, str]]:
    from etl.url_registry import load_entity_keys_from_db

    keys: set[tuple[str, str]] = set()
    if known_paths:
        keys |= load_entity_keys(known_paths)
    if known_db_url:
        keys |= load_entity_keys_from_db(known_db_url, source=source)
    return keys
