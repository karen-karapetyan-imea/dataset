#!/usr/bin/env bash
# Phase 2: import HTML on disk into arts_artists / arts_artworks (run after scrape).
#
# From crawl results JSONL:
#   ./scripts/import_artsper_legacy.sh
#
# From full sitemap URL list (only rows with HTML on disk):
#   IMPORT_URLS_FILE=state/sitemap_urls.txt ./scripts/import_artsper_legacy.sh
#
# Re-upsert rows already in DB:
#   IMPORT_SKIP_EXISTING=0 ./scripts/import_artsper_legacy.sh
set -euo pipefail

export IMPORT_ONLY=1
export IMPORT_URLS_FILE="${IMPORT_URLS_FILE:-}"
export IMPORT_MAPPING_FILE="${IMPORT_MAPPING_FILE:-state/results_new.jsonl}"
export IMPORT_SKIP_EXISTING="${IMPORT_SKIP_EXISTING:-1}"
exec "$(dirname "$0")/sync_artsper_incremental.sh"
