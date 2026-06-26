from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urlsplit, urlunsplit

from etl.urls import artsper_entity_from_url, entity_from_url, saatchi_entity_from_url

_KATANA_JSON_URL_KEYS = ("url", "request", "endpoint", "input")

_MARKETPLACE_TABLES: dict[str, dict[str, str]] = {
    "artsper": {
        "artist": "arts_artists",
        "artwork": "arts_artworks",
    },
    "saatchi": {
        "artist": "saatchi_artists",
        "artwork": "saatchi_artworks",
    },
    "artsy": {
        "artist": "artsy_artists",
        "artwork": "artsy_artworks",
        "partner": "artsy_partners",
        "show": "artsy_shows",
        "fair": "artsy_fairs",
    },
}


def normalize_url(url: str) -> str:
    """Lowercase host, drop query/fragment, strip trailing slash."""
    text = (url or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def html_filename_for_url(url: str) -> str:
    """Same basename as the HTML crawler (sha1 of URL)."""
    return hashlib.sha1(url.encode()).hexdigest() + ".html"


def entity_key_from_url(url: str, *, source: str = "artsper") -> tuple[str, str] | None:
    """Stable (entity_type, external_id) for marketplace entity URLs."""
    normalized = normalize_url(url) or url
    return entity_from_url(normalized, source=source)


def iter_urls_from_lines(path: Path) -> Iterator[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            url = line.strip()
            if url and not url.startswith("#"):
                yield url


def iter_urls_from_jsonl(path: Path) -> Iterator[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            for key in _KATANA_JSON_URL_KEYS:
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    yield value.strip()
                    break
            else:
                request = row.get("request")
                if isinstance(request, dict):
                    endpoint = request.get("endpoint")
                    if isinstance(endpoint, str) and endpoint.strip():
                        yield endpoint.strip()


def load_urls(paths: Iterable[Path]) -> set[str]:
    urls: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        if path.suffix.lower() == ".jsonl":
            iterator: Iterator[str] = iter_urls_from_jsonl(path)
        else:
            iterator = iter_urls_from_lines(path)
        for url in iterator:
            normalized = normalize_url(url)
            if normalized:
                urls.add(normalized)
    return urls


def load_entity_keys(paths: Iterable[Path], *, source: str = "artsper") -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for url in load_urls(paths):
        key = entity_key_from_url(url, source=source)
        if key is not None:
            keys.add(key)
    return keys


def load_entity_keys_from_db(db_url: str, *, source: str = "artsper") -> set[tuple[str, str]]:
    """Load known entity ids from marketplace tables."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for --known-db-url") from exc

    tables = _MARKETPLACE_TABLES.get(source)
    if tables is None:
        raise ValueError(f"unsupported marketplace source: {source}")

    keys: set[tuple[str, str]] = set()
    with psycopg.connect(db_url) as connection:
        with connection.cursor() as cursor:
            for entity_type, table_name in tables.items():
                cursor.execute(f"SELECT id::text FROM public.{table_name}")
                for (external_id,) in cursor.fetchall():
                    if external_id is not None:
                        keys.add((entity_type, str(external_id)))
    return keys


@dataclass(slots=True)
class UrlDiffStats:
    incoming_lines: int = 0
    normalized_urls: int = 0
    entity_urls: int = 0
    duplicate_entities: int = 0
    known_entities: int = 0
    new_entities: int = 0
    invalid_urls: int = 0


@dataclass(slots=True)
class UrlDiffResult:
    new_urls: list[str] = field(default_factory=list)
    known_urls: list[str] = field(default_factory=list)
    invalid_urls: list[str] = field(default_factory=list)
    stats: UrlDiffStats = field(default_factory=UrlDiffStats)

    def to_report(self) -> dict[str, Any]:
        return {
            "stats": {
                "incoming_lines": self.stats.incoming_lines,
                "normalized_urls": self.stats.normalized_urls,
                "entity_urls": self.stats.entity_urls,
                "duplicate_entities": self.stats.duplicate_entities,
                "known_entities": self.stats.known_entities,
                "new_entities": self.stats.new_entities,
                "invalid_urls": self.stats.invalid_urls,
            },
            "new_urls": self.new_urls,
            "known_urls": self.known_urls[:100],
            "invalid_urls_sample": self.invalid_urls[:50],
        }


def diff_entity_urls(
    incoming_paths: Iterable[Path],
    *,
    source: str = "artsper",
    known_paths: Iterable[Path] | None = None,
    known_entity_keys: set[tuple[str, str]] | None = None,
) -> UrlDiffResult:
    """Compare URL dump against known crawl/import state, deduped by entity id."""
    result = UrlDiffResult()
    known = set(known_entity_keys or ())
    if known_paths:
        known |= load_entity_keys(known_paths, source=source)

    seen_incoming: set[tuple[str, str]] = set()
    best_url_for_key: dict[tuple[str, str], str] = {}

    for path in incoming_paths:
        if not path.is_file():
            continue
        iterator = iter_urls_from_jsonl(path) if path.suffix.lower() == ".jsonl" else iter_urls_from_lines(path)
        for raw in iterator:
            result.stats.incoming_lines += 1
            normalized = normalize_url(raw)
            if not normalized:
                continue
            result.stats.normalized_urls += 1
            key = entity_key_from_url(normalized, source=source)
            if key is None:
                result.stats.invalid_urls += 1
                result.invalid_urls.append(normalized)
                continue
            result.stats.entity_urls += 1
            if key in seen_incoming:
                result.stats.duplicate_entities += 1
                continue
            seen_incoming.add(key)
            best_url_for_key[key] = normalized

    for key, url in sorted(best_url_for_key.items(), key=lambda item: item[1]):
        if key in known:
            result.stats.known_entities += 1
            result.known_urls.append(url)
        else:
            result.stats.new_entities += 1
            result.new_urls.append(url)

    return result


def diff_artsper_urls(
    incoming_paths: Iterable[Path],
    *,
    known_paths: Iterable[Path] | None = None,
    known_entity_keys: set[tuple[str, str]] | None = None,
) -> UrlDiffResult:
    return diff_entity_urls(
        incoming_paths,
        source="artsper",
        known_paths=known_paths,
        known_entity_keys=known_entity_keys,
    )


def write_url_list(path: Path, urls: Iterable[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for url in urls:
            handle.write(url + "\n")
            count += 1
    return count
