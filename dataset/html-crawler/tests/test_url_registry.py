from __future__ import annotations

import json
from pathlib import Path

from etl.url_registry import diff_artsper_urls, entity_key_from_url, normalize_url, write_url_list


def test_normalize_url_strips_query_and_trailing_slash() -> None:
    assert (
        normalize_url("https://WWW.Artsper.com/us/foo/?x=1#frag")
        == "https://www.artsper.com/us/foo"
    )


def test_entity_key_from_url() -> None:
    url = "https://www.artsper.com/us/contemporary-artworks/painting/2361374/title"
    assert entity_key_from_url(url) == ("artwork", "2361374")


def test_diff_artsper_urls_new_vs_known(tmp_path: Path) -> None:
    katana = tmp_path / "katana.txt"
    katana.write_text(
        "\n".join(
            [
                "https://www.artsper.com/us/gtm.js",
                "https://www.artsper.com/us/contemporary-artworks/painting/111/a",
                "https://www.artsper.com/us/contemporary-artworks/painting/222/b",
                "https://www.artsper.com/us/contemporary-artists/france/333/name",
            ]
        ),
        encoding="utf-8",
    )
    known = tmp_path / "results.jsonl"
    known.write_text(
        json.dumps(
            {
                "url": "https://www.artsper.com/us/contemporary-artworks/painting/111/old-title",
                "filename": "abc.html",
                "status_code": 200,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = diff_artsper_urls([katana], known_paths=[known])
    assert result.stats.known_entities == 1
    assert result.stats.new_entities == 2
    assert len(result.new_urls) == 2
    assert any("/222/" in url for url in result.new_urls)
    assert any("/333/" in url for url in result.new_urls)


def test_diff_artsper_urls_katana_jsonl(tmp_path: Path) -> None:
    katana = tmp_path / "katana.jsonl"
    katana.write_text(
        json.dumps({"url": "https://www.artsper.com/us/contemporary-artworks/painting/999/x"})
        + "\n",
        encoding="utf-8",
    )
    result = diff_artsper_urls([katana])
    assert result.stats.new_entities == 1
    assert result.new_urls[0].endswith("/999/x")


def test_write_url_list(tmp_path: Path) -> None:
    out = tmp_path / "new.txt"
    count = write_url_list(out, ["https://example.com/a", "https://example.com/b"])
    assert count == 2
    assert out.read_text(encoding="utf-8").count("\n") == 2
