# Weekly marketplace sync

Standalone HTML crawler and ETL for **Artsper**, **Saatchi Art**, and **Artsy**.

## Setup

```bash
cd html-crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Copy `proxy.txt` (or set `CRAWLER_PROXY` / `--proxy-file`). Load `DATABASE_URL` from `../.env` for imports.

## Weekly incremental jobs (remote: intersa)

```bash
cd /home/intersa/dataset/dataset/html-crawler
source .venv/bin/activate
export ENV_FILE=/home/intersa/dataset/.env
```

### Artsper (Sun 02:00)

```bash
HTML_DIR=/home/intersa/html-crawler/artsper_data \
URL_SOURCE=sitemap \
./scripts/sync_artsper_incremental.sh
```

Dry-run: `DIFF_ONLY=1 URL_SOURCE=sitemap ./scripts/sync_artsper_incremental.sh`

### Saatchi (Sun 04:00)

```bash
DATA_DIR=/home/intersa/html-crawler/saatchi_data \
HTML_DIR=/home/intersa/html-crawler/saatchi_data \
./scripts/sync_saatchi_incremental.sh
```

Or: `./scripts/run_saatchi_intersa.sh`

### Artsy (Sun 06:00)

```bash
HTML_DIR=/home/intersa/html-crawler/artsy_data \
./scripts/sync_artsy_incremental.sh
```

### Cron template

```cron
0 2 * * 0 intersa bash -lc 'cd /home/intersa/dataset/dataset/html-crawler && source .venv/bin/activate && ENV_FILE=/home/intersa/dataset/.env HTML_DIR=/home/intersa/html-crawler/artsper_data URL_SOURCE=sitemap ./scripts/sync_artsper_incremental.sh' >> /var/log/artsper-sync.log 2>&1
0 4 * * 0 intersa bash -lc 'cd /home/intersa/dataset/dataset/html-crawler && source .venv/bin/activate && ENV_FILE=/home/intersa/dataset/.env DATA_DIR=/home/intersa/html-crawler/saatchi_data ./scripts/sync_saatchi_incremental.sh' >> /var/log/saatchi-sync.log 2>&1
0 6 * * 0 intersa bash -lc 'cd /home/intersa/dataset/dataset/html-crawler && source .venv/bin/activate && ENV_FILE=/home/intersa/dataset/.env HTML_DIR=/home/intersa/html-crawler/artsy_data ./scripts/sync_artsy_incremental.sh' >> /var/log/artsy-sync.log 2>&1
```

## Validation checklist

1. `DIFF_ONLY=1` — review `state/{marketplace}/sitemap_diff.json`
2. Crawl completes — `results_new.jsonl` line count matches `urls_new.txt`
3. DB counts increase — `SELECT COUNT(*) FROM ...`
4. Import logs show `versioned=N` when prices changed; second run `versioned≈0`
5. Next-day `DIFF_ONLY=1` — near-zero new URLs

## Per-marketplace state dirs

| Marketplace | State dir | Sitemap script |
|-------------|-----------|----------------|
| Artsper | `state/artsper/` | `fetch_artsper_sitemap.sh` |
| Saatchi | `state/saatchi/` | `fetch_saatchi_sitemap.sh` |
| Artsy | `state/artsy/` | `fetch_artsy_sitemap.sh` |

## Phase flags (all incremental scripts)

| Flag | Effect |
|------|--------|
| `DIFF_ONLY=1` | Sitemap diff report only |
| `SCRAPE_ONLY=1` | Diff + crawl, skip import |
| `EXTRACT_ONLY=1` | Skip import (Saatchi/Artsy) |
| `IMPORT_ONLY=1` | Import latest results only |
| `SYNC_VERSIONS=1` | Compare batch vs DB, write `marketplace_entity_versions` on change (cron default) |
| `SKIP_EXISTING=1` | Bulk import: insert new IDs only, no version history |
| `SKIP_EXISTING=0` | Upsert rows even if id exists (no version history) |
| `SKIP_DDL=1` | Skip applying `sql/007_marketplace_versions.sql` |

## Entity versioning

Weekly crons default to `SYNC_VERSIONS=1`. Each run:

1. Sitemap diff finds new + lastmod-changed URLs
2. Crawl re-fetches those URLs (no `--skip-existing` on the incremental batch)
3. Extract writes batch JSONL (`*_batch.jsonl` for Saatchi/Artsy)
4. Import compares tracked fields vs current DB row
5. On change: append to `marketplace_entity_versions` and update the current table

Apply DDL once (or let sync scripts apply it):

```bash
psql "$DATABASE_URL" -f sql/007_marketplace_versions.sql
```

Example: price history for a Saatchi artwork:

```sql
SELECT entity_id, version_no,
       previous_snapshot->>'price' AS old_price,
       current_snapshot->>'price' AS new_price,
       changed_fields,
       observed_at
FROM marketplace_entity_versions
WHERE marketplace = 'saatchi' AND entity_type = 'artwork' AND entity_id = '9336593'
ORDER BY version_no;
```

Bulk first-time import (e.g. large JSONL on intersa without a crawl batch):

```bash
IMPORT_ONLY=1 SKIP_EXISTING=1 SYNC_VERSIONS=0 ./scripts/sync_saatchi_incremental.sh
```

## Full batch Saatchi (legacy)

```bash
DATA_DIR=output RESUME=1 ./scripts/sync_saatchi.sh
```

## Tests

```bash
pytest
```

## Artsy schema

See [docs/artsy_schema.md](docs/artsy_schema.md) and `sql/006_artsy.sql`.
