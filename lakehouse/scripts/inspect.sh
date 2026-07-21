#!/usr/bin/env bash
# Quick terminal commands for inspecting lakehouse data.
#
# Local (requires Java + activated venv):
#   source lakehouse/.venv/bin/activate
#   ./lakehouse/scripts/inspect.sh summary --crawl-date 2026-07-20
#
# Docker (recommended):
#   ./lakehouse/scripts/inspect.sh docker summary --crawl-date 2026-07-20
#   ./lakehouse/scripts/inspect.sh docker table gold.current_artworks

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

run_local() {
  if [[ -f "$ROOT/lakehouse/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT/lakehouse/.venv/bin/activate"
  fi
  python "$ROOT/lakehouse/scripts/inspect_data.py" "$@"
}

run_docker() {
  docker compose exec spark python /data/lakehouse/scripts/inspect_data.py "$@"
}

usage() {
  cat <<'EOF'
Usage:
  ./lakehouse/scripts/inspect.sh summary [--crawl-date YYYY-MM-DD] [--source saatchi]
  ./lakehouse/scripts/inspect.sh table <table-name> [--limit N] [--columns col1,col2]
  ./lakehouse/scripts/inspect.sh docker summary ...
  ./lakehouse/scripts/inspect.sh docker table gold.current_artworks

Examples:
  ./lakehouse/scripts/inspect.sh docker summary --crawl-date 2026-07-20
  ./lakehouse/scripts/inspect.sh docker table gold.current_artworks --limit 10
  ./lakehouse/scripts/inspect.sh docker table gold.artist_statistics
  ./lakehouse/scripts/inspect.sh docker table silver.artworks --format json --limit 3
  ./lakehouse/scripts/inspect.sh docker table silver.artworks --columns title,artist_name,price,currency
  ./lakehouse/scripts/inspect.sh docker table bronze --crawl-date 2026-07-20 --limit 5
  ./lakehouse/scripts/inspect.sh docker table failures --crawl-date 2026-07-20
EOF
}

MODE="local"
if [[ "${1:-}" == "docker" ]]; then
  MODE="docker"
  shift
fi

CMD="${1:-}"
shift || true

case "$CMD" in
  summary)
    if [[ "$MODE" == "docker" ]]; then
      run_docker "$@"
    else
      run_local "$@"
    fi
    ;;
  table)
    TABLE="${1:-}"
    if [[ -z "$TABLE" ]]; then
      echo "table name is required" >&2
      usage
      exit 1
    fi
    shift
    if [[ "$MODE" == "docker" ]]; then
      run_docker --table "$TABLE" "$@"
    else
      run_local --table "$TABLE" "$@"
    fi
    ;;
  help|-h|--help|"")
    usage
    ;;
  *)
    echo "Unknown command: $CMD" >&2
    usage
    exit 1
    ;;
esac
