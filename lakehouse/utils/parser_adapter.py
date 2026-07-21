"""Bridge html-crawler parsers into lakehouse processing."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from lakehouse.parsers.registry import MarketplaceParser, get_parser
from lakehouse.utils.storage import html_crawler_root


def ensure_crawler_import_path() -> None:
    root = html_crawler_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def route_entity_type(source: str, html: str, url: str) -> str | None:
    ensure_crawler_import_path()
    parser = get_parser(source)
    if parser.route_page is not None:
        routed = parser.route_page(html, url)
        if routed:
            return routed
    entity = parser.entity_from_url(url)
    return entity[0] if entity else None


def parse_html_record(
    *,
    source: str,
    url: str,
    html_bytes: bytes,
    crawl_timestamp: datetime,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ensure_crawler_import_path()
    parser = get_parser(source)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=True) as tmp:
        tmp.write(html_bytes)
        tmp.flush()
        path = Path(tmp.name)
        html_text = html_bytes.decode("utf-8", errors="replace")
        entity_type = route_entity_type(source, html_text, url)
        if entity_type is None:
            return None, {
                "status": "skip",
                "url": url,
                "reason": "unknown_entity_type",
            }

        if entity_type == "artwork":
            record, missing = parser.extract_artwork(path, url)
        else:
            record, missing = parser.extract_artist(path, url)

        if missing:
            return None, {
                "status": "missing",
                "url": url,
                "entity_type": entity_type,
                "missing": missing,
            }

        silver_row = normalize_to_silver(
            record,
            source=source,
            entity_type=entity_type,
            url=url,
            crawl_timestamp=crawl_timestamp,
        )
        return silver_row, None


def normalize_to_silver(
    record: dict[str, Any],
    *,
    source: str,
    entity_type: str,
    url: str,
    crawl_timestamp: datetime,
) -> dict[str, Any]:
    ensure_crawler_import_path()
    parser = get_parser(source)
    entity = parser.entity_from_url(url)

    entity_id = _entity_id_from_record(record, entity_type, entity)
    title = record.get("title") or record.get("name")
    artist_name = record.get("artist") or record.get("name")
    artist_id = _text(
        record.get("artist_external_id")
        or record.get("artist_id")
        or (entity[1] if entity_type == "artist" and entity else None)
    )
    page_url = _text(record.get("url") or record.get("canonical_url") or url)
    if entity_type == "artist":
        artist_profile_url = _text(
            record.get("url") or record.get("canonical_url") or record.get("profile_url") or url
        )
    else:
        artist_profile_url = _text(record.get("artist_url") or record.get("profile_url"))

    biography = _text(record.get("biography"))
    description = _text(record.get("description") or biography)
    user_name = _text(record.get("user_name"))
    first_name = _text(record.get("first_name"))
    last_name = _text(record.get("last_name"))
    education = _text(record.get("education"))
    exhibitions = _text(record.get("exhibitions"))
    country = _text(record.get("country"))
    city = _text(record.get("city"))
    state = _text(record.get("state"))
    joined_date = _text(record.get("joined_date"))

    category = _text(record.get("artform") or record.get("category"))
    medium = _text(record.get("medium") or category)
    materials = _string_list(record.get("materials"))
    styles = _string_list(record.get("styles"))
    subject = _text(record.get("subject"))
    price = _to_decimal(record.get("price"))
    currency = _text(record.get("currency"))
    availability = _text(record.get("availability"))
    artwork_year = _to_int(record.get("year") or record.get("artwork_year"))
    image_urls = _image_urls(record)
    image_url = image_urls[0] if image_urls else _text(record.get("image_url") or record.get("profile_image_url"))
    dimensions = _dimensions_to_string(record.get("dimensions"))
    sku = _text(record.get("sku"))
    keywords = _string_list(record.get("keywords"))

    return {
        "entity_id": entity_id,
        "source": source,
        "entity_type": entity_type,
        "url": page_url,
        "crawl_timestamp": crawl_timestamp,
        "title": title,
        "artist_name": artist_name,
        "artist_id": artist_id,
        "artist_profile_url": artist_profile_url,
        "user_name": user_name,
        "first_name": first_name,
        "last_name": last_name,
        "biography": biography,
        "education": education,
        "exhibitions": exhibitions,
        "country": country,
        "city": city,
        "state": state,
        "joined_date": joined_date,
        "category": category,
        "medium": medium,
        "materials": materials,
        "styles": styles,
        "subject": subject,
        "description": description,
        "price": price,
        "currency": currency,
        "availability": availability,
        "artwork_year": artwork_year,
        "image_url": image_url,
        "image_urls": image_urls,
        "dimensions": dimensions,
        "sku": sku,
        "keywords": keywords,
        "raw_json": json.dumps(record, default=str),
    }


def _entity_id_from_record(
    record: dict[str, Any],
    entity_type: str,
    entity: tuple[str, str] | None,
) -> str:
    if entity_type == "artwork":
        for key in ("artwork_id", "artwork_slug"):
            value = record.get(key)
            if value:
                return str(value)
    if entity_type == "artist":
        for key in ("artist_external_id", "artist_slug"):
            value = record.get(key)
            if value:
                return str(value)
    if entity:
        return str(entity[1])
    raise ValueError(f"Unable to derive entity_id for entity_type={entity_type}")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip()[:4])
    except (TypeError, ValueError):
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if not digits:
            return None
        try:
            return int(digits[:4])
        except ValueError:
            return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dimensions_to_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        parts = []
        for key in ("height", "width", "depth"):
            if value.get(key):
                parts.append(f"{key}={value[key]}")
        return ", ".join(parts) if parts else json.dumps(value)
    return str(value)


def _image_urls(record: dict[str, Any]) -> list[str]:
    urls = record.get("image_urls")
    if isinstance(urls, list):
        return [str(item) for item in urls if item]
    single = record.get("image_url") or record.get("profile_image_url")
    return [str(single)] if single else []
