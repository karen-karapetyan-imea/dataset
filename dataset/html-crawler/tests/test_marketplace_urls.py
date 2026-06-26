from __future__ import annotations

from etl.urls import (
    artsy_entity_from_url,
    saatchi_entity_from_url,
)


def test_saatchi_entity_artwork_url() -> None:
    url = "https://www.saatchiart.com/art/Painting-Test/735695/9336593/view"
    assert saatchi_entity_from_url(url) == ("artwork", "9336593")


def test_saatchi_entity_artist_profile_url() -> None:
    url = "https://www.saatchiart.com/account/profile/735695"
    assert saatchi_entity_from_url(url) == ("artist", "735695")


def test_artsy_entity_artwork_url() -> None:
    url = "https://www.artsy.net/artwork/andy-warhol-campbell-soup"
    assert artsy_entity_from_url(url) == ("artwork", "andy-warhol-campbell-soup")


def test_artsy_entity_artist_url() -> None:
    url = "https://www.artsy.net/artist/andy-warhol"
    assert artsy_entity_from_url(url) == ("artist", "andy-warhol")


def test_artsy_entity_partner_url() -> None:
    url = "https://www.artsy.net/partner/gagosian"
    assert artsy_entity_from_url(url) == ("partner", "gagosian")


def test_artsy_entity_show_url() -> None:
    url = "https://www.artsy.net/show/example-show"
    assert artsy_entity_from_url(url) == ("show", "example-show")


def test_artsy_entity_fair_url() -> None:
    url = "https://www.artsy.net/fair/example-fair"
    assert artsy_entity_from_url(url) == ("fair", "example-fair")
