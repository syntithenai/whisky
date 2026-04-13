#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
DB_PATH="${DB_PATH:-$ROOT_DIR/data/distilleries.db}"
WEB_DATA_PATH="${WEB_DATA_PATH:-$ROOT_DIR/data/web}"

cd "$ROOT_DIR"

if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/serve_site.py" \
  --db "$DB_PATH" \
  --web-data "$WEB_DATA_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  "$@"