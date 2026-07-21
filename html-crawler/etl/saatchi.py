from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
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
from etl.urls import saatchi_artist_from_url, saatchi_artwork_from_url

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
DATA_LAYER_RE = re.compile(r"dataLayer\s*=\s*(\[)", re.IGNORECASE)

SAATCHI_BASE = "https://www.saatchiart.com"


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _join_list(value: Any, sep: str = ", ") -> str | None:
    if isinstance(value, list):
        parts = [_text_or_none(item) for item in value]
        parts = [p for p in parts if p]
        return sep.join(parts) if parts else None
    return _text_or_none(value)


def parse_data_layer(html: str) -> dict[str, Any] | None:
    match = DATA_LAYER_RE.search(html)
    if not match:
        return None
    start = match.start(1)
    sub = html[start:]
    depth = 0
    for index, char in enumerate(sub):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                try:
                    items = json.loads(sub[: index + 1])
                except json.JSONDecodeError:
                    return None
                if isinstance(items, list) and items and isinstance(items[0], dict):
                    return items[0]
                return None
    return None


def parse_next_data(html: str) -> dict[str, Any] | None:
    match = NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _page_data(next_data: dict[str, Any] | None) -> dict[str, Any]:
    if not next_data:
        return {}
    props = next_data.get("props") or {}
    page_props = props.get("pageProps") or {}
    initial_state = page_props.get("initialState") or {}
    page = initial_state.get("page") or {}
    data = page.get("data") or {}
    return data if isinstance(data, dict) else {}


def route_saatchi_page(html: str) -> str | None:
    """Return 'artwork', 'artist', or None."""
    layer = parse_data_layer(html)
    if layer:
        pagetype = _text_or_none(layer.get("pagetype"))
        if pagetype == "artDetail":
            return "artwork"
        if pagetype == "userProfile":
            return "artist"

    next_data = parse_next_data(html)
    if next_data:
        page_route = _text_or_none(next_data.get("page")) or ""
        if "artdetail" in page_route.lower():
            return "artwork"
        if "artistprofile" in page_route.lower() or "profile" in page_route.lower():
            return "artist"
        data = _page_data(next_data)
        if data.get("pdpArtwork"):
            return "artwork"
        if data.get("accountData"):
            return "artist"
    return None


def _price_from_cents(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return None
    return str(Decimal(cents) / Decimal(100))


def _parse_year(value: Any) -> str | None:
    text = _text_or_none(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:4] if len(digits) >= 4 else None


def _artist_display_name(first: Any, last: Any, display: Any = None) -> str | None:
    name = _text_or_none(display)
    if name:
        return name
    parts = [_text_or_none(first), _text_or_none(last)]
    parts = [p for p in parts if p]
    return " ".join(parts) if parts else None


def _profile_url(user_name: str | None) -> str | None:
    user_name = _text_or_none(user_name)
    if not user_name:
        return None
    return f"{SAATCHI_BASE}/{user_name}"


def _image_urls_from_pdp(pdp: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    main_url = _text_or_none(pdp.get("imageUrl"))
    if main_url:
        urls.append(main_url)
    main_image = pdp.get("artworkMainImage")
    if isinstance(main_image, dict):
        for key in ("mainUrl", "fullscreenUrl", "thumbnailUrl"):
            urls.extend(as_list(main_image.get(key)))
    for item in pdp.get("artworkAdditionalImages") or []:
        if not isinstance(item, dict):
            continue
        for key in ("mainUrl", "fullscreenUrl", "thumbnailUrl"):
            urls.extend(as_list(item.get(key)))
    return dedupe_keep_order(urls)


def _dimensions_from_pdp(pdp: dict[str, Any]) -> dict[str, Any] | None:
    dims = pdp.get("dimensions")
    if not isinstance(dims, dict):
        return None
    out: dict[str, Any] = {}
    for src, dst in (
        ("heightInCentimeters", "height"),
        ("widthInCentimeters", "width"),
        ("depthInCentimeters", "depth"),
    ):
        val = dims.get(src)
        if val is not None:
            out[dst] = val
    return out or None


def extract_artwork_record(path: Path, url: str | None = None) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    layer = parse_data_layer(html)
    next_data = parse_next_data(html)
    page_data = _page_data(next_data)
    pdp = page_data.get("pdpArtwork") if isinstance(page_data.get("pdpArtwork"), dict) else {}
    artwork_block = page_data.get("artwork") if isinstance(page_data.get("artwork"), dict) else {}
    objects = parse_json_ld_blocks(html)
    product = find_schema_object(objects, "Product")

    page_url = (
        _text_or_none(pdp.get("artworkOriginalUrl"))
        or canonical_url(html, meta)
        or _text_or_none(product.get("offers", {}).get("url") if isinstance(product.get("offers"), dict) else None)
        or url
    )

    artwork_id = _text_or_none(pdp.get("artworkId") or pdp.get("legacyArtworkId"))
    artist_id = _text_or_none(pdp.get("artistId"))
    if page_url and (not artwork_id or not artist_id):
        ids = saatchi_artwork_from_url(page_url)
        if ids:
            artist_id = artist_id or ids[0]
            artwork_id = artwork_id or ids[1]
    if layer and not artwork_id:
        artwork_id = _text_or_none(layer.get("artwork id"))
    if layer and not artist_id:
        artist_id = _text_or_none(layer.get("artist id"))

    artist_name = _artist_display_name(
        pdp.get("artistFirstName"),
        pdp.get("artistLastName"),
        layer.get("artist name") if layer else None,
    )
    artist_url = _text_or_none(pdp.get("artistProfileUrl"))

    geo_prices = pdp.get("geoPricesInCents") if isinstance(pdp.get("geoPricesInCents"), dict) else {}
    price = _price_from_cents(geo_prices.get("US"))
    currency = "USD"
    if not price and layer:
        price = _price_from_cents(layer.get("price"))
        currency = _text_or_none((layer.get("ecommerce") or {}).get("currencyCode")) or currency
    offers = product.get("offers") if isinstance(product.get("offers"), dict) else {}
    if not price and offers.get("price") is not None:
        try:
            price = str(Decimal(str(offers.get("price"))))
        except InvalidOperation:
            price = None
        currency = _text_or_none(offers.get("priceCurrency")) or currency
    if not currency:
        currency = _text_or_none(meta.get("product:price:currency")) or "USD"
    if not price:
        price = _text_or_none(meta.get("product:price:amount"))

    mediums = pdp.get("mediums") or (layer.get("medium") if layer else None)
    materials = pdp.get("materials")
    styles = pdp.get("styles") or (layer.get("style") if layer else None)

    image_urls = _image_urls_from_pdp(pdp)
    if not image_urls:
        image_urls = dedupe_keep_order(
            as_list(product.get("image"))
            + as_list(meta.get("og:image"))
        )

    record: dict[str, Any] = {
        "entity_type": "artwork",
        "source_file": path.name,
        "url": page_url,
        "artwork_id": artwork_id,
        "artist_external_id": artist_id,
        "title": (
            _text_or_none(pdp.get("artworkTitle"))
            or _text_or_none(layer.get("artwork title") if layer else None)
            or _text_or_none(product.get("name"))
            or _text_or_none(meta.get("og:title"))
        ),
        "artist": artist_name,
        "artist_url": artist_url,
        "year": _parse_year(artwork_block.get("year")),
        "artform": _text_or_none(pdp.get("category") or (layer.get("category") if layer else None)),
        "medium": _join_list(mediums),
        "materials": materials if isinstance(materials, list) else as_list(materials),
        "styles": styles if isinstance(styles, list) else as_list(styles),
        "subject": _text_or_none(pdp.get("subject") or (layer.get("subject") if layer else None)),
        "price": price,
        "currency": currency,
        "availability": _text_or_none(pdp.get("originalArtworkStatus") or (layer.get("original availability") if layer else None)),
        "image_urls": image_urls,
        "description": _text_or_none(artwork_block.get("description") or product.get("description")),
        "dimensions": _dimensions_from_pdp(pdp),
        "sku": _text_or_none(pdp.get("sku") or (layer.get("sku") if layer else None) or product.get("sku")),
        "keywords": pdp.get("keywords") if isinstance(pdp.get("keywords"), list) else [],
    }

    missing: list[str] = []
    for field in ("title", "url"):
        if not record.get(field):
            missing.append(field)
    return record, missing


def extract_artist_record(path: Path, url: str | None = None) -> tuple[dict[str, Any], list[str]]:
    html = read_html(path)
    meta = meta_map(html)
    layer = parse_data_layer(html)
    next_data = parse_next_data(html)
    page_data = _page_data(next_data)
    account = page_data.get("accountData") if isinstance(page_data.get("accountData"), dict) else {}

    canonical = canonical_url(html, meta)
    user_name = _text_or_none(account.get("userName"))
    if not user_name and next_data:
        query = next_data.get("query") or {}
        if isinstance(query, dict):
            user_name = _text_or_none(query.get("userName"))

    profile_url = _profile_url(user_name)
    artist_id = _text_or_none(account.get("userId"))
    if not artist_id and canonical:
        artist_id = saatchi_artist_from_url(canonical)
    if not artist_id and layer:
        artist_id = _text_or_none(layer.get("artist id"))

    about_artist = account.get("aboutArtist") if isinstance(account.get("aboutArtist"), dict) else {}
    badges = account.get("badges") if isinstance(account.get("badges"), list) else []
    if not badges and layer:
        badges = layer.get("badges") or []

    name = _artist_display_name(
        account.get("firstName"),
        account.get("lastName"),
        account.get("displayName") or (layer.get("artist name") if layer else None),
    )
    if not name:
        og_title = _text_or_none(meta.get("og:title"))
        if og_title and "|" in og_title:
            name = og_title.split("|")[0].strip()

    record: dict[str, Any] = {
        "entity_type": "artist",
        "source_file": path.name,
        "url": profile_url or canonical or url,
        "artist_external_id": artist_id,
        "name": name,
        "first_name": _text_or_none(account.get("firstName")),
        "last_name": _text_or_none(account.get("lastName")),
        "user_name": user_name,
        "profile_image_url": _text_or_none(account.get("avatar") or account.get("avatarLarge") or meta.get("og:image")),
        "biography": _text_or_none(about_artist.get("about")),
        "education": _text_or_none(about_artist.get("education")),
        "exhibitions": _text_or_none(about_artist.get("exhibitions")),
        "country": _text_or_none(account.get("country") or (layer.get("artist country") if layer else None)),
        "city": _text_or_none(account.get("city")),
        "state": _text_or_none(account.get("state")),
        "canonical_url": canonical,
        "badges": badges,
        "joined_date": _text_or_none(account.get("joinedDate")),
    }

    missing: list[str] = []
    for field in ("name", "url", "artist_external_id"):
        if not record.get(field):
            missing.append(field)
    return record, missing
