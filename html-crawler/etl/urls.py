"""URL parsing helpers for Artsper, Saatchi, and Artsy."""

from __future__ import annotations

import re

ARTSPER_ARTWORK_RE = re.compile(
    r"artsper\.com/(?:[a-z]{2}/)?contemporary-artworks/[^/]+/(\d+)/",
    re.IGNORECASE,
)
ARTSPER_ARTIST_RE = re.compile(
    r"artsper\.com/(?:[a-z]{2}/)?contemporary-artists/[^/]+/(\d+)/",
    re.IGNORECASE,
)
SAATCHI_ARTWORK_RE = re.compile(
    r"saatchiart\.com/art/[^/]+/(\d+)/(\d+)(?:/view)?/?",
    re.IGNORECASE,
)
SAATCHI_ARTIST_PROFILE_RE = re.compile(
    r"saatchiart\.com/(?:account/profile/|)([a-z0-9_-]+)/?$",
    re.IGNORECASE,
)
SAATCHI_ARTIST_ID_RE = re.compile(
    r"saatchiart\.com/(?:account/profile/)?(\d+)/?$",
    re.IGNORECASE,
)
# Exact entity pages only: /artist/<slug> or /artwork/<slug> (no nested paths).
ARTSY_ARTWORK_RE = re.compile(
    r"artsy\.net/artwork/([a-z0-9-]+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)
ARTSY_ARTIST_RE = re.compile(
    r"artsy\.net/artist/([a-z0-9-]+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)


def artsper_entity_from_url(url: str) -> tuple[str, str] | None:
    """Return ('artwork'|'artist', numeric_id) for Artsper entity URLs."""
    artwork = ARTSPER_ARTWORK_RE.search(url)
    if artwork:
        return "artwork", artwork.group(1)
    artist = ARTSPER_ARTIST_RE.search(url)
    if artist:
        return "artist", artist.group(1)
    return None


def saatchi_artwork_from_url(url: str) -> tuple[str, str] | None:
    """Return (artist_id, artwork_id) from Saatchi artwork URLs."""
    match = SAATCHI_ARTWORK_RE.search(url)
    if not match:
        return None
    return match.group(1), match.group(2)


def saatchi_artist_from_url(url: str) -> str | None:
    """Return numeric artist id when present in Saatchi profile URLs."""
    match = SAATCHI_ARTIST_ID_RE.search(url)
    if match:
        return match.group(1)
    profile = SAATCHI_ARTIST_PROFILE_RE.search(url)
    if profile and profile.group(1).isdigit():
        return profile.group(1)
    return None


def artsy_entity_from_url(url: str) -> tuple[str, str] | None:
    """Return ('artwork'|'artist', slug) for Artsy entity page URLs."""
    artwork = ARTSY_ARTWORK_RE.search(url)
    if artwork:
        return "artwork", artwork.group(1).lower()
    artist = ARTSY_ARTIST_RE.search(url)
    if artist:
        return "artist", artist.group(1).lower()
    return None
