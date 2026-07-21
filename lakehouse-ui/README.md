# Lakehouse UI

Standalone Streamlit browser for the local Bronze / Silver / Gold lakehouse.

Does **not** require Spark or Java. Reads Parquet with PyArrow and Delta tables with `deltalake`.

## Setup

```bash
cd lakehouse-ui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
export LAKEHOUSE_DATA_ROOT=/home/samvel/dataset
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

You can also set the data root in the sidebar (directory that contains `bronze/`, `silver/`, `gold/`).

## Features

- Table picker: bronze, silver artworks/artists, gold analytics, parse failures
- Source + crawl date for bronze/failures partitions
- Row limit and text search (`title`, `artist_name`, `url`, `entity_id`)
- Interactive dataframe + expandable row detail
- Heavy columns (`html`, `raw_json`, `image_urls`) hidden by default

## Notes

- Read-only — the UI never writes lakehouse data.
- For very large Bronze partitions, keep the row limit modest or use search after loading.
