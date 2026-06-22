from __future__ import annotations

from pathlib import Path

from etl.url_registry import html_filename_for_url
from mapping_utils import iter_url_list_rows


def test_iter_url_list_rows_skips_missing_html(tmp_path: Path) -> None:
    url = "https://www.artsper.com/us/contemporary-artists/france/128876/nathalie-cubero"
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(url + "\n", encoding="utf-8")
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    rows = list(iter_url_list_rows(urls_file, html_dir))
    assert rows == []

    filename = html_filename_for_url(url)
    (html_dir / filename).write_text("<html></html>", encoding="utf-8")
    rows = list(iter_url_list_rows(urls_file, html_dir))
    assert rows == [(url, filename, 200)]
