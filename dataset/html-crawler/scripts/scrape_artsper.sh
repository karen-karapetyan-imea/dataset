#!/usr/bin/env bash
# Phase 1: download HTML only (no DB import).
#
# Incremental (new URLs from sitemap diff):
#   URL_SOURCE=sitemap ./scripts/scrape_artsper.sh
#
# Full sitemap (~286k URLs, resumable via --skip-existing + RESUME_CRAWL):
#   URL_SOURCE=sitemap FULL_CRAWL=1 RESUME_CRAWL=1 ./scripts/scrape_artsper.sh
set -euo pipefail

export URL_SOURCE="${URL_SOURCE:-sitemap}"
export SCRAPE_ONLY=1
exec "$(dirname "$0")/sync_artsper_incremental.sh"
