# Lakehouse

Local Bronze/Silver/Gold lakehouse for HTML crawler outputs. The `html-crawler/` project remains the source of truth for crawling and Saatchi/Artsper parsing; this project adds Spark + Delta processing and an Artsy parser.

## Setup

```bash
cd lakehouse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Requires Java 11+ for Spark.

Environment variables (see `../.env.example`):

- `LAKEHOUSE_DATA_ROOT` — repo root containing `bronze/`, `silver/`, `gold/`
- `HTML_CRAWLER_ROOT` — path to `html-crawler/` for parser imports

## Pipeline

```
crawler HTML + results.jsonl
  → Bronze Parquet (append-only)
  → Silver Delta (artworks, artists)
  → Gold Delta (analytics)
```

### Write Bronze

```bash
python lakehouse/jobs/write_bronze.py \
  --input html-crawler/output \
  --mapping html-crawler/state/results_new.jsonl \
  --source saatchi \
  --crawl-date 2026-07-20
```

### Bronze → Silver

```bash
python lakehouse/jobs/bronze_to_silver.py --source saatchi --crawl-date 2026-07-20
```

### Silver → Gold

```bash
python lakehouse/jobs/silver_to_gold.py
```

This writes:

- `gold/current_artworks`
- `gold/current_artists` (from `silver/artists`, or bootstrapped from artwork `artist_id` / `artist_profile_url` when artist pages are not crawled yet)
- `gold/price_history`
- `gold/artist_statistics`
- `gold/market_metrics`

### Artists pipeline

Artwork pages already carry `artist_id` and `artist_profile_url`. To enrich full artist profiles (biography, country, etc.):

```bash
# 1. Export unique artist profile URLs for the crawler
python lakehouse/jobs/export_artist_urls.py

# 2. Crawl those URLs with html-crawler (uses html-crawler/state/urls_saatchi_artists.txt)

# 3. Ingest artist HTML into Bronze, then Silver → Gold
python lakehouse/jobs/write_bronze.py \
  --input html-crawler/output \
  --mapping html-crawler/state/results.jsonl \
  --source saatchi \
  --crawl-date 2026-07-20
python lakehouse/jobs/bronze_to_silver.py --source saatchi --crawl-date 2026-07-20
python lakehouse/jobs/silver_to_gold.py
```

Inspect artists:

```bash
docker compose exec spark python /data/lakehouse/scripts/inspect_data.py \
  --table gold.current_artists --limit 10
```

### Migrate historical data

```bash
python lakehouse/jobs/migrate_legacy.py \
  --mapping crawler_backup/results.jsonl \
  --html-dirs html-crawler/output,html-crawler/artsper_data,html-crawler/saatchi_html
```

## Docker

```bash
docker compose up -d spark
docker compose exec spark python /data/lakehouse/jobs/write_bronze.py \
  --input /data/html-crawler/output \
  --mapping /data/html-crawler/state/results_new.jsonl \
  --source saatchi \
  --crawl-date 2026-07-20
```

## Tests

```bash
cd lakehouse
pytest
```

## Data layout

```
bronze/source={source}/crawl_date=YYYY-MM-DD/part-*.parquet
silver/artworks/          # Delta table
silver/artists/           # Delta table
gold/current_artworks/    # Delta table
gold/current_artists/     # Delta table
gold/price_history/
gold/artist_statistics/
gold/market_metrics/
```

## Adding a marketplace

1. Add parser under `lakehouse/parsers/`
2. Register it in `lakehouse/parsers/registry.py`
3. Run Bronze ingest with `--source <name>`
