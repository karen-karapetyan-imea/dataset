#!/usr/bin/env bash
# Fetch Artsy artist/artwork URLs from sitemap indexes and write
# new/updated entities to state/artsy_urls_new.txt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${DATABASE_URL:-}" ]]; then
  for env_file in "${ENV_FILE:-}" "$ROOT/.env" "$ROOT/../.env"; do
    [[ -n "$env_file" && -f "$env_file" ]] || continue
    set -a && source "$env_file" && set +a
    break
  done
fi

STATE_DIR="${STATE_DIR:-state}"
KNOWN="${KNOWN_URLS:-}"
PROXY_FILE="${PROXY_FILE:-}"
if [[ -z "$PROXY_FILE" && -f "$ROOT/proxy.txt" ]]; then
  PROXY_FILE="$ROOT/proxy.txt"
fi

source "${VENV:-$ROOT/.venv}/bin/activate" 2>/dev/null || true

ARGS=(
  --out-all "$STATE_DIR/artsy_sitemap_urls.txt"
  --out-new "$STATE_DIR/artsy_urls_new.txt"
  --report "$STATE_DIR/artsy_sitemap_diff.json"
  --state "$STATE_DIR/artsy_sitemap_lastmod.json"
)

if [[ -n "$KNOWN" ]]; then
  ARGS+=(--known "$KNOWN")
fi

if [[ -n "$PROXY_FILE" ]]; then
  ARGS+=(--proxy-file "$PROXY_FILE")
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  ARGS+=(--known-db-url "$DATABASE_URL")
fi

if [[ "${UPDATE_SITEMAP_STATE:-0}" == "1" ]]; then
  ARGS+=(--update-state)
fi

python3 scripts/fetch_artsy_sitemap.py "${ARGS[@]}"
