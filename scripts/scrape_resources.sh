#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRAPE_TIMEOUT_SECONDS="${SCRAPE_TIMEOUT_SECONDS:-120}"
SCRAPE_MAX_PAGES_PER_SITE="${SCRAPE_MAX_PAGES_PER_SITE:-20}"
SCRAPE_PARALLEL_PAGE_LOADS="${SCRAPE_PARALLEL_PAGE_LOADS:-4}"
SCRAPE_SITE_NAME_FILTER="${SCRAPE_SITE_NAME_FILTER:-}"
SCRAPE_RETRY_FAILED="${SCRAPE_RETRY_FAILED:-0}"
SCRAPE_DRY_RUN="${SCRAPE_DRY_RUN:-0}"
SCRAPE_REPORT_PATH="${SCRAPE_REPORT_PATH:-data/resource_scrape_post_run_report.md}"

export PYTHON_BIN
export SCRAPE_TIMEOUT_SECONDS
export SCRAPE_MAX_PAGES_PER_SITE
export SCRAPE_PARALLEL_PAGE_LOADS
export SCRAPE_SITE_NAME_FILTER
export SCRAPE_RETRY_FAILED
export SCRAPE_DRY_RUN
export SCRAPE_REPORT_PATH

"$PYTHON_BIN" - <<'PY'
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def normalize_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def status_is_unfinished(status: str | None) -> bool:
    return status is None or not str(status).strip()


def status_is_failed(status: str | None) -> bool:
    return bool(status) and "failed=" in str(status) and "failed=0" not in str(status)


root_dir = Path.cwd()
python_bin = os.environ["PYTHON_BIN"]
timeout_seconds = int(os.environ["SCRAPE_TIMEOUT_SECONDS"])
max_pages_per_site = int(os.environ["SCRAPE_MAX_PAGES_PER_SITE"])
parallel_page_loads = int(os.environ["SCRAPE_PARALLEL_PAGE_LOADS"])
site_name_filter = os.environ["SCRAPE_SITE_NAME_FILTER"].strip().lower()
retry_failed = os.environ["SCRAPE_RETRY_FAILED"] == "1"
dry_run = os.environ["SCRAPE_DRY_RUN"] == "1"
report_path = root_dir / os.environ["SCRAPE_REPORT_PATH"]

resources_db = sqlite3.connect(root_dir / "data/resources.db")
resources_db.row_factory = sqlite3.Row
state_db = sqlite3.connect(root_dir / "data/site_crawl_state.db")
state_db.row_factory = sqlite3.Row

resources = resources_db.execute(
    "SELECT name, url, category FROM resources WHERE url LIKE 'http%' ORDER BY category, name"
).fetchall()

state_rows = state_db.execute(
    "SELECT root_url, last_status FROM sites WHERE site_type='resource'"
).fetchall()
state_by_url = {normalize_url(row["root_url"]): row["last_status"] for row in state_rows}

queue = []
for row in resources:
    name = str(row["name"])
    url = normalize_url(row["url"])
    if site_name_filter and site_name_filter not in name.lower():
        continue
    status = state_by_url.get(url)
    if status_is_unfinished(status) or (retry_failed and status_is_failed(status)):
        queue.append((name, url, row["category"], status))

print(f"Resource targets total: {len(resources)}")
print(f"Queued this run: {len(queue)}")
print(f"Retry failed enabled: {retry_failed}")
print(f"Per-site timeout: {timeout_seconds}s")
print(f"Max pages per site: {max_pages_per_site}")

if not queue:
    print("Nothing to do.")
    sys.exit(0)

if dry_run:
    for index, (name, _url, _category, status) in enumerate(queue, 1):
        print(f"DRY RUN [{index}/{len(queue)}] {name} | prior_status={status}")
    print("Dry run complete.")
    sys.exit(0)

successes = []
failures = []
timeouts = []
unknown = []

for index, (name, url, _category, prior_status) in enumerate(queue, 1):
    print(f"\n[{index}/{len(queue)}] {name}")
    if prior_status:
        print(f"Prior status: {prior_status}")
    sys.stdout.flush()

    cmd = [
        python_bin,
        "scripts/crawl_whisky_sites.py",
        "--site-types",
        "resource",
        "--filter-name",
        name,
        "--max-sites",
        "1",
        "--max-pages-per-site",
        str(max_pages_per_site),
        "--parallel-page-loads",
        str(parallel_page_loads),
        "--quiet-crawl",
        "--headless",
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        timeouts.append(name)
        print(f"TIMEOUT after {timeout_seconds}s")
        sys.stdout.flush()
        continue

    output_lines = [line for line in proc.stdout.splitlines() if line.strip()]
    tail = " | ".join(output_lines[-4:]) if output_lines else "(no output)"

    latest_status_row = state_db.execute(
        "SELECT last_status FROM sites WHERE site_type='resource' AND RTRIM(root_url, '/') = ? ORDER BY id DESC LIMIT 1",
        (url,),
    ).fetchone()
    latest_status = latest_status_row["last_status"] if latest_status_row else None

    print(f"EXIT {proc.returncode}: {tail}")
    print(f"Recorded status: {latest_status}")

    if latest_status and "failed=0" in str(latest_status):
        successes.append(name)
    elif latest_status and "failed=" in str(latest_status):
        failures.append(name)
    else:
        unknown.append(name)

    sys.stdout.flush()

updated_state_rows = state_db.execute(
    "SELECT root_url, last_status FROM sites WHERE site_type='resource'"
).fetchall()
updated_state_by_url = {normalize_url(row["root_url"]): row["last_status"] for row in updated_state_rows}

remaining = []
for row in resources:
    name = str(row["name"])
    url = normalize_url(row["url"])
    if site_name_filter and site_name_filter not in name.lower():
        continue
    status = updated_state_by_url.get(url)
    if status_is_unfinished(status) or (retry_failed and status_is_failed(status)):
        remaining.append(name)

print("\nSummary")
print(f"Attempted: {len(queue)}")
print(f"Succeeded: {len(successes)}")
print(f"Failed: {len(failures)}")
print(f"Timed out: {len(timeouts)}")
print(f"Unknown: {len(unknown)}")
print(f"Remaining queued after run: {len(remaining)}")

if failures:
    print("Failed sites:")
    for name in failures:
        print(f"- {name}")

if timeouts:
    print("Timed out sites:")
    for name in timeouts:
        print(f"- {name}")

if unknown:
    print("Unknown status sites:")
    for name in unknown:
        print(f"- {name}")

report_lines = [
    "# Resource Scrape Post-Run Report",
    "",
    f"Generated: {datetime.now(timezone.utc).isoformat()}",
    f"Attempted: {len(queue)}",
    f"Succeeded: {len(successes)}",
    f"Failed: {len(failures)}",
    f"Timed out: {len(timeouts)}",
    f"Unknown: {len(unknown)}",
    f"Remaining queued after run: {len(remaining)}",
    f"Retry failed enabled: {retry_failed}",
    f"Per-site timeout: {timeout_seconds}s",
    f"Max pages per site: {max_pages_per_site}",
]

if failures:
    report_lines.extend(["", "## Failed Sites", ""])
    report_lines.extend(f"- {name}" for name in failures)

if timeouts:
    report_lines.extend(["", "## Timed Out Sites", ""])
    report_lines.extend(f"- {name}" for name in timeouts)

if unknown:
    report_lines.extend(["", "## Unknown Status Sites", ""])
    report_lines.extend(f"- {name}" for name in unknown)

if remaining:
    report_lines.extend(["", "## Remaining Queue", ""])
    report_lines.extend(f"- {name}" for name in remaining)

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
print(f"Post-run report: {report_path}")
PY