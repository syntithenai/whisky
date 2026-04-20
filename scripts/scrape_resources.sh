#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRAPE_TIMEOUT_SECONDS="${SCRAPE_TIMEOUT_SECONDS:-360}"
SCRAPE_LMSTUDIO_EXTRACT_TIMEOUT="${SCRAPE_LMSTUDIO_EXTRACT_TIMEOUT:-900}"
SCRAPE_PAGE_TIMEOUT_SECONDS="${SCRAPE_PAGE_TIMEOUT_SECONDS:-45}"
SCRAPE_DIRECT_FETCH_TIMEOUT_SECONDS="${SCRAPE_DIRECT_FETCH_TIMEOUT_SECONDS:-30}"
SCRAPE_MAX_PAGES_PER_SITE="${SCRAPE_MAX_PAGES_PER_SITE:-20}"
SCRAPE_PARALLEL_PAGE_LOADS="${SCRAPE_PARALLEL_PAGE_LOADS:-4}"
SCRAPE_SITE_WORKERS="${SCRAPE_SITE_WORKERS:-4}"
SCRAPE_MAX_RETRY_ROUNDS="${SCRAPE_MAX_RETRY_ROUNDS:-2}"
SCRAPE_DOMAIN_COOLDOWN_SECONDS="${SCRAPE_DOMAIN_COOLDOWN_SECONDS:-900}"
SCRAPE_LMSTUDIO_SCREEN_MODEL="${SCRAPE_LMSTUDIO_SCREEN_MODEL:-ibm/granite-4-h-tiny}"
SCRAPE_LMSTUDIO_MODEL="${SCRAPE_LMSTUDIO_MODEL:-openai/gpt-oss-20b}"
SCRAPE_QUIET_CRAWL="${SCRAPE_QUIET_CRAWL:-0}"
SCRAPE_SKIP_PODCASTS="${SCRAPE_SKIP_PODCASTS:-0}"
SCRAPE_WHISPER_SERVICE_URL="${SCRAPE_WHISPER_SERVICE_URL:-http://127.0.0.1:10010}"
SCRAPE_CDP_URL="${SCRAPE_CDP_URL:-http://127.0.0.1:9222}"
SCRAPE_UNDETECTED_CHROME="${SCRAPE_UNDETECTED_CHROME:-0}"
SCRAPE_SITE_NAME_FILTER="${SCRAPE_SITE_NAME_FILTER:-}"
SCRAPE_RETRY_FAILED="${SCRAPE_RETRY_FAILED:-1}"
SCRAPE_FORCE_RESCRAPE="${SCRAPE_FORCE_RESCRAPE:-0}"
SCRAPE_DRY_RUN="${SCRAPE_DRY_RUN:-0}"
SCRAPE_REPORT_PATH="${SCRAPE_REPORT_PATH:-data/resource_scrape_post_run_report.md}"
SCRAPE_AUTO_EXPAND_RESOURCES="${SCRAPE_AUTO_EXPAND_RESOURCES:-1}"
SCRAPE_AUTO_EXPAND_BATCH_SIZE="${SCRAPE_AUTO_EXPAND_BATCH_SIZE:-8}"
SCRAPE_AUTO_EXPAND_MAX_ROUNDS="${SCRAPE_AUTO_EXPAND_MAX_ROUNDS:-1}"
SCRAPE_ZERO_OK_STREAK_THRESHOLD="${SCRAPE_ZERO_OK_STREAK_THRESHOLD:-2}"
SCRAPE_ZERO_OK_SUPPRESS_HOURS="${SCRAPE_ZERO_OK_SUPPRESS_HOURS:-72}"
SCRAPE_POLICY_STATE_PATH="${SCRAPE_POLICY_STATE_PATH:-data/resource_scrape_policy_state.json}"
SCRAPE_RESOURCE_SEED_PATH="${SCRAPE_RESOURCE_SEED_PATH:-data/resource_sites_seed.json}"
SCRAPE_RESOURCE_CANDIDATES_PATH="${SCRAPE_RESOURCE_CANDIDATES_PATH:-data/resource_sites_seed_candidates.json}"

export PYTHON_BIN
export SCRAPE_TIMEOUT_SECONDS
export SCRAPE_LMSTUDIO_EXTRACT_TIMEOUT
export SCRAPE_PAGE_TIMEOUT_SECONDS
export SCRAPE_DIRECT_FETCH_TIMEOUT_SECONDS
export SCRAPE_MAX_PAGES_PER_SITE
export SCRAPE_PARALLEL_PAGE_LOADS
export SCRAPE_SITE_WORKERS
export SCRAPE_MAX_RETRY_ROUNDS
export SCRAPE_DOMAIN_COOLDOWN_SECONDS
export SCRAPE_LMSTUDIO_SCREEN_MODEL
export SCRAPE_LMSTUDIO_MODEL
export SCRAPE_QUIET_CRAWL
export SCRAPE_SKIP_PODCASTS
export SCRAPE_WHISPER_SERVICE_URL
export SCRAPE_CDP_URL
export SCRAPE_UNDETECTED_CHROME
export SCRAPE_SITE_NAME_FILTER
export SCRAPE_RETRY_FAILED
export SCRAPE_FORCE_RESCRAPE
export SCRAPE_DRY_RUN
export SCRAPE_REPORT_PATH
export SCRAPE_AUTO_EXPAND_RESOURCES
export SCRAPE_AUTO_EXPAND_BATCH_SIZE
export SCRAPE_AUTO_EXPAND_MAX_ROUNDS
export SCRAPE_ZERO_OK_STREAK_THRESHOLD
export SCRAPE_ZERO_OK_SUPPRESS_HOURS
export SCRAPE_POLICY_STATE_PATH
export SCRAPE_RESOURCE_SEED_PATH
export SCRAPE_RESOURCE_CANDIDATES_PATH

# Kill any existing crawler or scrape processes before starting this run.
if pids=$(pgrep -f 'scripts/crawl_whisky_sites\.py' 2>/dev/null); then
    echo "[startup] Stopping existing crawler(s): $pids"
    kill -- $pids 2>/dev/null || true
    sleep 2
    # Force-kill anything that didn't stop cleanly
    if live=$(pgrep -f 'scripts/crawl_whisky_sites\.py' 2>/dev/null); then
        kill -9 -- $live 2>/dev/null || true
    fi
fi
if pids=$(pgrep -f 'scripts/scrape_resources\.sh' 2>/dev/null | grep -v "^$$\$" | grep -v "^$BASHPID\$"); then
    [ -n "$pids" ] && { echo "[startup] Stopping other scrape_resources.sh: $pids"; kill -- $pids 2>/dev/null || true; }
fi

"$PYTHON_BIN" - <<'PY'
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def normalize_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def status_is_unfinished(status: str | None) -> bool:
    return status is None or not str(status).strip()


def status_is_failed(status: str | None) -> bool:
    return bool(status) and "failed=" in str(status) and "failed=0" not in str(status)


def status_has_zero_ok_pages(status: str | None) -> bool:
    if not status:
        return False
    text = str(status)
    marker = "ok pages="
    if marker not in text:
        return False
    try:
        ok_pages = int(text.split(marker, 1)[1].split()[0])
    except Exception:
        return False
    return ok_pages == 0


root_dir = Path.cwd()
python_bin = os.environ["PYTHON_BIN"]
timeout_seconds = int(os.environ["SCRAPE_TIMEOUT_SECONDS"])
lmstudio_extract_timeout = int(os.environ["SCRAPE_LMSTUDIO_EXTRACT_TIMEOUT"])
page_timeout_seconds = int(os.environ["SCRAPE_PAGE_TIMEOUT_SECONDS"])
direct_fetch_timeout_seconds = int(os.environ["SCRAPE_DIRECT_FETCH_TIMEOUT_SECONDS"])
max_pages_per_site = int(os.environ["SCRAPE_MAX_PAGES_PER_SITE"])
parallel_page_loads = int(os.environ["SCRAPE_PARALLEL_PAGE_LOADS"])
site_workers = max(1, int(os.environ["SCRAPE_SITE_WORKERS"]))
max_retry_rounds = max(0, int(os.environ["SCRAPE_MAX_RETRY_ROUNDS"]))
domain_cooldown_seconds = max(0, int(os.environ["SCRAPE_DOMAIN_COOLDOWN_SECONDS"]))
lmstudio_screen_model = os.environ["SCRAPE_LMSTUDIO_SCREEN_MODEL"].strip() or "ibm/granite-4-h-tiny"
lmstudio_model = os.environ["SCRAPE_LMSTUDIO_MODEL"].strip() or "openai/gpt-oss-20b"
quiet_crawl = os.environ["SCRAPE_QUIET_CRAWL"] == "1"
skip_podcasts = os.environ["SCRAPE_SKIP_PODCASTS"] == "1"
whisper_service_url = os.environ["SCRAPE_WHISPER_SERVICE_URL"].strip()
cdp_url = os.environ["SCRAPE_CDP_URL"].strip()
undetected_chrome = os.environ["SCRAPE_UNDETECTED_CHROME"] == "1"
site_name_filter = os.environ["SCRAPE_SITE_NAME_FILTER"].strip().lower()
retry_failed = os.environ["SCRAPE_RETRY_FAILED"] == "1"
force_rescrape = os.environ["SCRAPE_FORCE_RESCRAPE"] == "1"
dry_run = os.environ["SCRAPE_DRY_RUN"] == "1"
report_path = root_dir / os.environ["SCRAPE_REPORT_PATH"]
auto_expand_resources = os.environ["SCRAPE_AUTO_EXPAND_RESOURCES"] == "1"
auto_expand_batch_size = max(0, int(os.environ["SCRAPE_AUTO_EXPAND_BATCH_SIZE"]))
auto_expand_max_rounds = max(0, int(os.environ["SCRAPE_AUTO_EXPAND_MAX_ROUNDS"]))
zero_ok_streak_threshold = max(1, int(os.environ["SCRAPE_ZERO_OK_STREAK_THRESHOLD"]))
zero_ok_suppress_hours = max(1, int(os.environ["SCRAPE_ZERO_OK_SUPPRESS_HOURS"]))
policy_state_path = root_dir / os.environ["SCRAPE_POLICY_STATE_PATH"]
seed_path = root_dir / os.environ["SCRAPE_RESOURCE_SEED_PATH"]
candidate_path = root_dir / os.environ["SCRAPE_RESOURCE_CANDIDATES_PATH"]
resources_db_path = root_dir / "data/resources.db"
state_db_path = root_dir / "data/site_crawl_state.db"

def open_resources_db() -> sqlite3.Connection:
    conn = sqlite3.connect(resources_db_path)
    conn.row_factory = sqlite3.Row
    return conn


resources_db = open_resources_db()
state_db = sqlite3.connect(state_db_path)
state_db.row_factory = sqlite3.Row

min_site_timeout = lmstudio_extract_timeout + 120
if timeout_seconds < min_site_timeout:
    print(
        f"[config] SCRAPE_TIMEOUT_SECONDS={timeout_seconds}s is below "
        f"SCRAPE_LMSTUDIO_EXTRACT_TIMEOUT+120 ({min_site_timeout}s); using {min_site_timeout}s"
    )
    timeout_seconds = min_site_timeout


def load_resources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT name, url, category FROM resources WHERE url LIKE 'http%' ORDER BY category, name"
    ).fetchall()


def load_state_by_url() -> dict[str, str | None]:
    state_rows = state_db.execute(
        "SELECT root_url, last_status FROM sites WHERE site_type='resource'"
    ).fetchall()
    return {normalize_url(row["root_url"]): row["last_status"] for row in state_rows}


def load_policy_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for raw_url, raw_info in payload.items():
        url = normalize_url(str(raw_url))
        if not url or not isinstance(raw_info, dict):
            continue
        streak = raw_info.get("zero_ok_streak", 0)
        suppress_until = raw_info.get("suppress_until", "")
        out[url] = {
            "zero_ok_streak": int(streak) if isinstance(streak, (int, float, str)) and str(streak).strip() else 0,
            "suppress_until": str(suppress_until or ""),
        }
    return out


def save_policy_state(path: Path, payload: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def suppression_active(info: dict[str, object] | None, now_ts: float) -> bool:
    if not info:
        return False
    suppress_until_raw = str(info.get("suppress_until") or "").strip()
    if not suppress_until_raw:
        return False
    try:
        until = datetime.fromisoformat(suppress_until_raw)
    except Exception:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until.timestamp() > now_ts


def should_queue_site(
    status: str | None,
    retry_failed_flag: bool,
    force_rescrape_flag: bool,
    policy_info: dict[str, object] | None,
    now_ts: float,
) -> bool:
    if force_rescrape_flag:
        return True
    if status_is_unfinished(status):
        return True
    if retry_failed_flag and status_is_failed(status):
        return True
    if status_has_zero_ok_pages(status):
        return not suppression_active(policy_info, now_ts)
    return False


def build_queue(
    resources: list[sqlite3.Row],
    state_by_url: dict[str, str | None],
    policy_state_by_url: dict[str, dict[str, object]],
) -> list[tuple[str, str, str, str | None]]:
    queue: list[tuple[str, str, str, str | None]] = []
    now_ts = time.time()
    for row in resources:
        name = str(row["name"])
        url = normalize_url(row["url"])
        if site_name_filter and site_name_filter not in name.lower():
            continue
        status = state_by_url.get(url)
        policy_info = policy_state_by_url.get(url)
        if should_queue_site(status, retry_failed, force_rescrape, policy_info, now_ts):
            queue.append((name, url, row["category"], status))
    return queue


def count_zero_ok_suppressed(
    resources: list[sqlite3.Row],
    state_by_url: dict[str, str | None],
    policy_state_by_url: dict[str, dict[str, object]],
) -> int:
    if force_rescrape:
        return 0
    now_ts = time.time()
    suppressed = 0
    for row in resources:
        name = str(row["name"])
        if site_name_filter and site_name_filter not in name.lower():
            continue
        url = normalize_url(row["url"])
        status = state_by_url.get(url)
        if status_has_zero_ok_pages(status) and suppression_active(policy_state_by_url.get(url), now_ts):
            suppressed += 1
    return suppressed


def log_queue_snapshot(
    resources: list[sqlite3.Row],
    queue: list[tuple[str, str, str, str | None]],
    cycle: int,
    suppressed_zero_ok: int,
) -> None:
    print(f"\n=== Resource scrape cycle {cycle} ===")
    print(f"Resource targets total: {len(resources)}")
    print(f"Queued this cycle: {len(queue)}")
    print(f"Retry failed enabled: {retry_failed}")
    print(f"Per-site timeout: {timeout_seconds}s")
    print(f"LM Studio extract timeout: {lmstudio_extract_timeout}s")
    print(f"Page load timeout: {page_timeout_seconds}s")
    print(f"Direct fetch timeout: {direct_fetch_timeout_seconds}s")
    print(f"Max pages per site: {max_pages_per_site}")
    print(f"LM Studio screen model: {lmstudio_screen_model}")
    print(f"LM Studio model: {lmstudio_model}")
    print(f"Quiet crawl: {quiet_crawl}")
    print(f"Skip podcasts: {skip_podcasts}")
    print(f"Site workers: {site_workers}")
    print(f"Retry rounds: {max_retry_rounds}")
    print(f"Domain cooldown: {domain_cooldown_seconds}s")
    print(f"Auto-expand resources: {auto_expand_resources}")
    print(f"Auto-expand batch size: {auto_expand_batch_size}")
    print(f"Auto-expand max rounds: {auto_expand_max_rounds}")
    print(f"Zero-ok suppression threshold: {zero_ok_streak_threshold}")
    print(f"Zero-ok suppression hours: {zero_ok_suppress_hours}")
    print(f"Zero-ok currently suppressed: {suppressed_zero_ok}")


def promote_resource_candidates() -> dict[str, object]:
    cmd = [
        python_bin,
        "scripts/promote_resource_seed_candidates.py",
        "--seed",
        str(seed_path),
        "--candidates",
        str(candidate_path),
        "--count",
        str(auto_expand_batch_size),
        "--json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(
        cmd,
        cwd=root_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unable to parse seed promotion output: {proc.stdout!r}") from exc
    if not dry_run and int(result.get("added", 0)) > 0:
        rebuild_cmd = [
            python_bin,
            "scripts/build_resources_database.py",
            "--seed",
            str(seed_path),
            "--db",
            str(resources_db_path),
        ]
        subprocess.run(rebuild_cmd, cwd=root_dir, check=True)
    return result


def maybe_expand_resources(expansion_rounds_used: int, reason: str) -> dict[str, object] | None:
    if dry_run:
        return None
    if site_name_filter:
        return None
    if not auto_expand_resources or auto_expand_batch_size <= 0:
        return None
    if expansion_rounds_used >= auto_expand_max_rounds:
        return None
    if not candidate_path.exists():
        print(f"[auto-expand] candidate file missing: {candidate_path}")
        return None
    print(f"[auto-expand] {reason}; promoting up to {auto_expand_batch_size} new resource seed(s)")
    result = promote_resource_candidates()
    added = int(result.get("added", 0))
    if added <= 0:
        print("[auto-expand] no unused candidates available")
        return None
    added_names = result.get("added_names", [])
    print(f"[auto-expand] promoted {added} resource seed(s):")
    for name in added_names:
        print(f"- {name}")
    result["trigger_reason"] = reason
    return result


if dry_run:
    resources = load_resources(resources_db)
    state_by_url = load_state_by_url()
    policy_state_by_url = load_policy_state(policy_state_path)
    queue = build_queue(resources, state_by_url, policy_state_by_url)
    suppressed_zero_ok = count_zero_ok_suppressed(resources, state_by_url, policy_state_by_url)
    log_queue_snapshot(resources, queue, 1, suppressed_zero_ok)
    if not queue:
        print("Nothing to do.")
        sys.exit(0)
    for index, (name, _url, _category, status) in enumerate(queue, 1):
        print(f"DRY RUN [{index}/{len(queue)}] {name} | prior_status={status}")
    print("Dry run complete.")
    sys.exit(0)

def get_domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def model_aliases(model_name: str) -> set[str]:
    cleaned = str(model_name or "").strip()
    if not cleaned:
        return set()
    aliases = {cleaned}
    if "/" in cleaned:
        aliases.add(cleaned.split("/")[-1])
    return aliases


def ensure_lmstudio_models_available(required_models: list[str]) -> None:
    req = Request("http://127.0.0.1:1234/v1/models", method="GET")
    with urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        raise RuntimeError("LM Studio /models response missing data array")
    available_ids = {
        str(item.get("id", "")).strip()
        for item in raw_models
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    available_aliases: set[str] = set()
    for model_id in available_ids:
        available_aliases.update(model_aliases(model_id))
    missing = [model for model in required_models if not (model_aliases(model) & available_aliases)]
    if missing:
        raise RuntimeError(
            "Required LM Studio model(s) not available: "
            f"{', '.join(missing)}. Available: {', '.join(sorted(available_ids)[:20]) or 'none'}"
        )


ensure_lmstudio_models_available([lmstudio_screen_model, lmstudio_model])


def build_command(site_name: str) -> list[str]:
    cmd = [
        python_bin,
        "scripts/crawl_whisky_sites.py",
        "--site-types",
        "resource",
        "--filter-name",
        site_name,
        "--max-sites",
        "1",
        "--max-pages-per-site",
        str(max_pages_per_site),
        "--parallel-page-loads",
        str(parallel_page_loads),
        "--page-timeout",
        str(page_timeout_seconds),
        "--direct-fetch-timeout",
        str(direct_fetch_timeout_seconds),
        "--lmstudio-extract-timeout",
        str(lmstudio_extract_timeout),
        "--lmstudio-screen-model",
        lmstudio_screen_model,
        "--lmstudio-model",
        lmstudio_model,
        "--headless",
    ]
    if cdp_url:
        cmd.extend(["--cdp-url", cdp_url])
    if undetected_chrome:
        cmd.append("--undetected-chrome")
    if skip_podcasts:
        cmd.extend(["--max-audio-files-per-page", "0"])
    elif whisper_service_url:
        cmd.extend(["--whisper-service-url", whisper_service_url])
    if force_rescrape:
        cmd.append("--force-rescrape")
    cmd.append("--no-distillery-sync")
    if quiet_crawl:
        cmd.append("--quiet-crawl")
    return cmd


def run_site(entry: dict[str, str]) -> dict[str, object]:
    cmd = build_command(entry["name"])
    try:
        proc = subprocess.run(
            cmd,
            cwd=root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
        )
        output = proc.stdout or ""
        return {
            "entry": entry,
            "timed_out": False,
            "returncode": proc.returncode,
            "output": output,
        }
    except subprocess.TimeoutExpired as exc:
        output = ""
        if exc.stdout:
            output = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
        return {
            "entry": entry,
            "timed_out": True,
            "returncode": None,
            "output": output,
        }


def output_tail(output: str) -> str:
    output_lines = [line for line in output.splitlines() if line.strip()]
    return " | ".join(output_lines[-4:]) if output_lines else "(no output)"


def read_latest_status(url: str) -> str | None:
    row = state_db.execute(
        "SELECT last_status FROM sites WHERE site_type='resource' AND RTRIM(root_url, '/') = ? ORDER BY id DESC LIMIT 1",
        (normalize_url(url),),
    ).fetchone()
    return str(row["last_status"]) if row and row["last_status"] is not None else None


def classify_result(timed_out: bool, output: str, latest_status: str | None) -> str:
    haystack = (str(latest_status or "") + "\n" + output).lower()
    if timed_out:
        return "timed_out"
    if any(token in haystack for token in [" 403", " 429", "captcha", "challenge", "access denied", "cloudflare"]):
        return "block_suspected"
    if latest_status and "failed=0" in latest_status:
        return "success"
    if latest_status and "failed=" in latest_status and "failed=0" not in latest_status:
        return "failed"
    return "unknown"


total_attempts = 0
successes: set[str] = set()
failures: set[str] = set()
timeouts: set[str] = set()
unknown: set[str] = set()
blocked: set[str] = set()
domain_next_allowed: dict[str, float] = {}

attempted_names: list[str] = []
expansion_events: list[dict[str, object]] = []
expansion_rounds_used = 0
last_resources: list[sqlite3.Row] = []
last_remaining: list[str] = []
last_suppressed_zero_ok = 0
cycle = 0
policy_state_by_url = load_policy_state(policy_state_path)

while True:
    resources = load_resources(resources_db)
    state_by_url = load_state_by_url()
    queue = build_queue(resources, state_by_url, policy_state_by_url)
    suppressed_zero_ok = count_zero_ok_suppressed(resources, state_by_url, policy_state_by_url)
    queued_urls = {normalize_url(url) for _name, url, _category, _status in queue}
    cycle += 1
    log_queue_snapshot(resources, queue, cycle, suppressed_zero_ok)

    if not queue:
        expansion = maybe_expand_resources(expansion_rounds_used, "queue exhausted")
        if expansion is None:
            last_resources = resources
            last_remaining = []
            if total_attempts == 0:
                print("Nothing to do.")
            break
        expansion_events.append(expansion)
        expansion_rounds_used += 1
        resources_db.close()
        resources_db = open_resources_db()
        continue

    entries = [
        {
            "name": str(name),
            "url": str(url),
            "category": str(category),
            "prior_status": str(prior_status) if prior_status is not None else "",
        }
        for name, url, category, prior_status in queue
    ]

    for retry_round in range(0, max_retry_rounds + 1):
        if not entries:
            break

        round_label = "primary" if retry_round == 0 else f"retry-{retry_round}"
        print(f"\n--- Round {retry_round}/{max_retry_rounds} ({round_label}) ---")

        pending = list(entries)
        entries = []
        retry_candidates: list[dict[str, str]] = []

        while pending:
            now = time.time()
            ready: list[dict[str, str]] = []
            deferred: list[dict[str, str]] = []
            for entry in pending:
                wait_until = domain_next_allowed.get(get_domain(entry["url"]), 0.0)
                if wait_until > now:
                    deferred.append(entry)
                else:
                    ready.append(entry)

            if not ready:
                next_ready = min(domain_next_allowed.get(get_domain(item["url"]), now) for item in deferred)
                sleep_for = max(1, int(next_ready - now))
                print(f"[cooldown] waiting {sleep_for}s before retrying cooled domains")
                sys.stdout.flush()
                time.sleep(sleep_for)
                pending = deferred
                continue

            pending = deferred
            print(f"[dispatch] {len(ready)} site(s) with {site_workers} worker(s)")
            sys.stdout.flush()

            with ThreadPoolExecutor(max_workers=site_workers) as executor:
                futures = {}
                for entry in ready:
                    total_attempts += 1
                    attempted_names.append(entry["name"])
                    display = f"[{total_attempts}] {entry['name']}"
                    print(f"{display} queued")
                    if entry["prior_status"]:
                        print(f"  prior: {entry['prior_status']}")
                    futures[executor.submit(run_site, entry)] = entry

                while futures:
                    done, _ = wait(list(futures.keys()), timeout=20, return_when=FIRST_COMPLETED)
                    if not done:
                        print(f"[heartbeat] active={len(futures)} pending={len(pending)}")
                        sys.stdout.flush()
                        continue

                    for future in done:
                        entry = futures.pop(future)
                        result = future.result()
                        timed_out = bool(result["timed_out"])
                        output = str(result["output"] or "")
                        tail = output_tail(output)
                        latest_status = read_latest_status(entry["url"])
                        outcome = classify_result(timed_out, output, latest_status)

                        if timed_out:
                            print(f"TIMEOUT after {timeout_seconds}s: {entry['name']}")
                        else:
                            print(f"EXIT {result['returncode']}: {entry['name']} | {tail}")
                        print(f"Recorded status: {latest_status}")

                        if outcome == "success":
                            successes.add(entry["name"])
                            failures.discard(entry["name"])
                            timeouts.discard(entry["name"])
                            unknown.discard(entry["name"])
                            blocked.discard(entry["name"])
                        elif outcome == "failed":
                            failures.add(entry["name"])
                            successes.discard(entry["name"])
                        elif outcome == "timed_out":
                            timeouts.add(entry["name"])
                            successes.discard(entry["name"])
                        elif outcome == "block_suspected":
                            blocked.add(entry["name"])
                            unknown.add(entry["name"])
                            successes.discard(entry["name"])
                        else:
                            unknown.add(entry["name"])
                            successes.discard(entry["name"])

                        if outcome in {"timed_out", "block_suspected"} and domain_cooldown_seconds > 0:
                            domain_next_allowed[get_domain(entry["url"])] = time.time() + domain_cooldown_seconds

                        if outcome != "success" and retry_round < max_retry_rounds:
                            retry_candidates.append(
                                {
                                    "name": entry["name"],
                                    "url": entry["url"],
                                    "category": entry["category"],
                                    "prior_status": latest_status or entry["prior_status"],
                                }
                            )

                        sys.stdout.flush()

        entries = retry_candidates

    updated_state_by_url = load_state_by_url()
    now_dt = datetime.now(timezone.utc)
    for row in resources:
        url = normalize_url(row["url"])
        status = updated_state_by_url.get(url)
        previous_info = policy_state_by_url.get(url, {})
        previous_streak = int(previous_info.get("zero_ok_streak", 0)) if isinstance(previous_info, dict) else 0
        next_streak = (previous_streak + 1) if status_has_zero_ok_pages(status) else 0
        suppress_until = ""
        if next_streak >= zero_ok_streak_threshold:
            suppress_until = (now_dt + timedelta(hours=zero_ok_suppress_hours)).isoformat()
        policy_state_by_url[url] = {
            "zero_ok_streak": next_streak,
            "suppress_until": suppress_until,
        }
    save_policy_state(policy_state_path, policy_state_by_url)

    remaining = []
    remaining_urls: set[str] = set()
    now_ts = time.time()
    for row in resources:
        name = str(row["name"])
        url = normalize_url(row["url"])
        if site_name_filter and site_name_filter not in name.lower():
            continue
        status = updated_state_by_url.get(url)
        if should_queue_site(status, retry_failed, force_rescrape, policy_state_by_url.get(url), now_ts):
            remaining.append(name)
            remaining_urls.add(url)

    last_resources = resources
    last_remaining = remaining
    last_suppressed_zero_ok = count_zero_ok_suppressed(resources, updated_state_by_url, policy_state_by_url)

    if remaining:
        if remaining_urls == queued_urls:
            print("[auto-expand] cycle made no queue progress; treating remaining queue as stalled")
            expansion = maybe_expand_resources(expansion_rounds_used, "queue stalled after scrape cycle")
            if expansion is not None:
                expansion_events.append(expansion)
                expansion_rounds_used += 1
                resources_db.close()
                resources_db = open_resources_db()
                continue
        break

    expansion = maybe_expand_resources(expansion_rounds_used, "queue exhausted")
    if expansion is None:
        break

    expansion_events.append(expansion)
    expansion_rounds_used += 1
    resources_db.close()
    resources_db = open_resources_db()

print("\nSummary")
print(f"Attempted: {total_attempts}")
print(f"Succeeded: {len(successes)}")
print(f"Failed: {len(failures)}")
print(f"Timed out: {len(timeouts)}")
print(f"Unknown: {len(unknown)}")
print(f"Blocked suspected: {len(blocked)}")
print(f"Remaining queued after run: {len(last_remaining)}")
print(f"Zero-ok suppressed after run: {last_suppressed_zero_ok}")
print(f"Auto-expansion rounds used: {expansion_rounds_used}")

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

if blocked:
    print("Blocked suspected sites:")
    for name in sorted(blocked):
        print(f"- {name}")

report_lines = [
    "# Resource Scrape Post-Run Report",
    "",
    f"Generated: {datetime.now(timezone.utc).isoformat()}",
    f"Attempted: {total_attempts}",
    f"Succeeded: {len(successes)}",
    f"Failed: {len(failures)}",
    f"Timed out: {len(timeouts)}",
    f"Unknown: {len(unknown)}",
    f"Blocked suspected: {len(blocked)}",
    f"Remaining queued after run: {len(last_remaining)}",
    f"Zero-ok suppressed after run: {last_suppressed_zero_ok}",
    f"Retry failed enabled: {retry_failed}",
    f"Per-site timeout: {timeout_seconds}s",
    f"Max pages per site: {max_pages_per_site}",
    f"Site workers: {site_workers}",
    f"Retry rounds: {max_retry_rounds}",
    f"Domain cooldown: {domain_cooldown_seconds}s",
    f"LM Studio model: {lmstudio_model}",
    f"Quiet crawl: {quiet_crawl}",
    f"Skip podcasts: {skip_podcasts}",
    f"Auto-expand resources: {auto_expand_resources}",
    f"Auto-expand batch size: {auto_expand_batch_size}",
    f"Auto-expand max rounds: {auto_expand_max_rounds}",
    f"Zero-ok suppression threshold: {zero_ok_streak_threshold}",
    f"Zero-ok suppression hours: {zero_ok_suppress_hours}",
    f"Auto-expansion rounds used: {expansion_rounds_used}",
]

if expansion_events:
    report_lines.extend(["", "## Auto-expanded Resources", ""])
    for index, event in enumerate(expansion_events, start=1):
        names = ", ".join(str(name) for name in event.get("added_names", [])) or "none"
        reason = str(event.get("trigger_reason", "queue exhausted"))
        report_lines.append(f"- Round {index} ({reason}): {names}")

if failures:
    report_lines.extend(["", "## Failed Sites", ""])
    report_lines.extend(f"- {name}" for name in failures)

if timeouts:
    report_lines.extend(["", "## Timed Out Sites", ""])
    report_lines.extend(f"- {name}" for name in timeouts)

if unknown:
    report_lines.extend(["", "## Unknown Status Sites", ""])
    report_lines.extend(f"- {name}" for name in sorted(unknown))

if blocked:
    report_lines.extend(["", "## Blocked Suspected Sites", ""])
    report_lines.extend(f"- {name}" for name in sorted(blocked))

if last_remaining:
    report_lines.extend(["", "## Remaining Queue", ""])
    report_lines.extend(f"- {name}" for name in last_remaining)

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
print(f"Post-run report: {report_path}")
resources_db.close()
state_db.close()
PY