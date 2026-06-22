from __future__ import annotations

from etl.sitemap import (
    diff_sitemap_entries,
    parse_child_sitemap_locs,
    parse_url_entries,
    SitemapEntry,
)


INDEX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.artsper.com/sitemap.artist_0.xml</loc></sitemap>
  <sitemap><loc>https://www.artsper.com/sitemap.artwork_category_6_0.xml</loc></sitemap>
</sitemapindex>"""

URLSET_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.artsper.com/us/contemporary-artists/france/128876/nathalie-cubero</loc>
    <lastmod>2026-06-08T04:00:50+02:00</lastmod>
  </url>
  <url>
    <loc>https://www.artsper.com/us/contemporary-artworks/painting/2361374/un-petit-bout</loc>
    <lastmod>2026-06-09T04:00:50+02:00</lastmod>
  </url>
</urlset>"""


def test_parse_child_sitemap_locs() -> None:
    locs = parse_child_sitemap_locs(INDEX_XML)
    assert len(locs) == 2
    assert "artist_0.xml" in locs[0]


def test_parse_url_entries() -> None:
    entries = parse_url_entries(URLSET_XML)
    assert len(entries) == 2
    assert entries[0][1] == "2026-06-08T04:00:50+02:00"


def test_diff_sitemap_new_and_updated() -> None:
    entries = [
        SitemapEntry(
            url="https://www.artsper.com/us/contemporary-artists/france/128876/nathalie-cubero",
            lastmod="2026-06-08T04:00:50+02:00",
            entity_type="artist",
            entity_id="128876",
        ),
        SitemapEntry(
            url="https://www.artsper.com/us/contemporary-artworks/painting/2361374/un-petit-bout",
            lastmod="2026-06-09T04:00:50+02:00",
            entity_type="artwork",
            entity_id="2361374",
        ),
    ]
    known = {("artist", "128876")}
    state = {"artist:128876": "2026-06-01T00:00:00+02:00"}
    result = diff_sitemap_entries(entries, known_entity_keys=known, lastmod_state=state)
    assert result.stats.new_entities == 1
    assert result.stats.updated_entities == 1
    assert len(result.to_crawl) == 2
