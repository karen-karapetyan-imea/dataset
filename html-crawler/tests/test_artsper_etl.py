from pathlib import Path

from etl.artsper import extract_artwork_record

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "artsper_artwork_sample.html"
URL = "https://www.artsper.com/us/contemporary-artworks/painting/2361374/sample-title"


def test_extract_artsper_artwork_record() -> None:
    record, missing = extract_artwork_record(FIXTURE, URL)
    assert not missing
    assert record["title"] == "Sample Title"
    assert record["artist"] == "Jane Artist"
    assert record["artist_external_id"] == "128876"
    assert record["price"] == "1200"
    assert record["currency"] == "USD"
