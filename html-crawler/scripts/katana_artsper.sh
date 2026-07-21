#!/usr/bin/env bash
# Discover Artsper artist/artwork URLs with Katana.
#
# Usage:
#   ./scripts/katana_artsper.sh
#   OUTPUT=state/katana.jsonl JSONL=1 ./scripts/katana_artsper.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SEED="${KATANA_SEED:-https://www.artsper.com/us}"
DEPTH="${KATANA_DEPTH:-4}"
OUTPUT="${KATANA_OUTPUT:-state/katana_urls.txt}"
CONCURRENCY="${KATANA_CONCURRENCY:-20}"

mkdir -p "$(dirname "$OUTPUT")"

ARGS=(
  -u "$SEED"
  -d "$DEPTH"
  -jc
  -kf all
  -c "$CONCURRENCY"
  -mr 'contemporary-artworks|contemporary-artists'
  -o "$OUTPUT"
)

if [[ "${JSONL:-0}" == "1" ]]; then
  ARGS+=(-j)
fi

echo "[katana_artsper] seed=$SEED depth=$DEPTH output=$OUTPUT"
katana "${ARGS[@]}"
echo "[katana_artsper] done lines=$(wc -l < "$OUTPUT" | tr -d ' ')"
