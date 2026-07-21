#!/usr/bin/env python3
"""Streamlit browser for local Bronze / Silver / Gold lakehouse tables."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from data_access import (
    TABLE_CHOICES,
    dataframe_for_display,
    default_data_root,
    list_bronze_partitions,
    list_failure_partitions,
    load_table,
    resolve_table_path,
    summarize_tables,
    table_exists,
)

st.set_page_config(
    page_title="Lakehouse Browser",
    page_icon="🗃️",
    layout="wide",
)


def _init_state() -> None:
    if "refresh_token" not in st.session_state:
        st.session_state.refresh_token = 0
    if "active_query" not in st.session_state:
        st.session_state.active_query = None


def _sidebar() -> dict:
    st.sidebar.title("Lakehouse Browser")
    data_root_str = st.sidebar.text_input(
        "Data root",
        value=str(default_data_root()),
        help="Directory containing bronze/, silver/, gold/",
    )
    root = Path(data_root_str).expanduser().resolve()

    table = st.sidebar.selectbox("Table", TABLE_CHOICES, index=1)

    bronze_parts = list_bronze_partitions(root)
    failure_parts = list_failure_partitions(root)

    sources = sorted(
        {s for s, _ in bronze_parts} | {s for s, _ in failure_parts} | {"saatchi", "artsper", "artsy"}
    )
    source = st.sidebar.selectbox(
        "Source",
        sources,
        index=sources.index("saatchi") if "saatchi" in sources else 0,
    )

    needs_date = table in ("bronze", "failures")
    crawl_date: str | None = None
    if needs_date:
        if table == "bronze":
            dates = [d for s, d in bronze_parts if s == source]
        else:
            dates = [d for s, d in failure_parts if s == source]
        if dates:
            crawl_date = st.sidebar.selectbox("Crawl date", dates)
        else:
            crawl_date = st.sidebar.text_input("Crawl date (YYYY-MM-DD)", value="2026-07-20")

    limit = st.sidebar.number_input("Row limit", min_value=1, max_value=50_000, value=200, step=50)
    search = st.sidebar.text_input("Search", placeholder="title / artist / url / entity_id")
    show_heavy = st.sidebar.checkbox("Show heavy columns (html, raw_json, image_urls)", value=False)

    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        if st.button("Refresh", use_container_width=True):
            st.session_state.refresh_token += 1
    with col_b:
        load = st.button("Load", type="primary", use_container_width=True)

    query = {
        "root": str(root),
        "table": table,
        "source": source,
        "crawl_date": crawl_date,
        "limit": int(limit),
        "search": search.strip() or None,
        "show_heavy": show_heavy,
    }
    if load:
        st.session_state.active_query = query
        st.session_state.refresh_token += 1

    return {"root": root, "query": query}


@st.cache_data(show_spinner=False)
def _cached_load(
    table: str,
    root_str: str,
    source: str,
    crawl_date: str | None,
    limit: int,
    search: str | None,
    show_heavy: bool,
    refresh_token: int,
) -> tuple[pd.DataFrame, str, int]:
    _ = refresh_token
    df, path, total = load_table(
        table,
        Path(root_str),
        source=source,
        crawl_date=crawl_date,
        limit=limit,
        search=search,
        show_heavy=show_heavy,
    )
    return df, str(path), total


def _render_summary(root: Path) -> None:
    st.subheader("Catalog")
    summary = summarize_tables(root)
    if not summary:
        st.info(f"No lakehouse tables found under `{root}`.")
        return
    st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)


def _render_table(query: dict) -> None:
    root = Path(query["root"])
    table = query["table"]
    try:
        path = resolve_table_path(
            table,
            root,
            source=query["source"],
            crawl_date=query["crawl_date"],
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    if not table_exists(table, path):
        st.warning(f"Table not found: `{path}`")
        _render_summary(root)
        return

    with st.spinner(f"Loading {table}…"):
        try:
            df, path_str, total = _cached_load(
                table,
                query["root"],
                query["source"],
                query["crawl_date"],
                query["limit"],
                query["search"],
                query["show_heavy"],
                st.session_state.refresh_token,
            )
        except Exception as exc:
            st.exception(exc)
            return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Table", table)
    m2.metric("Rows shown", len(df))
    m3.metric("Total / filtered", total)
    m4.metric("Columns", len(df.columns))
    st.caption(f"Path: `{path_str}`")

    if df.empty:
        st.info("No rows match the current filters.")
        return

    display_df = dataframe_for_display(df)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.subheader("Row detail")
    row_idx = st.number_input(
        "Row index",
        min_value=0,
        max_value=max(len(df) - 1, 0),
        value=0,
        step=1,
    )
    row = df.iloc[int(row_idx)].to_dict()
    pretty = {}
    for key, value in row.items():
        if isinstance(value, (bytes, bytearray)):
            pretty[key] = f"<{len(value)} bytes>"
        elif isinstance(value, float) and pd.isna(value):
            pretty[key] = None
        else:
            try:
                if isinstance(value, str) and value.strip().startswith(("{", "[")):
                    pretty[key] = json.loads(value)
                else:
                    pretty[key] = value
            except (json.JSONDecodeError, TypeError):
                pretty[key] = value
    st.json(pretty, expanded=False)

    url = row.get("url")
    if isinstance(url, str) and url.startswith("http"):
        st.markdown(f"[Open URL]({url})")


def main() -> None:
    _init_state()
    opts = _sidebar()

    st.title("Medallion Lakehouse")
    st.write("Browse Bronze Parquet and Silver/Gold Delta tables (read-only).")

    active = st.session_state.active_query
    if active:
        _render_table(active)
    else:
        st.info("Choose a table in the sidebar and click **Load**.")
        _render_summary(opts["root"])


if __name__ == "__main__":
    main()
