from __future__ import annotations

import json
from pathlib import Path

from etl.sitemap import (
    SitemapEntry,
    build_lastmod_state_from_entries,
    diff_sitemap_entries,
    load_lastmod_state,
    save_lastmod_state,
)


def test_diff_sitemap_new_and_updated() -> None:
    entries = [
        SitemapEntry(
            url="https://www.artsy.net/artwork/a",
            lastmod="2026-01-01T00:00:00+00:00",
            entity_type="artwork",
            entity_id="a",
        ),
        SitemapEntry(
            url="https://www.artsy.net/artwork/b",
            lastmod="2026-06-01T00:00:00+00:00",
            entity_type="artwork",
            entity_id="b",
        ),
    ]
    known = {("artwork", "a")}
    state = {"artwork:a": "2026-01-01T00:00:00+00:00"}
    result = diff_sitemap_entries(entries, known_entity_keys=known, lastmod_state=state)
    assert result.stats.new_entities == 1
    assert result.stats.updated_entities == 0
    assert any(entry.entity_id == "b" for entry in result.to_crawl)


def test_lastmod_state_roundtrip(tmp_path: Path) -> None:
    entries = [
        SitemapEntry(
            url="https://www.saatchiart.com/art/x/1/2/view",
            lastmod="2026-06-01T00:00:00+00:00",
            entity_type="artwork",
            entity_id="2",
        )
    ]
    state_path = tmp_path / "lastmod.json"
    save_lastmod_state(state_path, build_lastmod_state_from_entries(entries))
    loaded = load_lastmod_state(state_path)
    assert loaded["artwork:2"] == "2026-06-01T00:00:00+00:00"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert "last_fetch_at" in payload
