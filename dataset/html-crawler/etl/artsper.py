"""Artsper HTML extractors (JSON-LD + meta fallbacks)."""

from __future__ import annotations

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
from etl.urls import artsper_entity_from_url


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _artist_external_id_from_creator(creator: Any) -> str | None:
    if not isinstance(creator, dict):
        return None
    for key in ("url", "@id", "sameAs"):
        value = creator.get(key)
        if not value:
            continue
        entity = artsper_entity_from_url(str(value))
        if entity and entity[0] == "artist":
            return entity[1]
    return None


def _creator_name(creator: Any) -> str | None:
    if isinstance(creator, dict):
        return _text_or_none(creator.get("name"))
    return _text_or_none(creator)


def _offers_fields(offers: Any) -> tuple[str | None, str | None]:
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if not isinstance(offers, dict):
        return None, None
    price = _text_or_none(offers.get("price"))
    currency = _text_or_none(offers.get("priceCurrency"))
    return price, currency


def extract_artwork_record(
    path: Path,
    url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    objects = parse_json_ld_blocks(html)
    visual = find_schema_object(objects, "VisualArtwork")
    product = find_schema_object(objects, "Product")
    schema_obj = visual or product

    page_url = canonical_url(html, meta) or url
    creator = schema_obj.get("creator") if isinstance(schema_obj, dict) else None
    artist = _creator_name(creator) or _text_or_none(meta.get("og:artist"))
    title = (
        _text_or_none(schema_obj.get("name") if isinstance(schema_obj, dict) else None)
        or _text_or_none(meta.get("og:title"))
    )
    price, currency = _offers_fields(schema_obj.get("offers") if isinstance(schema_obj, dict) else None)
    image_urls = dedupe_keep_order(
        as_list(schema_obj.get("image") if isinstance(schema_obj, dict) else None)
        + as_list(meta.get("og:image"))
    )
    artist_external_id = _artist_external_id_from_creator(creator)
    artist_url = None
    if isinstance(creator, dict):
        artist_url = _text_or_none(creator.get("url"))

    record: dict[str, Any] = {
        "source_file": path.name,
        "url": page_url,
        "title": title,
        "artist": artist,
        "artist_external_id": artist_external_id,
        "artist_url": artist_url,
        "year": _text_or_none(schema_obj.get("dateCreated") if isinstance(schema_obj, dict) else None),
        "artform": _text_or_none(schema_obj.get("artform") if isinstance(schema_obj, dict) else None),
        "medium": _text_or_none(schema_obj.get("artMedium") if isinstance(schema_obj, dict) else None),
        "price": price,
        "currency": currency,
        "image_urls": image_urls,
        "description": _text_or_none(schema_obj.get("description") if isinstance(schema_obj, dict) else None),
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
    html = read_html(path)
    meta = meta_map(html)
    objects = parse_json_ld_blocks(html)
    person = find_schema_object(objects, "Person")
    profile = find_schema_object(objects, "ProfilePage")

    page_url = canonical_url(html, meta) or url
    name = (
        _text_or_none(person.get("name") if isinstance(person, dict) else None)
        or _text_or_none(profile.get("name") if isinstance(profile, dict) else None)
        or _text_or_none(meta.get("og:title"))
    )
    image_url = (
        _text_or_none(person.get("image") if isinstance(person, dict) else None)
        or _text_or_none(meta.get("og:image"))
    )
    if isinstance(person, dict) and isinstance(person.get("image"), dict):
        image_url = _text_or_none(person["image"].get("url")) or image_url

    about = None
    if isinstance(person, dict):
        about = _text_or_none(person.get("description"))
    if not about and isinstance(profile, dict):
        about = _text_or_none(profile.get("description"))

    record: dict[str, Any] = {
        "source_file": path.name,
        "url": page_url,
        "name": name,
        "image_url": image_url,
        "about_text": about,
    }

    missing: list[str] = []
    for field in ("name", "url"):
        if not record.get(field):
            missing.append(field)
    return record, missing
