#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOCK_FILE="$ROOT_DIR/.scrape_runner.lock"
exec 9>"$LOCK_FILE"

current_pid="$$"
pattern='scripts/run_scrape_pipeline.py|scripts/crawl_whisky_sites.py'

stop_existing_crawlers() {
  local existing_pids remaining pid cmd
  existing_pids="$(pgrep -f "$pattern" || true)"
  if [[ -z "$existing_pids" ]]; then
    return
  fi

  echo "[scrape] Stopping existing crawler process(es):"
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    [[ "$pid" == "$current_pid" ]] && continue
    cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    echo "[scrape]   PID $pid :: $cmd"
    kill "$pid" 2>/dev/null || true
  done <<< "$existing_pids"

  for _ in {1..20}; do
    remaining="$(pgrep -f "$pattern" || true)"
    [[ -z "$remaining" ]] && break
    sleep 0.5
  done

  remaining="$(pgrep -f "$pattern" || true)"
  if [[ -n "$remaining" ]]; then
    echo "[scrape] Force-stopping stuck crawler process(es):"
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      [[ "$pid" == "$current_pid" ]] && continue
      cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
      echo "[scrape]   PID $pid :: $cmd"
      kill -9 "$pid" 2>/dev/null || true
    done <<< "$remaining"
  fi
}

if ! flock -n 9; then
  echo "[scrape] Lock is held; clearing running/jammed crawler instances first..."
  stop_existing_crawlers
  if ! flock -w 15 9; then
    echo "[scrape] Could not acquire launcher lock after cleanup. Try again in a few seconds."
    exit 1
  fi
fi

stop_existing_crawlers

echo "[scrape] Starting crawler with exclusive startup guard."

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

# The lock is only needed during startup/cleanup. Release before long-running pipeline.
flock -u 9
exec 9>&-

exec "$PYTHON_BIN" scripts/run_scrape_pipeline.py "$@"
