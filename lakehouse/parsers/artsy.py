"""Artsy HTML extractors (JSON-LD + __NEXT_DATA__ fallbacks)."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from lakehouse.utils.storage import html_crawler_root

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _ensure_crawler_path() -> None:
    root = str(html_crawler_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _etl():
    _ensure_crawler_path()
    from etl import common
    from etl.urls import artsy_entity_from_url

    return common, artsy_entity_from_url


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _parse_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _find_key(node: Any, key: str) -> Any:
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_key(item, key)
            if found is not None:
                return found
    return None


def _price_decimal(value: Any) -> str | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if amount > 100_000:
        amount = amount / Decimal("100")
    return str(amount.quantize(Decimal("0.01")))


def _offers_fields(offers: Any) -> tuple[str | None, str | None]:
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if not isinstance(offers, dict):
        return None, None
    return _price_decimal(offers.get("price")), _text_or_none(offers.get("priceCurrency"))


def extract_artwork_record(
    path: Path,
    url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    common, artsy_entity_from_url = _etl()
    html = common.read_html(path)
    meta = common.meta_map(html)
    objects = common.parse_json_ld_blocks(html)
    next_data = _parse_next_data(html)

    visual = common.find_schema_object(objects, "VisualArtwork")
    product = common.find_schema_object(objects, "Product")
    schema_obj = visual or product

    page_url = common.canonical_url(html, meta) or url
    entity = artsy_entity_from_url(page_url or "")
    slug = entity[1] if entity and entity[0] == "artwork" else None

    title = (
        _text_or_none(schema_obj.get("name") if isinstance(schema_obj, dict) else None)
        or _text_or_none(_find_key(next_data, "title"))
        or _text_or_none(meta.get("og:title"))
    )
    artist = None
    if isinstance(schema_obj, dict) and isinstance(schema_obj.get("creator"), dict):
        artist = _text_or_none(schema_obj["creator"].get("name"))
    if not artist:
        names = _find_key(next_data, "artistNames")
        if isinstance(names, list) and names:
            artist = _text_or_none(names[0])
    if not artist:
        artist = _text_or_none(meta.get("og:artist"))

    price, currency = _offers_fields(schema_obj.get("offers") if isinstance(schema_obj, dict) else None)
    if not price:
        price = _price_decimal(_find_key(next_data, "listPrice"))
    if not currency:
        currency = _text_or_none(_find_key(next_data, "currencyCode")) or "USD"

    image_urls = common.dedupe_keep_order(
        common.as_list(schema_obj.get("image") if isinstance(schema_obj, dict) else None)
        + common.as_list(meta.get("og:image"))
        + common.as_list(_find_key(next_data, "imageURLs"))
    )

    dimensions = _text_or_none(_find_key(next_data, "dimensions"))
    medium = (
        _text_or_none(schema_obj.get("artMedium") if isinstance(schema_obj, dict) else None)
        or _text_or_none(_find_key(next_data, "medium"))
        or _text_or_none(_find_key(next_data, "category"))
    )

    record: dict[str, Any] = {
        "entity_type": "artwork",
        "source_file": path.name,
        "url": page_url,
        "artwork_slug": slug,
        "title": title,
        "artist": artist,
        "medium": medium,
        "price": price,
        "currency": currency,
        "dimensions": dimensions,
        "image_urls": image_urls,
        "description": _text_or_none(schema_obj.get("description") if isinstance(schema_obj, dict) else None),
        "availability": _text_or_none(_find_key(next_data, "availability")),
        "category": _text_or_none(_find_key(next_data, "category")),
    }

    missing: list[str] = []
    for field in ("title", "url"):
        if not record.get(field):
            missing.append(field)
    return record, missing


def extract_artist_record(
    path: Path,
    url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    common, artsy_entity_from_url = _etl()
    html = common.read_html(path)
    meta = common.meta_map(html)
    objects = common.parse_json_ld_blocks(html)
    next_data = _parse_next_data(html)

    person = common.find_schema_object(objects, "Person")
    profile = common.find_schema_object(objects, "ProfilePage")

    page_url = common.canonical_url(html, meta) or url
    entity = artsy_entity_from_url(page_url or "")
    slug = entity[1] if entity and entity[0] == "artist" else None

    name = (
        _text_or_none(person.get("name") if isinstance(person, dict) else None)
        or _text_or_none(profile.get("name") if isinstance(profile, dict) else None)
        or _text_or_none(_find_key(next_data, "name"))
        or _text_or_none(meta.get("og:title"))
    )
    image_url = (
        _text_or_none(person.get("image") if isinstance(person, dict) else None)
        or _text_or_none(meta.get("og:image"))
        or _text_or_none(_find_key(next_data, "imageUrl"))
    )
    if isinstance(person, dict) and isinstance(person.get("image"), dict):
        image_url = _text_or_none(person["image"].get("url")) or image_url

    biography = None
    if isinstance(person, dict):
        biography = _text_or_none(person.get("description"))
    if not biography:
        biography = _text_or_none(_find_key(next_data, "biography"))

    record: dict[str, Any] = {
        "entity_type": "artist",
        "source_file": path.name,
        "url": page_url,
        "artist_slug": slug,
        "name": name,
        "image_url": image_url,
        "biography": biography,
        "profile_image_url": image_url,
    }

    missing: list[str] = []
    for field in ("name", "url"):
        if not record.get(field):
            missing.append(field)
    return record, missing
