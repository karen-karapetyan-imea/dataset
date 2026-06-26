#!/usr/bin/env bash
# Saatchi weekly sync for /home/intersa/dataset
set -euo pipefail

DATASET_ROOT="${DATASET_ROOT:-/home/intersa/dataset/dataset}"
HTML_CRAWLER="${HTML_CRAWLER:-$DATASET_ROOT/html-crawler}"
DATA_DIR="${DATA_DIR:-/home/intersa/html-crawler/saatchi_data}"
ENV_FILE="${ENV_FILE:-$DATASET_ROOT/.env}"

if [[ ! -d "$HTML_CRAWLER" ]]; then
  echo "html-crawler not found: $HTML_CRAWLER" >&2
  exit 1
fi

cd "$HTML_CRAWLER"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements-dev.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export ENV_FILE
export DATA_DIR
export HTML_DIR="$DATA_DIR"
export RESUME="${RESUME:-1}"

exec ./scripts/sync_saatchi_incremental.sh
