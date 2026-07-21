#!/usr/bin/env bash
# Fetch Artsper artist/artwork URLs from https://www.artsper.com/sitemap.xml
# and write only new/updated entities to state/urls_new.txt.
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
INDEX="${SITEMAP_URL:-https://www.artsper.com/sitemap.xml}"
KNOWN="${KNOWN_URLS:-results.jsonl}"

source "${VENV:-$ROOT/.venv}/bin/activate" 2>/dev/null || true

ARGS=(
  --index "$INDEX"
  --known "$KNOWN"
  --out-all "$STATE_DIR/sitemap_urls.txt"
  --out-new "$STATE_DIR/urls_new.txt"
  --report "$STATE_DIR/sitemap_diff.json"
  --state "$STATE_DIR/sitemap_lastmod.json"
)

if [[ -n "${DATABASE_URL:-}" ]]; then
  ARGS+=(--known-db-url "$DATABASE_URL")
fi

if [[ "${UPDATE_SITEMAP_STATE:-0}" == "1" ]]; then
  ARGS+=(--update-state)
fi

python3 scripts/fetch_artsper_sitemap.py "${ARGS[@]}"
