#!/usr/bin/env bash
# Incremental Saatchi pipeline: sitemap -> crawl -> extract -> import
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "$0")/_artsper_sync_env.sh"
artsper_sync_root
artsper_sync_load_env

STATE_DIR="${STATE_DIR:-state/saatchi}"
DATA_DIR="${DATA_DIR:-${HTML_DIR:-saatchi_data}}"
HTML_DIR="${HTML_DIR:-$DATA_DIR}"
KNOWN="${KNOWN_URLS:-results.jsonl}"
NEW_URLS="${NEW_URLS_FILE:-$STATE_DIR/urls_new.txt}"
NEW_RESULTS="${NEW_RESULTS_FILE:-$STATE_DIR/results_new.jsonl}"
ARTWORKS_JSONL="${ARTWORKS_JSONL:-$STATE_DIR/saatchi_artworks.jsonl}"
ARTISTS_JSONL="${ARTISTS_JSONL:-$STATE_DIR/saatchi_artists.jsonl}"
ARTWORKS_BATCH="${ARTWORKS_BATCH:-$STATE_DIR/saatchi_artworks_batch.jsonl}"
ARTISTS_BATCH="${ARTISTS_BATCH:-$STATE_DIR/saatchi_artists_batch.jsonl}"
FAILURES_JSONL="${FAILURES_JSONL:-$STATE_DIR/saatchi_parse_failures.jsonl}"
ARTIST_URLS="${ARTIST_URLS_FILE:-$STATE_DIR/urls_artists_new.txt}"
SNAPSHOT="${SITEMAP_SNAPSHOT:-$STATE_DIR/sitemap_entries.snapshot.json}"
LASTMOD_STATE="${SITEMAP_STATE:-$STATE_DIR/sitemap_lastmod.json}"
VERSIONS_DDL="${VERSIONS_DDL:-$ROOT/sql/007_marketplace_versions.sql}"
SYNC_VERSIONS="${SYNC_VERSIONS:-1}"
WORKERS="${WORKERS:-$(nproc 2>/dev/null || echo 4)}"
ENTITY="${ENTITY:-all}"

artsper_sync_proxy_args
if [[ ${#PROXY_ARGS[@]} -gt 0 ]]; then
  CONCURRENCY="${CONCURRENCY:-150}"
else
  CONCURRENCY="${CONCURRENCY:-5}"
fi

source "${VENV:-$ROOT/.venv}/bin/activate" 2>/dev/null || true

ARTWORKS_IMPORT="$ARTWORKS_JSONL"
ARTISTS_IMPORT="$ARTISTS_JSONL"
BATCH_EXTRACT=0

if [[ "${IMPORT_ONLY:-0}" != "1" ]]; then
  if [[ ! -d "$DATA_DIR" ]]; then
    mkdir -p "$DATA_DIR"
  fi

  if [[ "${SKIP_SITEMAP:-0}" != "1" ]]; then
    echo "[sync_saatchi_incremental] fetch sitemap data_dir=$DATA_DIR"
    KNOWN_URLS="$KNOWN" STATE_DIR="$STATE_DIR" ./scripts/fetch_saatchi_sitemap.sh
  fi

  if [[ "${DIFF_ONLY:-0}" == "1" ]]; then
    echo "[sync_saatchi_incremental] DIFF_ONLY=1 done"
    exit 0
  fi

  NEW_COUNT="$(wc -l < "$NEW_URLS" 2>/dev/null | tr -d ' ' || echo 0)"
  if [[ "$NEW_COUNT" != "0" ]]; then
    echo "[sync_saatchi_incremental] crawl new_urls=$NEW_COUNT"
    python3 main.py \
      --urls "$NEW_URLS" \
      --output-dir "$DATA_DIR" \
      --results "$NEW_RESULTS" \
      --no-results-append \
      --workers "$CONCURRENCY" \
      "${PROXY_ARGS[@]}"
    BATCH_EXTRACT=1
  else
    echo "[sync_saatchi_incremental] no new artwork URLs from sitemap"
  fi

  if [[ "${SCRAPE_ONLY:-0}" == "1" ]]; then
    echo "[sync_saatchi_incremental] SCRAPE_ONLY=1 done"
    exit 0
  fi

  if [[ "$BATCH_EXTRACT" == "1" && -f "$NEW_RESULTS" ]]; then
    echo "[sync_saatchi_incremental] batch extract mapping=$NEW_RESULTS"
    python3 "$ROOT/store_saatchi_data.py" \
      --data-dir "$DATA_DIR" \
      --mapping-file "$NEW_RESULTS" \
      --refresh \
      --output-artworks "$ARTWORKS_BATCH" \
      --output-artists "$ARTISTS_BATCH" \
      --failures "$STATE_DIR/saatchi_parse_failures_batch.jsonl" \
      --entity "$ENTITY" \
      --workers "$WORKERS"
    ARTWORKS_IMPORT="$ARTWORKS_BATCH"
    ARTISTS_IMPORT="$ARTISTS_BATCH"
  else
    EXTRACT_ARGS=(
      --data-dir "$DATA_DIR"
      --output-artworks "$ARTWORKS_JSONL"
      --output-artists "$ARTISTS_JSONL"
      --failures "$FAILURES_JSONL"
      --entity "$ENTITY"
      --workers "$WORKERS"
      --resume
    )
    echo "[sync_saatchi_incremental] extract entity=$ENTITY"
    python3 "$ROOT/store_saatchi_data.py" "${EXTRACT_ARGS[@]}"
  fi

  if [[ "${EXTRACT_ONLY:-0}" == "1" ]]; then
    echo "[sync_saatchi_incremental] EXTRACT_ONLY=1 done"
    exit 0
  fi

  if [[ "${ARTIST_PASS:-1}" == "1" && -f "$ARTWORKS_JSONL" ]]; then
    echo "[sync_saatchi_incremental] build artist profile URL list"
    ARTWORKS_JSONL="$ARTWORKS_JSONL" ARTIST_URLS="$ARTIST_URLS" python3 - <<'PY'
import json
from pathlib import Path
import os

artworks = Path(os.environ["ARTWORKS_JSONL"])
out = Path(os.environ["ARTIST_URLS"])
urls: set[str] = set()
if artworks.is_file():
    for line in artworks.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("artist_url"):
            urls.add(row["artist_url"])
        if row.get("artist_external_id"):
            urls.add(f"https://www.saatchiart.com/account/profile/{row['artist_external_id']}")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(sorted(urls)) + ("\n" if urls else ""), encoding="utf-8")
print(len(urls), "artist urls ->", out)
PY
    ARTIST_NEW_COUNT="$(wc -l < "$ARTIST_URLS" 2>/dev/null | tr -d ' ' || echo 0)"
    if [[ "$ARTIST_NEW_COUNT" != "0" ]]; then
      ARTIST_RESULTS="$STATE_DIR/results_artists.jsonl"
      echo "[sync_saatchi_incremental] crawl artist profiles=$ARTIST_NEW_COUNT"
      python3 main.py \
        --urls "$ARTIST_URLS" \
        --output-dir "$DATA_DIR" \
        --results "$ARTIST_RESULTS" \
        --no-results-append \
        --workers "$CONCURRENCY" \
        "${PROXY_ARGS[@]}"
      echo "[sync_saatchi_incremental] batch extract artists mapping=$ARTIST_RESULTS"
      python3 "$ROOT/store_saatchi_data.py" \
        --data-dir "$DATA_DIR" \
        --mapping-file "$ARTIST_RESULTS" \
        --refresh \
        --output-artworks "$ARTWORKS_BATCH" \
        --output-artists "$ARTISTS_BATCH" \
        --failures "$STATE_DIR/saatchi_parse_failures_artists_batch.jsonl" \
        --entity artist \
        --workers "$WORKERS"
      ARTISTS_IMPORT="$ARTISTS_BATCH"
    fi
  fi
fi

if [[ "${EXTRACT_ONLY:-0}" == "1" || "${SCRAPE_ONLY:-0}" == "1" ]]; then
  exit 0
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required for import" >&2
  exit 1
fi

if [[ "${SKIP_DDL:-0}" != "1" ]]; then
  echo "[sync_saatchi_incremental] apply ddl=$VERSIONS_DDL"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$VERSIONS_DDL"
fi

IMPORT_ARGS=(--db-url "$DATABASE_URL" --html-dir "$HTML_DIR")
if [[ "${SYNC_VERSIONS:-0}" == "1" ]]; then
  IMPORT_ARGS+=(--sync-versions)
elif [[ "${SKIP_EXISTING:-1}" == "1" ]]; then
  IMPORT_ARGS+=(--skip-existing)
else
  IMPORT_ARGS+=(--no-skip-existing)
fi
if [[ -f "$NEW_RESULTS" ]]; then
  IMPORT_ARGS+=(--mapping-file "$NEW_RESULTS")
fi
if [[ -f "$ARTISTS_IMPORT" ]]; then
  IMPORT_ARGS+=(--artists-jsonl "$ARTISTS_IMPORT")
fi
if [[ -f "$ARTWORKS_IMPORT" ]]; then
  IMPORT_ARGS+=(--artworks-jsonl "$ARTWORKS_IMPORT")
fi

echo "[sync_saatchi_incremental] import sync_versions=${SYNC_VERSIONS:-0}"
python3 "$ROOT/import_saatchi_to_db.py" "${IMPORT_ARGS[@]}"

if [[ "${SKIP_SITEMAP:-0}" != "1" && -f "$SNAPSHOT" ]]; then
  python3 scripts/fetch_marketplace_sitemap.py \
    --source saatchi \
    --update-state-only \
    --snapshot "$SNAPSHOT" \
    --state "$LASTMOD_STATE"
fi

if [[ -f "$NEW_RESULTS" ]]; then
  cat "$NEW_RESULTS" >> "$KNOWN"
fi

echo "[sync_saatchi_incremental] done"
