"""Artsy HTML extractors (JSON-LD + meta fallbacks)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from etl.common import (
    as_list,
    canonical_url,
    dedupe_keep_order,
    find_schema_object,
    meta_map,
    parse_json_ld_blocks,
    read_html,
)
from etl.urls import artsy_entity_from_url

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_next_data(html: str) -> dict[str, Any] | None:
    match = NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def route_artsy_page(html: str, url: str | None = None) -> str | None:
    if url:
        entity = artsy_entity_from_url(url)
        if entity:
            return entity[0]
    meta = meta_map(html)
    canonical = canonical_url(html, meta)
    if canonical:
        entity = artsy_entity_from_url(canonical)
        if entity:
            return entity[0]
    return None


def _entity_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    entity = artsy_entity_from_url(url)
    return entity[1] if entity else None


def _creator_fields(creator: Any) -> tuple[str | None, str | None]:
    if isinstance(creator, dict):
        name = _text_or_none(creator.get("name"))
        url = _text_or_none(creator.get("url") or creator.get("@id"))
        artist_id = _entity_id_from_url(url) if url else None
        return name, artist_id
    return _text_or_none(creator), None


def _base_record(path: Path, page_type: str, url: str | None) -> dict[str, Any]:
    page_url = url
    entity_id = _entity_id_from_url(page_url)
    return {
        "entity_type": page_type,
        "source_file": path.name,
        "url": page_url,
        "external_id": entity_id,
    }


def extract_artwork_record(path: Path, url: str | None = None) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    objects = parse_json_ld_blocks(html)
    visual = find_schema_object(objects, "VisualArtwork")
    product = find_schema_object(objects, "Product")
    schema_obj = visual or product or {}

    page_url = canonical_url(html, meta) or url
    record = _base_record(path, "artwork", page_url)
    artist_name, artist_id = _creator_fields(schema_obj.get("creator") if isinstance(schema_obj, dict) else None)
    image_urls = dedupe_keep_order(
        as_list(schema_obj.get("image") if isinstance(schema_obj, dict) else None)
        + as_list(meta.get("og:image"))
    )
    offers = schema_obj.get("offers") if isinstance(schema_obj, dict) else None
    price = None
    currency = None
    if isinstance(offers, dict):
        price = _text_or_none(offers.get("price"))
        currency = _text_or_none(offers.get("priceCurrency"))

    record.update(
        {
            "title": _text_or_none(schema_obj.get("name") if isinstance(schema_obj, dict) else None)
            or _text_or_none(meta.get("og:title")),
            "artist_name": artist_name,
            "artist_external_id": artist_id,
            "description": _text_or_none(schema_obj.get("description") if isinstance(schema_obj, dict) else None),
            "medium": _text_or_none(schema_obj.get("artMedium") if isinstance(schema_obj, dict) else None),
            "year": _text_or_none(schema_obj.get("dateCreated") if isinstance(schema_obj, dict) else None),
            "price": price,
            "currency": currency,
            "image_urls": image_urls,
            "canonical_url": page_url,
        }
    )
    missing = [field for field in ("title", "url", "external_id") if not record.get(field)]
    return record, missing


def extract_artist_record(path: Path, url: str | None = None) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    objects = parse_json_ld_blocks(html)
    person = find_schema_object(objects, "Person") or find_schema_object(objects, "ProfilePage") or {}

    page_url = canonical_url(html, meta) or url
    record = _base_record(path, "artist", page_url)
    og_title = _text_or_none(meta.get("og:title"))
    name = _text_or_none(person.get("name") if isinstance(person, dict) else None) or og_title
    record.update(
        {
            "name": name,
            "biography": _text_or_none(person.get("description") if isinstance(person, dict) else None),
            "image_url": _text_or_none(meta.get("og:image")),
            "canonical_url": page_url,
        }
    )
    missing = [field for field in ("name", "url", "external_id") if not record.get(field)]
    return record, missing


def extract_partner_record(path: Path, url: str | None = None) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    org = find_schema_object(parse_json_ld_blocks(html), "Organization") or {}

    page_url = canonical_url(html, meta) or url
    record = _base_record(path, "partner", page_url)
    record.update(
        {
            "name": _text_or_none(org.get("name") if isinstance(org, dict) else None)
            or _text_or_none(meta.get("og:title")),
            "description": _text_or_none(org.get("description") if isinstance(org, dict) else None),
            "image_url": _text_or_none(meta.get("og:image")),
            "canonical_url": page_url,
        }
    )
    missing = [field for field in ("name", "url", "external_id") if not record.get(field)]
    return record, missing


def extract_show_record(path: Path, url: str | None = None) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    event = find_schema_object(parse_json_ld_blocks(html), "Event") or find_schema_object(
        parse_json_ld_blocks(html), "ExhibitionEvent"
    ) or {}

    page_url = canonical_url(html, meta) or url
    record = _base_record(path, "show", page_url)
    record.update(
        {
            "name": _text_or_none(event.get("name") if isinstance(event, dict) else None)
            or _text_or_none(meta.get("og:title")),
            "description": _text_or_none(event.get("description") if isinstance(event, dict) else None),
            "start_date": _text_or_none(event.get("startDate") if isinstance(event, dict) else None),
            "end_date": _text_or_none(event.get("endDate") if isinstance(event, dict) else None),
            "canonical_url": page_url,
        }
    )
    missing = [field for field in ("name", "url", "external_id") if not record.get(field)]
    return record, missing


def extract_fair_record(path: Path, url: str | None = None) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    event = find_schema_object(parse_json_ld_blocks(html), "Event") or {}

    page_url = canonical_url(html, meta) or url
    record = _base_record(path, "fair", page_url)
    record.update(
        {
            "name": _text_or_none(event.get("name") if isinstance(event, dict) else None)
            or _text_or_none(meta.get("og:title")),
            "description": _text_or_none(event.get("description") if isinstance(event, dict) else None),
            "start_date": _text_or_none(event.get("startDate") if isinstance(event, dict) else None),
            "end_date": _text_or_none(event.get("endDate") if isinstance(event, dict) else None),
            "canonical_url": page_url,
        }
    )
    missing = [field for field in ("name", "url", "external_id") if not record.get(field)]
    return record, missing


EXTRACTORS = {
    "artwork": extract_artwork_record,
    "artist": extract_artist_record,
    "partner": extract_partner_record,
    "show": extract_show_record,
    "fair": extract_fair_record,
}
