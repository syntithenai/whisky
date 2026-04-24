#!/usr/bin/env bash
set -euo pipefail

# Targeted resource-only scrape matrix for high-value lesson/quiz signal.
# Usage:
#   scripts/run_resource_targeted_batches.sh            # run all batches
#   scripts/run_resource_targeted_batches.sh compliance # run one batch
#   scripts/run_resource_targeted_batches.sh --dry-run operations

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DRY_RUN=0
BATCH="${1:-all}"
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  BATCH="${2:-all}"
fi

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

run_site() {
  local label="$1"
  local filter="$2"
  local pages="$3"
  local extract_timeout="$4"
  local site_timeout="$5"
  local workers="$6"
  local page_loads="$7"
  local undetected="$8"

  echo
  echo "=== ${label} :: ${filter} ==="
  local dry="0"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    dry="1"
  fi

  SCRAPE_DRY_RUN="$dry" \
  SCRAPE_SITE_NAME_FILTER="$filter" \
  SCRAPE_MAX_PAGES_PER_SITE="$pages" \
  SCRAPE_LMSTUDIO_EXTRACT_TIMEOUT="$extract_timeout" \
  SCRAPE_TIMEOUT_SECONDS="$site_timeout" \
  SCRAPE_SITE_WORKERS="$workers" \
  SCRAPE_PARALLEL_PAGE_LOADS="$page_loads" \
  SCRAPE_MAX_RETRY_ROUNDS=1 \
  SCRAPE_DOMAIN_COOLDOWN_SECONDS=180 \
  SCRAPE_SKIP_PODCASTS=1 \
  SCRAPE_UNDETECTED_CHROME="$undetected" \
  SCRAPE_QUIET_CRAWL=1 \
  PYTHON_BIN="$PYTHON_BIN" \
  scripts/scrape_resources.sh
}

run_compliance_batch() {
  # Regulatory/compliance signal for phases 2/6/8.
  run_site "compliance" "TTB Distilled Spirits" 24 900 1200 1 1 1
  run_site "compliance" "Distilled Spirits Council" 24 900 1200 1 1 1
  run_site "compliance" "UK HMRC - Excise Notice 39" 20 900 1200 1 1 0
  run_site "compliance" "Australian Taxation Office - Excise for Alcohol" 20 900 1200 1 1 0
  run_site "compliance" "Australian Border Force - Spirits Excise" 20 900 1200 1 1 0
  run_site "compliance" "Kentucky Distillers' Association" 20 900 1200 1 1 1
}

run_operations_batch() {
  # Operations/equipment/process signal for phases 3/6/11.
  run_site "operations" "StillDragon Learn" 30 900 1200 1 2 0
  run_site "operations" "RahrBSG Spirits & Distilling" 30 900 1200 1 2 0
  run_site "operations" "Gusmer Enterprises Beverage Alcohol" 25 900 1200 1 2 0
  run_site "operations" "White Labs Beverage Alcohol" 25 900 1200 1 2 0
  run_site "operations" "James B. Beam Institute for Kentucky Spirits" 24 900 1200 1 2 0
  run_site "operations" "Artisan Spirit Magazine" 20 900 1200 1 2 1
}

run_chemistry_batch() {
  # Chemistry/biochemistry and mechanism signal for phases 9/10.
  run_site "chemistry" "Whisky Science" 30 900 1200 1 2 0
  run_site "chemistry" "Australian Wine Research Institute (AWRI)" 24 900 1200 1 2 0
  run_site "chemistry" "Whisky Magazine" 24 900 1200 1 2 0
  run_site "chemistry" "ScotchWhisky.com" 24 900 1200 1 2 0
  run_site "chemistry" "Alcohol Professor" 20 900 1200 1 2 1
}

run_context_batch() {
  # Contextual narrative sources for phases 2/4/5/7.
  run_site "context" "Bourbon Pursuit" 20 900 1200 1 2 0
  run_site "context" "Whisky Waffle" 20 900 1200 1 2 0
}

case "$BATCH" in
  all)
    run_compliance_batch
    run_operations_batch
    run_chemistry_batch
    run_context_batch
    ;;
  compliance)
    run_compliance_batch
    ;;
  operations)
    run_operations_batch
    ;;
  chemistry)
    run_chemistry_batch
    ;;
  context)
    run_context_batch
    ;;
  *)
    echo "Unknown batch: $BATCH"
    echo "Valid: all | compliance | operations | chemistry | context"
    exit 1
    ;;
esac

echo
echo "Targeted resource batch run complete (${BATCH})."
