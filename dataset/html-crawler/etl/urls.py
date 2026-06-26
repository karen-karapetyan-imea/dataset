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
    r"saatchiart\.com/account/profile/([a-z0-9_-]+)/?$",
    re.IGNORECASE,
)
SAATCHI_ARTIST_ID_RE = re.compile(
    r"saatchiart\.com/(?:account/profile/)?(\d+)/?$",
    re.IGNORECASE,
)
SAATCHI_USERNAME_RE = re.compile(
    r"saatchiart\.com/([a-z0-9_-]+)/?$",
    re.IGNORECASE,
)
ARTSY_ARTWORK_RE = re.compile(
    r"artsy\.net/artwork/([^/?#]+)",
    re.IGNORECASE,
)
ARTSY_ARTIST_RE = re.compile(
    r"artsy\.net/artist/([^/?#]+)",
    re.IGNORECASE,
)
ARTSY_PARTNER_RE = re.compile(
    r"artsy\.net/partner/([^/?#]+)",
    re.IGNORECASE,
)
ARTSY_SHOW_RE = re.compile(
    r"artsy\.net/show/([^/?#]+)",
    re.IGNORECASE,
)
ARTSY_FAIR_RE = re.compile(
    r"artsy\.net/fair/([^/?#]+)",
    re.IGNORECASE,
)

_SAATCHI_RESERVED = frozenset(
    {
        "art",
        "account",
        "accounts",
        "search",
        "collections",
        "stories",
        "magazine",
        "api",
        "www",
    }
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


def saatchi_entity_from_url(url: str) -> tuple[str, str] | None:
    """Return ('artwork'|'artist', external_id) for Saatchi entity URLs."""
    artwork = saatchi_artwork_from_url(url)
    if artwork:
        return "artwork", artwork[1]
    artist_id = saatchi_artist_from_url(url)
    if artist_id:
        return "artist", artist_id
    profile = SAATCHI_ARTIST_PROFILE_RE.search(url)
    if profile:
        return "artist", profile.group(1)
    username = SAATCHI_USERNAME_RE.search(url)
    if username:
        slug = username.group(1).lower()
        if slug not in _SAATCHI_RESERVED:
            return "artist", slug
    return None


def artsy_entity_from_url(url: str) -> tuple[str, str] | None:
    """Return (entity_type, slug) for Artsy catalog URLs."""
    for pattern, entity_type in (
        (ARTSY_ARTWORK_RE, "artwork"),
        (ARTSY_ARTIST_RE, "artist"),
        (ARTSY_PARTNER_RE, "partner"),
        (ARTSY_SHOW_RE, "show"),
        (ARTSY_FAIR_RE, "fair"),
    ):
        match = pattern.search(url)
        if match:
            return entity_type, match.group(1)
    return None


def entity_from_url(url: str, *, source: str) -> tuple[str, str] | None:
    """Dispatch URL parsing by marketplace source name."""
    if source == "artsper":
        return artsper_entity_from_url(url)
    if source == "saatchi":
        return saatchi_entity_from_url(url)
    if source == "artsy":
        return artsy_entity_from_url(url)
    return None
