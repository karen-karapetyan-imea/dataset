# html-crawler

Standalone HTML crawler and ETL for **Saatchi Art** and **Artsper**. No API dependency.

## Setup

```bash
cd html-crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Copy `proxy.txt` (or set `CRAWLER_PROXY` / `--proxy-file`). Load `DATABASE_URL` from `../.env` for imports.

## Crawl

```bash
python main.py \
  --urls state/urls_saatchi.txt \
  --output-dir output \
  --results state/results.jsonl \
  --proxy-file proxy.txt \
  --skip-existing
```

Flags: `--workers`, `--rps`, `--skip-existing`, `--no-results-append`.

Rebuild URL lists from the backup crawl log:

```bash
python scripts/extract_urls_from_results.py \
  --results ../crawler_backup/results.jsonl \
  --output-dir state
```

## Saatchi pipeline

```bash
# Apply DDL once
psql "$DATABASE_URL" -f sql/005_saatchi.sql

# Extract HTML -> JSONL
python store_saatchi_data.py --data-dir output --resume

# Import JSONL -> Postgres
python import_saatchi_to_db.py \
  --db-url "$DATABASE_URL" \
  --html-dir output \
  --artists-jsonl state/saatchi_artists.jsonl \
  --artworks-jsonl state/saatchi_artworks.jsonl

# Or all-in-one
DATA_DIR=output ./scripts/sync_saatchi.sh
```

## Artsper pipeline

```bash
# Discover URLs from sitemap
python scripts/fetch_artsper_sitemap.py --output state/sitemap_urls.txt

# Crawl
python main.py --urls state/sitemap_urls.txt --output-dir output --proxy-file proxy.txt

# Extract
python store_data.py --data-dir output --urls-file state/sitemap_urls.txt

# Import to legacy arts_* tables
python import_to_legacy_db.py \
  --db-url "$DATABASE_URL" \
  --html-dir output \
  --mapping-file state/results.jsonl
```

## Tests

```bash
pytest
```
