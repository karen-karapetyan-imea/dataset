#!/usr/bin/env bash
# Incremental Artsy pipeline: sitemap -> crawl -> extract -> import
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "$0")/_artsper_sync_env.sh"
artsper_sync_root
artsper_sync_load_env

STATE_DIR="${STATE_DIR:-state/artsy}"
HTML_DIR="${HTML_DIR:-artsy_data}"
KNOWN="${KNOWN_URLS:-results.jsonl}"
NEW_URLS="${NEW_URLS_FILE:-$STATE_DIR/urls_new.txt}"
NEW_RESULTS="${NEW_RESULTS_FILE:-$STATE_DIR/results_new.jsonl}"
SNAPSHOT="${SITEMAP_SNAPSHOT:-$STATE_DIR/sitemap_entries.snapshot.json}"
LASTMOD_STATE="${SITEMAP_STATE:-$STATE_DIR/sitemap_lastmod.json}"
DDL_FILE="${DDL_FILE:-$ROOT/sql/006_artsy.sql}"
VERSIONS_DDL="${VERSIONS_DDL:-$ROOT/sql/007_marketplace_versions.sql}"
SYNC_VERSIONS="${SYNC_VERSIONS:-1}"
STATE_SUFFIX="${STATE_SUFFIX:-}"
WORKERS="${WORKERS:-$(nproc 2>/dev/null || echo 4)}"
ENTITY="${ENTITY:-all}"

artsper_sync_proxy_args
if [[ ${#PROXY_ARGS[@]} -gt 0 ]]; then
  CONCURRENCY="${CONCURRENCY:-150}"
else
  CONCURRENCY="${CONCURRENCY:-5}"
fi

source "${VENV:-$ROOT/.venv}/bin/activate" 2>/dev/null || true

if [[ "${IMPORT_ONLY:-0}" != "1" ]]; then
  mkdir -p "$HTML_DIR"

  if [[ "${DDL_ONLY:-0}" == "1" ]]; then
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$DDL_FILE"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$VERSIONS_DDL"
    echo "[sync_artsy_incremental] DDL_ONLY=1 done"
    exit 0
  fi

  if [[ -n "${DATABASE_URL:-}" && "${SKIP_DDL:-0}" != "1" && "${DIFF_ONLY:-0}" != "1" ]]; then
    echo "[sync_artsy_incremental] apply ddl=$DDL_FILE"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$DDL_FILE"
    echo "[sync_artsy_incremental] apply ddl=$VERSIONS_DDL"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$VERSIONS_DDL"
  fi

  echo "[sync_artsy_incremental] fetch sitemaps"
  KNOWN_URLS="$KNOWN" STATE_DIR="$STATE_DIR" ./scripts/fetch_artsy_sitemap.sh

  if [[ "${DIFF_ONLY:-0}" == "1" ]]; then
    echo "[sync_artsy_incremental] DIFF_ONLY=1 done"
    exit 0
  fi

  NEW_COUNT="$(wc -l < "$NEW_URLS" 2>/dev/null | tr -d ' ' || echo 0)"
  if [[ "$NEW_COUNT" != "0" ]]; then
    echo "[sync_artsy_incremental] crawl new_urls=$NEW_COUNT"
    python3 main.py \
      --urls "$NEW_URLS" \
      --output-dir "$HTML_DIR" \
      --results "$NEW_RESULTS" \
      --no-results-append \
      --workers "$CONCURRENCY" \
      "${PROXY_ARGS[@]}"
    STATE_SUFFIX="_batch"
  else
    echo "[sync_artsy_incremental] no new URLs from sitemap"
  fi

  if [[ "${SCRAPE_ONLY:-0}" == "1" ]]; then
    echo "[sync_artsy_incremental] SCRAPE_ONLY=1 done"
    exit 0
  fi

  EXTRACT_ARGS=(
    --data-dir "$HTML_DIR"
    --state-dir "$STATE_DIR"
    --entity "$ENTITY"
    --workers "$WORKERS"
  )
  if [[ "$STATE_SUFFIX" == "_batch" && -f "$NEW_RESULTS" ]]; then
    EXTRACT_ARGS+=(--mapping-file "$NEW_RESULTS" --refresh --output-suffix "$STATE_SUFFIX")
    echo "[sync_artsy_incremental] batch extract mapping=$NEW_RESULTS"
  else
    EXTRACT_ARGS+=(--resume)
    echo "[sync_artsy_incremental] extract entity=$ENTITY"
  fi
  python3 "$ROOT/store_artsy_data.py" "${EXTRACT_ARGS[@]}"

  if [[ "${EXTRACT_ONLY:-0}" == "1" ]]; then
    echo "[sync_artsy_incremental] EXTRACT_ONLY=1 done"
    exit 0
  fi
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required for import" >&2
  exit 1
fi

if [[ "${IMPORT_ONLY:-0}" == "1" && "${SKIP_DDL:-0}" != "1" ]]; then
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$VERSIONS_DDL"
fi

IMPORT_ARGS=(--db-url "$DATABASE_URL" --html-dir "$HTML_DIR" --state-dir "$STATE_DIR")
if [[ "${SYNC_VERSIONS:-0}" == "1" ]]; then
  IMPORT_ARGS+=(--sync-versions)
elif [[ "${SKIP_EXISTING:-1}" == "1" ]]; then
  IMPORT_ARGS+=(--skip-existing)
else
  IMPORT_ARGS+=(--no-skip-existing)
fi
if [[ -n "$STATE_SUFFIX" ]]; then
  IMPORT_ARGS+=(--state-suffix "$STATE_SUFFIX")
fi
if [[ -f "$NEW_RESULTS" ]]; then
  IMPORT_ARGS+=(--mapping-file "$NEW_RESULTS")
fi

echo "[sync_artsy_incremental] import sync_versions=${SYNC_VERSIONS:-0} state_suffix=${STATE_SUFFIX:-}"
python3 "$ROOT/import_artsy_to_db.py" "${IMPORT_ARGS[@]}"

if [[ -f "$SNAPSHOT" ]]; then
  python3 scripts/fetch_marketplace_sitemap.py \
    --source artsy \
    --update-state-only \
    --snapshot "$SNAPSHOT" \
    --state "$LASTMOD_STATE"
fi

if [[ -f "$NEW_RESULTS" ]]; then
  cat "$NEW_RESULTS" >> "$KNOWN"
fi

echo "[sync_artsy_incremental] done"
