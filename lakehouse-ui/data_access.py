"""Path helpers and table loaders for the lakehouse browser (no Spark)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

HEAVY_COLUMNS = ("html", "raw_json", "image_urls", "headers_json")

TABLE_CHOICES = (
    "bronze",
    "silver.artworks",
    "silver.artists",
    "gold.current_artworks",
    "gold.current_artists",
    "gold.price_history",
    "gold.artist_statistics",
    "gold.market_metrics",
    "failures",
)

SEARCH_COLUMNS = ("title", "artist_name", "url", "name", "entity_id")

DEFAULT_DATA_ROOT = Path(
    os.environ.get("LAKEHOUSE_DATA_ROOT", str(Path(__file__).resolve().parents[1]))
).resolve()


def default_data_root() -> Path:
    return DEFAULT_DATA_ROOT


def bronze_partition_path(root: Path, source: str, crawl_date: str) -> Path:
    return root / "bronze" / f"source={source}" / f"crawl_date={crawl_date}"


def silver_artworks_path(root: Path) -> Path:
    return root / "silver" / "artworks"


def silver_artists_path(root: Path) -> Path:
    return root / "silver" / "artists"


def silver_failures_path(root: Path, source: str, crawl_date: str) -> Path:
    return root / "silver" / "_failures" / f"source={source}" / f"crawl_date={crawl_date}"


def gold_table_path(root: Path, table_name: str) -> Path:
    return root / "gold" / table_name


def resolve_table_path(
    table: str,
    root: Path,
    *,
    source: str,
    crawl_date: str | None,
) -> Path:
    if table == "bronze":
        if not crawl_date:
            raise ValueError("crawl_date is required for bronze")
        return bronze_partition_path(root, source, crawl_date)
    if table == "silver.artworks":
        return silver_artworks_path(root)
    if table == "silver.artists":
        return silver_artists_path(root)
    if table == "gold.current_artworks":
        return gold_table_path(root, "current_artworks")
    if table == "gold.current_artists":
        return gold_table_path(root, "current_artists")
    if table == "gold.price_history":
        return gold_table_path(root, "price_history")
    if table == "gold.artist_statistics":
        return gold_table_path(root, "artist_statistics")
    if table == "gold.market_metrics":
        return gold_table_path(root, "market_metrics")
    if table == "failures":
        if not crawl_date:
            raise ValueError("crawl_date is required for failures")
        return silver_failures_path(root, source, crawl_date)
    raise ValueError(f"Unknown table: {table}")


def list_bronze_partitions(root: Path) -> list[tuple[str, str]]:
    """Return sorted (source, crawl_date) pairs under bronze/."""
    bronze_root = root / "bronze"
    if not bronze_root.is_dir():
        return []
    found: list[tuple[str, str]] = []
    for source_dir in sorted(bronze_root.glob("source=*")):
        if not source_dir.is_dir():
            continue
        source = source_dir.name.split("=", 1)[-1]
        for date_dir in sorted(source_dir.glob("crawl_date=*")):
            if date_dir.is_dir():
                crawl_date = date_dir.name.split("=", 1)[-1]
                found.append((source, crawl_date))
    return found


def list_failure_partitions(root: Path) -> list[tuple[str, str]]:
    failures_root = root / "silver" / "_failures"
    if not failures_root.is_dir():
        return []
    found: list[tuple[str, str]] = []
    for source_dir in sorted(failures_root.glob("source=*")):
        if not source_dir.is_dir():
            continue
        source = source_dir.name.split("=", 1)[-1]
        for date_dir in sorted(source_dir.glob("crawl_date=*")):
            if date_dir.is_dir() and (date_dir / "failures.jsonl").is_file():
                crawl_date = date_dir.name.split("=", 1)[-1]
                found.append((source, crawl_date))
    return found


def table_exists(table: str, path: Path) -> bool:
    if table == "failures":
        return (path / "failures.jsonl").is_file()
    if table == "bronze":
        return path.is_dir() and any(path.glob("*.parquet"))
    return path.exists() and (path / "_delta_log").is_dir()


def summarize_tables(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source, crawl_date in list_bronze_partitions(root):
        path = bronze_partition_path(root, source, crawl_date)
        rows.append(
            {
                "table": "bronze",
                "source": source,
                "crawl_date": crawl_date,
                "path": str(path),
                "status": "ok" if table_exists("bronze", path) else "missing",
            }
        )
    for label, path in (
        ("silver.artworks", silver_artworks_path(root)),
        ("silver.artists", silver_artists_path(root)),
        ("gold.current_artworks", gold_table_path(root, "current_artworks")),
        ("gold.current_artists", gold_table_path(root, "current_artists")),
        ("gold.price_history", gold_table_path(root, "price_history")),
        ("gold.artist_statistics", gold_table_path(root, "artist_statistics")),
        ("gold.market_metrics", gold_table_path(root, "market_metrics")),
    ):
        rows.append(
            {
                "table": label,
                "source": "",
                "crawl_date": "",
                "path": str(path),
                "status": "ok" if path.exists() else "missing",
            }
        )
    for source, crawl_date in list_failure_partitions(root):
        path = silver_failures_path(root, source, crawl_date)
        rows.append(
            {
                "table": "failures",
                "source": source,
                "crawl_date": crawl_date,
                "path": str(path),
                "status": "ok" if table_exists("failures", path) else "missing",
            }
        )
    return rows


def _drop_heavy(df: pd.DataFrame, show_heavy: bool) -> pd.DataFrame:
    if show_heavy:
        return df
    drop_cols = [col for col in HEAVY_COLUMNS if col in df.columns]
    return df.drop(columns=drop_cols) if drop_cols else df


def _apply_search(df: pd.DataFrame, search: str | None) -> pd.DataFrame:
    if not search or not search.strip():
        return df
    needle = search.strip().lower()
    mask = pd.Series(False, index=df.index)
    for col in SEARCH_COLUMNS:
        if col not in df.columns:
            continue
        series = df[col].astype(str).str.lower()
        mask = mask | series.str.contains(re.escape(needle), na=False)
    return df[mask]


def _load_bronze(path: Path, *, limit: int, show_heavy: bool) -> tuple[pd.DataFrame, int]:
    dataset = ds.dataset(str(path), format="parquet")
    total = dataset.count_rows()
    columns = [name for name in dataset.schema.names if show_heavy or name not in HEAVY_COLUMNS]
    table = dataset.to_table(columns=columns if columns else None)
    df = table.to_pandas()
    if limit > 0:
        df = df.head(limit)
    return df, total


def _load_delta(path: Path, *, limit: int, show_heavy: bool) -> tuple[pd.DataFrame, int]:
    from deltalake import DeltaTable

    delta = DeltaTable(str(path))
    df = delta.to_pandas()
    total = len(df)
    df = _drop_heavy(df, show_heavy)
    if limit > 0:
        df = df.head(limit)
    return df, total


def _load_failures(path: Path, *, limit: int) -> tuple[pd.DataFrame, int]:
    manifest = path / "failures.jsonl"
    rows: list[dict] = []
    with manifest.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    total = len(df)
    if limit > 0:
        df = df.head(limit)
    return df, total


def load_table(
    table: str,
    root: Path,
    *,
    source: str = "saatchi",
    crawl_date: str | None = None,
    limit: int = 200,
    search: str | None = None,
    show_heavy: bool = False,
) -> tuple[pd.DataFrame, Path, int]:
    """Load a lakehouse table slice.

    Returns (dataframe, path, total_rows_before_limit_after_search_applied_on_full_load).
    For bronze, search is applied after reading the limited parquet head when possible;
    for small tables we filter the full frame then re-limit.
    """
    path = resolve_table_path(table, root, source=source, crawl_date=crawl_date)
    if not table_exists(table, path):
        raise FileNotFoundError(f"Table path not found: {path}")

    if table == "bronze":
        # Read full partition metadata cheaply; for search load more then filter.
        if search and search.strip():
            df, total = _load_bronze(path, limit=0, show_heavy=show_heavy)
            df = _apply_search(df, search)
            filtered_total = len(df)
            if limit > 0:
                df = df.head(limit)
            return df.reset_index(drop=True), path, filtered_total
        df, total = _load_bronze(path, limit=limit, show_heavy=show_heavy)
        return df.reset_index(drop=True), path, total

    if table == "failures":
        df, total = _load_failures(path, limit=0)
        df = _apply_search(df, search)
        filtered_total = len(df)
        if limit > 0:
            df = df.head(limit)
        return df.reset_index(drop=True), path, filtered_total

    df, total = _load_delta(path, limit=0, show_heavy=show_heavy)
    df = _apply_search(df, search)
    filtered_total = len(df)
    if limit > 0:
        df = df.head(limit)
    return df.reset_index(drop=True), path, filtered_total


def dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Convert binary / nested cells to display-friendly strings."""
    if df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(_cell_to_str)
    return out


def _cell_to_str(value: object) -> object:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str)
    return value
