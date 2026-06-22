#!/usr/bin/env bash
# Incremental Artsper pipeline:
#   sitemap.xml or Katana URL dump -> diff -> crawl new only -> import to catalog_*
#
# Env:
#   URL_SOURCE=sitemap   use https://www.artsper.com/sitemap.xml (recommended)
#   SITEMAP_URL          override sitemap index URL
#   KATANA_URLS          Katana output when URL_SOURCE!=sitemap
#   DATABASE_URL         required for import (auto-loaded from .env)
#   HTML_DIR             default artsper_data/ if present, else output/
#   PROXY_FILE           default proxy.txt when present
#   USE_PROXY=0          disable proxies
#   CONCURRENCY          default 150 with proxy, 5 without
#   SCRAPE_ONLY=1        diff + crawl only, skip import
#   IMPORT_ONLY=1        import latest new-results only
#   DIFF_ONLY=1          report only
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "$0")/_artsper_sync_env.sh"
artsper_sync_root
artsper_sync_load_env
artsper_sync_default_html_dir
artsper_sync_proxy_args

STATE_DIR="${STATE_DIR:-state}"
KNOWN="${KNOWN_URLS:-results.jsonl}"
KATANA="${KATANA_URLS:-}"
NEW_URLS="${NEW_URLS_FILE:-$STATE_DIR/urls_new.txt}"
NEW_RESULTS="${NEW_RESULTS_FILE:-$STATE_DIR/results_new.jsonl}"
DIFF_REPORT="${DIFF_REPORT:-$STATE_DIR/url_diff.json}"
SOURCE="${CRAWL_SOURCE:-artsper}"

if [[ ${#PROXY_ARGS[@]} -gt 0 ]]; then
  CONCURRENCY="${CONCURRENCY:-150}"
else
  CONCURRENCY="${CONCURRENCY:-5}"
  echo "[sync_artsper_incremental] warning: no proxy.txt — using concurrency=$CONCURRENCY" >&2
fi

source "${VENV:-$ROOT/.venv}/bin/activate" 2>/dev/null || true

if [[ "${IMPORT_ONLY:-0}" != "1" ]]; then
  if [[ "${URL_SOURCE:-}" == "sitemap" || -n "${SITEMAP_URL:-}" ]]; then
    echo "[sync_artsper_incremental] fetch sitemap index=${SITEMAP_URL:-https://www.artsper.com/sitemap.xml} html_dir=$HTML_DIR"
    SITEMAP_URL="${SITEMAP_URL:-https://www.artsper.com/sitemap.xml}" \
      KNOWN_URLS="$KNOWN" STATE_DIR="$STATE_DIR" HTML_DIR="$HTML_DIR" \
      ./scripts/fetch_artsper_sitemap.sh
    DIFF_REPORT="${DIFF_REPORT:-$STATE_DIR/sitemap_diff.json}"
  else
    if [[ -z "$KATANA" ]]; then
      echo "Set URL_SOURCE=sitemap or KATANA_URLS (path to Katana output txt/jsonl)" >&2
      exit 1
    fi
    if [[ ! -f "$KATANA" ]]; then
      echo "KATANA_URLS file not found: $KATANA" >&2
      exit 1
    fi

    echo "[sync_artsper_incremental] diff katana=$KATANA known=$KNOWN"
    PREPARE_ARGS=(
      "$KATANA"
      --known "$KNOWN"
      --out-new "$NEW_URLS"
      --report "$DIFF_REPORT"
    )
    if [[ -n "${DATABASE_URL:-}" ]]; then
      PREPARE_ARGS+=(--known-db-url "$DATABASE_URL")
    fi
    python3 scripts/prepare_artsper_urls.py "${PREPARE_ARGS[@]}"
  fi

  if [[ "${DIFF_ONLY:-0}" == "1" ]]; then
    echo "[sync_artsper_incremental] DIFF_ONLY=1 done"
    exit 0
  fi

  NEW_COUNT="$(wc -l < "$NEW_URLS" | tr -d ' ')"
  if [[ "$NEW_COUNT" == "0" ]]; then
    echo "[sync_artsper_incremental] no new URLs to crawl"
    exit 0
  fi

  echo "[sync_artsper_incremental] crawl new_urls=$NEW_COUNT html_dir=$HTML_DIR workers=$CONCURRENCY"
  python3 main.py \
    --urls "$NEW_URLS" \
    --output-dir "$HTML_DIR" \
    --results "$NEW_RESULTS" \
    --no-results-append \
    --skip-existing \
    --workers "$CONCURRENCY" \
    "${PROXY_ARGS[@]}"
fi

if [[ "${SCRAPE_ONLY:-0}" == "1" || "${DIFF_ONLY:-0}" == "1" ]]; then
  echo "[sync_artsper_incremental] scrape-only done"
  exit 0
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required for import" >&2
  exit 1
fi

IMPORT_MAPPING="${IMPORT_MAPPING_FILE:-$NEW_RESULTS}"
if [[ ! -f "$IMPORT_MAPPING" ]]; then
  echo "Import mapping not found: $IMPORT_MAPPING" >&2
  exit 1
fi

echo "[sync_artsper_incremental] import mapping=$IMPORT_MAPPING"
python3 import_to_legacy_db.py \
  --db-url "$DATABASE_URL" \
  --html-dir "$HTML_DIR" \
  --mapping-file "$IMPORT_MAPPING"

if [[ "${URL_SOURCE:-}" == "sitemap" || -n "${SITEMAP_URL:-}" ]]; then
  python3 scripts/fetch_artsper_sitemap.py --update-state-only \
    --snapshot "$STATE_DIR/sitemap_entries.snapshot.json" \
    --state "$STATE_DIR/sitemap_lastmod.json"
fi

echo "[sync_artsper_incremental] done"
