"""Pytest fixtures for lakehouse tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAKEHOUSE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAKEHOUSE_ROOT.parent
HTML_CRAWLER_ROOT = REPO_ROOT / "html-crawler"

for path in (str(LAKEHOUSE_ROOT), str(HTML_CRAWLER_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="session")
def spark():
    pytest.importorskip("pyspark")
    import shutil

    if not shutil.which("java"):
        pytest.skip("Java is required for Spark tests")

    from lakehouse.utils.spark import get_spark

    session = get_spark("lakehouse-tests")
    yield session
    session.stop()


@pytest.fixture
def tmp_data_root(tmp_path: Path) -> Path:
    for sub in ("bronze", "silver", "gold"):
        (tmp_path / sub).mkdir(parents=True)
    return tmp_path
