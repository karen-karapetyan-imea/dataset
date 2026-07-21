#!/usr/bin/env bash
set -euo pipefail

artsper_sync_root() {
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$ROOT"
}

artsper_sync_load_env() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    artsper_sync_normalize_db_url
    return
  fi
  local candidate
  for candidate in \
    "${ENV_FILE:-}" \
    "$ROOT/.env" \
    "$ROOT/../.env" \
    ; do
    [[ -n "$candidate" && -f "$candidate" ]] || continue
    # shellcheck disable=SC1090
    set -a && source "$candidate" && set +a
    if [[ -n "${DATABASE_URL:-}" ]]; then
      artsper_sync_normalize_db_url
      return
    fi
  done
}

artsper_sync_normalize_db_url() {
  DATABASE_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql:\/\/}"
  DATABASE_URL="${DATABASE_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"
  if [[ "$DATABASE_URL" == *"ssl=require"* && "$DATABASE_URL" != *"sslmode="* ]]; then
    DATABASE_URL="${DATABASE_URL/ssl=require/sslmode=require}"
  fi
  export DATABASE_URL
}

artsper_sync_proxy_args() {
  PROXY_ARGS=()
  if [[ "${USE_PROXY:-1}" == "0" ]]; then
    return
  fi
  local proxy_file="${PROXY_FILE:-}"
  if [[ -z "$proxy_file" && -f "$ROOT/proxy.txt" ]]; then
    proxy_file="$ROOT/proxy.txt"
  fi
  if [[ -n "$proxy_file" ]]; then
    PROXY_ARGS=(--proxy-file "$proxy_file")
  fi
}

artsper_sync_default_html_dir() {
  if [[ -n "${HTML_DIR:-}" ]]; then
    return
  fi
  if [[ -d "$ROOT/artsper_data" ]]; then
    HTML_DIR="$ROOT/artsper_data"
  else
    HTML_DIR="$ROOT/output"
  fi
  export HTML_DIR
}
