"""Shared HTML parsing helpers for ETL extractors."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

META_TAG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
META_TAG_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
LINK_CANONICAL_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def read_html(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def meta_map(html: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for pattern in (META_TAG_RE, META_TAG_RE_ALT):
        for match in pattern.finditer(html):
            if pattern is META_TAG_RE:
                key, value = match.group(1), match.group(2)
            else:
                value, key = match.group(1), match.group(2)
            meta.setdefault(key.strip().lower(), unescape(value.strip()))
    return meta


def canonical_url(html: str, meta: dict[str, str] | None = None) -> str | None:
    match = LINK_CANONICAL_RE.search(html)
    if match:
        return unescape(match.group(1).strip())
    meta = meta or meta_map(html)
    return meta.get("og:url")


def parse_json_ld_blocks(html: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for block in JSON_LD_RE.findall(html):
        text = block.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            objects.append(data)
        elif isinstance(data, list):
            objects.extend(item for item in data if isinstance(item, dict))
    return objects


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def find_schema_object(
    objects: list[dict[str, Any]],
    schema_type: str,
) -> dict[str, Any]:
    target = schema_type.lower()
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        obj_type = obj.get("@type")
        if isinstance(obj_type, list):
            types = [str(item).lower() for item in obj_type]
        else:
            types = [str(obj_type).lower()] if obj_type else []
        if target in types:
            return obj
        graph = obj.get("@graph")
        if isinstance(graph, list):
            nested = find_schema_object([item for item in graph if isinstance(item, dict)], schema_type)
            if nested:
                return nested
    return {}


def absolute_url(base: str | None, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if not href:
        return None
    if base:
        return urljoin(base, href)
    return href
