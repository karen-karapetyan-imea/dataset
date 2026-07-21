# html-crawler

Standalone HTML crawler and ETL for **Saatchi Art**, **Artsper**, and **Artsy** (sitemap discovery). No API dependency.

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
  --urls state/urls_saatchiart.txt \
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
# Discover URLs from sitemap (all entity URLs)
python scripts/fetch_saatchi_sitemap.py --out-all state/urls_saatchiart.txt

# Or via wrapper
./scripts/fetch_saatchi_sitemap.sh

# Incremental: new + updated URLs only
python scripts/fetch_saatchi_sitemap.py \
  --known state/results.jsonl \
  --update-state

# Crawl
python main.py \
  --urls state/urls_saatchiart.txt \
  --output-dir output \
  --results state/results.jsonl \
  --proxy-file proxy.txt \
  --skip-existing

# Apply DDL once
psql "$DATABASE_URL" -f sql/005_saatchi.sql
psql "$DATABASE_URL" -f sql/006_entity_history.sql

# Extract HTML -> JSONL
python store_saatchi_data.py --data-dir output --resume

# Import JSONL -> Postgres
python import_saatchi_to_db.py \
  --db-url "$DATABASE_URL" \
  --html-dir output \
  --artists-jsonl state/saatchi_artists.jsonl \
  --artworks-jsonl state/saatchi_artworks.jsonl

# Or all-in-one
# Note: to record history for changes, re-import existing rows:
#   SKIP_EXISTING=0 DATA_DIR=output ./scripts/sync_saatchi.sh
DATA_DIR=output ./scripts/sync_saatchi.sh
```

Outputs: `state/urls_saatchiart.txt` (all), `state/urls_saatchi_new.txt` (diff), `state/saatchi_sitemap_diff.json`.

## Artsper pipeline

```bash
# Note: enable history before running the importer:
#   psql "$DATABASE_URL" -f sql/006_entity_history.sql
# Add artist_url / artwork_url columns (once):
#   psql "$DATABASE_URL" -f sql/007_arts_urls.sql

# Discover URLs from sitemap
python scripts/fetch_artsper_sitemap.py --out-all state/sitemap_urls.txt

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

## Artsy pipeline (sitemap)

Discovers artist/artwork URLs from Artsy sitemap indexes. HTML parse and DB import are not implemented yet — this only produces URL lists for crawling.

```bash
# Discover URLs (uses curl_cffi; proxy recommended behind Cloudflare)
python scripts/fetch_artsy_sitemap.py --proxy-file proxy.txt --update-state

# Or via wrapper
UPDATE_SITEMAP_STATE=1 ./scripts/fetch_artsy_sitemap.sh

# Crawl discovered URLs (optional next step)
python main.py \
  --urls state/artsy_urls_new.txt \
  --output-dir output \
  --results state/artsy_results.jsonl \
  --proxy-file proxy.txt
```

Outputs: `state/artsy_sitemap_urls.txt`, `state/artsy_urls_new.txt`, `state/artsy_sitemap_diff.json`.

## Tests

```bash
pytest
```
