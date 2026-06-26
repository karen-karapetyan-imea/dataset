from __future__ import annotations

import json
from pathlib import Path

from mapping_utils import iter_mapping_rows


def test_store_saatchi_mapping_file_filters(tmp_path: Path) -> None:
    data_dir = tmp_path / "html"
    data_dir.mkdir()
    (data_dir / "a.html").write_text("<html></html>", encoding="utf-8")
    (data_dir / "b.html").write_text("<html></html>", encoding="utf-8")
    mapping = tmp_path / "results.jsonl"
    mapping.write_text(
        json.dumps({"url": "https://example.com/a", "filename": "a.html", "status_code": 200}) + "\n",
        encoding="utf-8",
    )
    filenames = {filename for _url, filename, _status in iter_mapping_rows(mapping)}
    assert filenames == {"a.html"}
    assert (data_dir / "a.html").is_file()
    assert not (data_dir / "c.html").is_file()
