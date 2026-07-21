"""Extensible marketplace parser registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lakehouse.utils.storage import html_crawler_root

ExtractFn = Callable[[Path, str | None], tuple[dict[str, Any], list[str]]]
RouteFn = Callable[[str, str], str | None]
EntityFn = Callable[[str], tuple[str, str] | None]


@dataclass(frozen=True)
class MarketplaceParser:
    source: str
    route_page: RouteFn | None
    extract_artwork: ExtractFn
    extract_artist: ExtractFn
    entity_from_url: EntityFn


def _ensure_crawler_path() -> None:
    import sys

    root = str(html_crawler_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _build_registry() -> dict[str, MarketplaceParser]:
    _ensure_crawler_path()
    from etl.artsper import extract_artwork_record as artsper_extract_artwork
    from etl.artsper import extract_artist_record as artsper_extract_artist
    from etl.saatchi import extract_artwork_record as saatchi_extract_artwork
    from etl.saatchi import extract_artist_record as saatchi_extract_artist
    from etl.saatchi import route_saatchi_page
    from etl.urls import artsper_entity_from_url, artsy_entity_from_url, saatchi_artwork_from_url, saatchi_artist_from_url

    from lakehouse.parsers.artsy import extract_artwork_record as artsy_extract_artwork
    from lakehouse.parsers.artsy import extract_artist_record as artsy_extract_artist

    def saatchi_entity(url: str) -> tuple[str, str] | None:
        artwork = saatchi_artwork_from_url(url)
        if artwork:
            return "artwork", artwork[1]
        artist = saatchi_artist_from_url(url)
        if artist:
            return "artist", artist
        return None

    def route_saatchi(html: str, url: str) -> str | None:
        routed = route_saatchi_page(html)
        if routed:
            return routed
        entity = saatchi_entity(url)
        return entity[0] if entity else None

    def route_from_url(_html: str, url: str, entity_fn: EntityFn) -> str | None:
        entity = entity_fn(url)
        return entity[0] if entity else None

    return {
        "saatchi": MarketplaceParser(
            source="saatchi",
            route_page=route_saatchi,
            extract_artwork=saatchi_extract_artwork,
            extract_artist=saatchi_extract_artist,
            entity_from_url=saatchi_entity,
        ),
        "artsper": MarketplaceParser(
            source="artsper",
            route_page=lambda html, url: route_from_url(html, url, artsper_entity_from_url),
            extract_artwork=artsper_extract_artwork,
            extract_artist=artsper_extract_artist,
            entity_from_url=artsper_entity_from_url,
        ),
        "artsy": MarketplaceParser(
            source="artsy",
            route_page=lambda html, url: route_from_url(html, url, artsy_entity_from_url),
            extract_artwork=artsy_extract_artwork,
            extract_artist=artsy_extract_artist,
            entity_from_url=artsy_entity_from_url,
        ),
    }


_REGISTRY: dict[str, MarketplaceParser] | None = None


def get_parser(source: str) -> MarketplaceParser:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    parser = _REGISTRY.get(source)
    if parser is None:
        raise KeyError(f"No parser registered for source={source!r}")
    return parser


def register_parser(parser: MarketplaceParser) -> None:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    _REGISTRY[parser.source] = parser
