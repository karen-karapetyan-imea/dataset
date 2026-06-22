#!/usr/bin/env bash
# Phase 2: import HTML on disk into arts_artists / arts_artworks.
#
# From crawl results JSONL:
#   ./scripts/import_artsper_catalog.sh
#
# From full sitemap URL list (imports only URLs that have HTML files):
#   IMPORT_URLS_FILE=state/sitemap_urls.txt ./scripts/import_artsper_catalog.sh
set -euo pipefail

export IMPORT_ONLY=1
export IMPORT_URLS_FILE="${IMPORT_URLS_FILE:-}"
export IMPORT_MAPPING_FILE="${IMPORT_MAPPING_FILE:-state/results_new.jsonl}"
exec "$(dirname "$0")/sync_artsper_incremental.sh"
