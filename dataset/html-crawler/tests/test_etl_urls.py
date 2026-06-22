from etl.artsper import _artist_external_id_from_creator
from etl.urls import (
    artsper_entity_from_url,
    saatchi_artist_from_url,
    saatchi_artwork_from_url,
)


def test_artsper_artwork_url() -> None:
    url = "https://www.artsper.com/us/contemporary-artworks/painting/2361374/title"
    assert artsper_entity_from_url(url) == ("artwork", "2361374")


def test_artsper_artist_url() -> None:
    url = "https://www.artsper.com/us/contemporary-artists/france/128876/nathalie-cubero"
    assert artsper_entity_from_url(url) == ("artist", "128876")


def test_saatchi_artwork_url() -> None:
    url = (
        "https://www.saatchiart.com/art/Painting-Gold-abstract-painting-GB416-FEATURED/"
        "735695/9336593/view"
    )
    assert saatchi_artwork_from_url(url) == ("735695", "9336593")


def test_saatchi_artist_url() -> None:
    url = "https://www.saatchiart.com/account/profile/735695"
    assert saatchi_artist_from_url(url) == "735695"


def test_artist_external_id_from_creator_url() -> None:
    creator = {
        "name": "Nathalie Cubero",
        "url": "https://www.artsper.com/us/contemporary-artists/france/128876/nathalie-cubero",
    }
    assert _artist_external_id_from_creator(creator) == "128876"
