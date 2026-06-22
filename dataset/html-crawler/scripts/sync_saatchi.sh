#!/usr/bin/env bash
# Saatchi pipeline: DDL → extract HTML → import saatchi_artists / saatchi_artworks
#
# Full run:
#   DATA_DIR=/path/to/saatchi_html ./scripts/sync_saatchi.sh
#
# Phase flags:
#   DDL_ONLY=1        apply 005_saatchi.sql only
#   EXTRACT_ONLY=1    run store_saatchi_data.py only (skip DDL + import)
#   IMPORT_ONLY=1     run import_saatchi_to_db.py only (skip DDL + extract)
#
# Env:
#   DATABASE_URL      loaded from .env if unset
#   ENV_FILE          override .env path
#   DATA_DIR          flat directory of sha1.html files (required unless IMPORT_ONLY=1)
#   STATE_DIR         default state/
#   WORKERS           process pool for extraction (default: CPU count)
#   RESUME=1          append/skip already extracted source_file in JSONL
#   SKIP_EXISTING=1   skip DB rows that already exist (default)
#   ENTITY            all | artwork | artist (default all)
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "$0")/_artsper_sync_env.sh"
artsper_sync_root
artsper_sync_load_env

STATE_DIR="${STATE_DIR:-state}"
ARTWORKS_JSONL="${ARTWORKS_JSONL:-$STATE_DIR/saatchi_artworks.jsonl}"
ARTISTS_JSONL="${ARTISTS_JSONL:-$STATE_DIR/saatchi_artists.jsonl}"
FAILURES_JSONL="${FAILURES_JSONL:-$STATE_DIR/saatchi_parse_failures.jsonl}"
DDL_FILE="${DDL_FILE:-$ROOT/sql/005_saatchi.sql}"
WORKERS="${WORKERS:-$(nproc 2>/dev/null || echo 4)}"
ENTITY="${ENTITY:-all}"

source "${VENV:-$ROOT/.venv}/bin/activate" 2>/dev/null || true

if [[ "${IMPORT_ONLY:-0}" != "1" ]]; then
  if [[ -z "${DATA_DIR:-}" ]]; then
    echo "Set DATA_DIR to the flat directory of Saatchi sha1.html files" >&2
    exit 1
  fi
  if [[ ! -d "$DATA_DIR" ]]; then
    echo "DATA_DIR not found: $DATA_DIR" >&2
    exit 1
  fi
fi

if [[ "${EXTRACT_ONLY:-0}" != "1" && "${IMPORT_ONLY:-0}" != "1" ]]; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required for DDL and import (set in .env or environment)" >&2
    exit 1
  fi
  if [[ ! -f "$DDL_FILE" ]]; then
    echo "DDL file not found: $DDL_FILE" >&2
    exit 1
  fi
  echo "[sync_saatchi] apply ddl=$DDL_FILE"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$DDL_FILE"
fi

if [[ "${DDL_ONLY:-0}" == "1" ]]; then
  echo "[sync_saatchi] DDL_ONLY=1 done"
  exit 0
fi

if [[ "${IMPORT_ONLY:-0}" != "1" ]]; then
  EXTRACT_ARGS=(
    --data-dir "$DATA_DIR"
    --output-artworks "$ARTWORKS_JSONL"
    --output-artists "$ARTISTS_JSONL"
    --failures "$FAILURES_JSONL"
    --entity "$ENTITY"
    --workers "$WORKERS"
  )
  if [[ "${RESUME:-0}" == "1" ]]; then
    EXTRACT_ARGS+=(--resume)
  fi
  if [[ -n "${LIMIT:-}" ]]; then
    EXTRACT_ARGS+=(--limit "$LIMIT")
  fi

  echo "[sync_saatchi] extract data_dir=$DATA_DIR workers=$WORKERS entity=$ENTITY"
  python3 "$ROOT/store_saatchi_data.py" "${EXTRACT_ARGS[@]}"
fi

if [[ "${EXTRACT_ONLY:-0}" == "1" ]]; then
  echo "[sync_saatchi] EXTRACT_ONLY=1 done"
  exit 0
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required for import" >&2
  exit 1
fi

HTML_DIR="${HTML_DIR:-$DATA_DIR}"
IMPORT_ARGS=(--db-url "$DATABASE_URL" --html-dir "$HTML_DIR")

if [[ "${SKIP_EXISTING:-1}" == "1" ]]; then
  IMPORT_ARGS+=(--skip-existing)
else
  IMPORT_ARGS+=(--no-skip-existing)
fi

if [[ -f "$ARTISTS_JSONL" ]]; then
  IMPORT_ARGS+=(--artists-jsonl "$ARTISTS_JSONL")
fi
if [[ -f "$ARTWORKS_JSONL" ]]; then
  IMPORT_ARGS+=(--artworks-jsonl "$ARTWORKS_JSONL")
fi

if [[ ! -f "$ARTISTS_JSONL" && ! -f "$ARTWORKS_JSONL" ]]; then
  echo "No JSONL files found to import: $ARTISTS_JSONL / $ARTWORKS_JSONL" >&2
  exit 1
fi

if [[ -n "${LIMIT:-}" ]]; then
  IMPORT_ARGS+=(--limit "$LIMIT")
fi

echo "[sync_saatchi] import artists=$ARTISTS_JSONL artworks=$ARTWORKS_JSONL"
python3 "$ROOT/import_saatchi_to_db.py" "${IMPORT_ARGS[@]}"

echo "[sync_saatchi] done"
