#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

patterns=(
  'scripts/run_scrape_pipeline\.py'
  'scripts/crawl_whisky_sites\.py'
  'scripts/scrape\.sh'
  'scripts/scrape_distilleries\.sh'
  'scripts/scrape_resources\.sh'
)

declare -A seen_pids=()

collect_matching_pids() {
  local pattern pid
  for pattern in "${patterns[@]}"; do
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      [[ "$pid" == "$$" ]] && continue
      [[ "$pid" == "$BASHPID" ]] && continue
      [[ "$pid" == "$PPID" ]] && continue
      seen_pids["$pid"]=1
    done < <(pgrep -f "$pattern" || true)
  done
}

print_matching_processes() {
  local pid cmd
  for pid in "${!seen_pids[@]}"; do
    cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    [[ -z "$cmd" ]] && continue
    echo "[stop_crawl]   PID $pid :: $cmd"
  done
}

stop_processes() {
  local signal="$1"
  local pid
  for pid in "${!seen_pids[@]}"; do
    kill "$signal" "$pid" 2>/dev/null || true
  done
}

clear_finished_pids() {
  local pid
  for pid in "${!seen_pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      unset 'seen_pids[$pid]'
    fi
  done
}

collect_matching_pids

if [[ "${#seen_pids[@]}" -eq 0 ]]; then
  echo "[stop_crawl] No crawl-related processes are running."
  exit 0
fi

echo "[stop_crawl] Stopping crawl-related process(es):"
print_matching_processes
stop_processes TERM

for _ in {1..20}; do
  clear_finished_pids
  [[ "${#seen_pids[@]}" -eq 0 ]] && break
  sleep 0.5
done

clear_finished_pids

if [[ "${#seen_pids[@]}" -gt 0 ]]; then
  echo "[stop_crawl] Force-stopping remaining process(es):"
  print_matching_processes
  stop_processes KILL
fi

echo "[stop_crawl] Crawl stop request complete."