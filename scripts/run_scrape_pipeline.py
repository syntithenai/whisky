#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import re
import select
import sqlite3
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


ALLOWED_IMAGE_LABELS = {"bottle", "logo", "award", "lifestyle", "equipment", "junk"}


class PipelineTerminated(RuntimeError):
    """Raised when the pipeline receives a termination signal."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {message}", flush=True)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def try_parse_json_block(content: str) -> Any:
    content = content.strip()
    try:
        return json.loads(content)
    except Exception:
        pass

    match = re.search(r"\{.*\}", content, re.S)
    if match:
        return json.loads(match.group(0))
    match = re.search(r"\[.*\]", content, re.S)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON block found in model response")


def lmstudio_chat_json(base_url: str, model: str, system_prompt: str, user_payload: dict[str, Any], timeout: int) -> Any:
    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ],
    }
    req = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    content = payload["choices"][0]["message"]["content"]
    return try_parse_json_block(content)


def ensure_models_available(base_url: str, required_models: list[str]) -> None:
    req = Request(base_url.rstrip("/") + "/models", method="GET")
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    raw_data = payload.get("data") if isinstance(payload, dict) else []
    data = raw_data if isinstance(raw_data, list) else []
    ids = {str(item.get("id", "")).strip() for item in data if isinstance(item, dict)}
    aliases = set(ids)
    for mid in list(ids):
        if "/" in mid:
            aliases.add(mid.split("/")[-1])

    missing: list[str] = []
    for model in required_models:
        wanted = {model}
        if "/" in model:
            wanted.add(model.split("/")[-1])
        if not (wanted & aliases):
            missing.append(model)
    if missing:
        raise RuntimeError(f"Missing required model(s): {', '.join(missing)}")


def load_model_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Invalid model policy JSON")
    return payload


def resolve_models(policy: dict[str, Any], args: argparse.Namespace) -> dict[str, str]:
    models = dict((policy.get("models") or {}))

    resolved = {
        "summarization": str(args.lmstudio_model or models.get("summarization") or "openai/gpt-oss-20b"),
        "review": str(args.lmstudio_review_model or models.get("review") or "google/gemma-3-27b"),
        "image_labeling": str(args.lmstudio_image_label_model or models.get("image_labeling") or "google/gemma-3-27b"),
        "relevance_screening": str(args.lmstudio_screen_model or models.get("relevance_screening") or "ibm/granite-4-h-tiny"),
    }
    return resolved


def parse_run_summary_from_report(path: Path) -> dict[str, int]:
    out = {
        "sites_processed": 0,
        "sites_succeeded": 0,
        "sites_failed": 0,
        "pages_processed": 0,
        "pages_skipped": 0,
        "pages_failed": 0,
        "pages_summarized": 0,
    }
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8", errors="replace")
    mapping = {
        "sites_processed": r"-\s*Sites processed:\s*(\d+)",
        "sites_succeeded": r"-\s*Sites succeeded:\s*(\d+)",
        "sites_failed": r"-\s*Sites failed:\s*(\d+)",
        "pages_processed": r"-\s*Pages processed:\s*(\d+)",
        "pages_skipped": r"-\s*Pages skipped:\s*(\d+)",
        "pages_failed": r"-\s*Pages failed:\s*(\d+)",
        "pages_summarized": r"-\s*Pages summarized:\s*(\d+)",
    }
    for key, pattern in mapping.items():
        m = re.search(pattern, text)
        if m:
            out[key] = int(m.group(1))
    return out


def read_quality_distribution(csv_path: Path) -> dict[str, int]:
    dist = {"high": 0, "medium": 0, "low": 0}
    if not csv_path.exists():
        return dist
    with csv_path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = str(row.get("relevance_label") or "").strip().lower()
            if label in dist:
                dist[label] += 1
    return dist


def ensure_image_label_columns(conn: sqlite3.Connection) -> None:
    cols = {str(r[1]).lower() for r in conn.execute("PRAGMA table_info(images)").fetchall()}
    additions = []
    if "ai_label" not in cols:
        additions.append(("ai_label", "TEXT"))
    if "ai_label_confidence" not in cols:
        additions.append(("ai_label_confidence", "REAL"))
    if "ai_label_reason" not in cols:
        additions.append(("ai_label_reason", "TEXT"))
    if "ai_labeled_at" not in cols:
        additions.append(("ai_labeled_at", "TEXT"))
    if "ai_label_model" not in cols:
        additions.append(("ai_label_model", "TEXT"))
    if "ai_label_prompt_version" not in cols:
        additions.append(("ai_label_prompt_version", "TEXT"))
    for name, typ in additions:
        conn.execute(f"ALTER TABLE images ADD COLUMN {name} {typ}")
    if additions:
        conn.commit()


def parse_min_source_width(source_url: str) -> int | None:
    try:
        parsed = urlparse(source_url)
        params = parse_qs(parsed.query)
        candidates = [*params.get("width", []), *params.get("w", [])]
        widths = [int(str(v)) for v in candidates if str(v).isdigit()]
        if widths:
            return min(widths)
    except Exception:
        return None
    return None


def run_review_phase(base_url: str, model: str, prompt_path: Path, timeout: int, run_summary: dict[str, Any],
                     manifest_dir: Path, triage_json: Path, quality_csv: Path, image_label_counts: dict[str, int]) -> dict[str, Any]:
    log_event("Review phase: preparing prompt payload")
    prompt = load_text(prompt_path)
    triage_snapshot: dict[str, Any] = {}
    if triage_json.exists():
        triage_snapshot = json.loads(triage_json.read_text(encoding="utf-8", errors="replace"))
    user_payload = {
        "run_summary": run_summary,
        "per_site_stats": {},
        "failure_stats": {
            "pages_failed": int(run_summary.get("pages_failed", 0)),
            "sites_failed": int(run_summary.get("sites_failed", 0)),
        },
        "relevance_distribution": read_quality_distribution(quality_csv),
        "triage_snapshot": triage_snapshot.get("counts", {}),
        "extraction_completeness": {},
        "image_label_distribution": image_label_counts,
    }
    parsed = lmstudio_chat_json(
        base_url=base_url,
        model=model,
        system_prompt=prompt,
        user_payload=user_payload,
        timeout=timeout,
    )
    out = {
        "run_id": manifest_dir.name,
        "generated_at": now_iso(),
        "model": model,
        "prompt_version": "review-v1",
        "summary": parsed.get("summary", {}),
        "priorities_next_run": parsed.get("priorities_next_run", []),
        "action_items": parsed.get("action_items", []),
    }
    out_path = manifest_dir / "review.json"
    out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    log_event(f"Review phase: completed -> {out_path}")
    return {"status": "completed", "output_file": str(out_path), "model": model, "prompt_version": "review-v1"}


def run_image_label_phase(base_url: str, model: str, prompt_path: Path, timeout: int, distillery_db: Path,
                          manifest_dir: Path, label_all: bool = False, max_images: int = 0,
                          workers: int = 8, state_db: Path | None = None,
                          min_image_score: int = 70, min_page_relevance_score: int = 20,
                          min_source_width: int = 240, min_raster_file_bytes: int = 12_000) -> tuple[dict[str, Any], dict[str, int]]:
    prompt = load_text(prompt_path)

    worker_count = max(1, int(workers))

    def _label_one(row: sqlite3.Row) -> dict[str, Any]:
        image_id = f"db-image:{int(row['id'])}"
        user_payload = {
            "image_id": image_id,
            "source_url": str(row["source_url"] or ""),
            "page_url": str(row["page_url"] or ""),
            "local_path": str(row["local_path"] or ""),
            "alt_text": str(row["alt_text"] or ""),
            "context_excerpt": str(row["category"] or ""),
        }
        parsed = lmstudio_chat_json(
            base_url=base_url,
            model=model,
            system_prompt=prompt,
            user_payload=user_payload,
            timeout=timeout,
        )

        if isinstance(parsed, list):
            item = parsed[0] if parsed else {}
        else:
            item = parsed

        label = str(item.get("label", "")).strip().lower()
        if label not in ALLOWED_IMAGE_LABELS:
            label = "junk"
        conf = float(item.get("confidence", 0.0) or 0.0)
        conf = max(0.0, min(1.0, conf))
        reason = str(item.get("reason", "")).strip()[:280]
        reviewed_at = now_iso()

        return {
            "db_id": int(row["id"]),
            "image_id": image_id,
            "source_url": str(row["source_url"] or ""),
            "local_path": str(row["local_path"] or ""),
            "page_url": str(row["page_url"] or ""),
            "label": label,
            "confidence": conf,
            "reason": reason,
            "reviewed_at": reviewed_at,
        }

    conn = sqlite3.connect(distillery_db)
    conn.row_factory = sqlite3.Row
    try:
        ensure_image_label_columns(conn)
        attached_state = False
        if state_db and state_db.exists() and min_page_relevance_score > 0:
            conn.execute("ATTACH DATABASE ? AS state", (str(state_db),))
            attached_state = True

        where_clauses = ["LOWER(COALESCE(i.ai_label, '')) <> 'junk'"]
        params: list[Any] = []
        if not label_all:
            where_clauses.append("COALESCE(i.ai_label, '') = ''")
        if min_image_score > 0:
            where_clauses.append("COALESCE(i.score, 0) >= ?")
            params.append(int(min_image_score))
        if attached_state and min_page_relevance_score > 0:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM state.pages p
                    WHERE p.url = i.page_url
                      AND COALESCE(p.is_content_excluded, 0) = 0
                      AND COALESCE(p.is_quarantined, 0) = 0
                      AND COALESCE(p.relevance_score, 0) >= ?
                )
                """
            )
            params.append(int(min_page_relevance_score))

        where = "WHERE " + " AND ".join(clause.strip() for clause in where_clauses)
        limit_clause = f"LIMIT {int(max_images)}" if max_images > 0 else ""
        rows = conn.execute(
            f"""
            SELECT i.id, i.source_url, i.page_url, i.local_path, i.alt_text, i.category, COALESCE(i.score, 0) AS score
            FROM images i
            {where}
            ORDER BY i.score DESC, i.id ASC
            {limit_clause}
            """,
            params,
        ).fetchall()

        pre_quality_count = len(rows)
        filtered_low_quality = 0
        filtered_rows: list[sqlite3.Row] = []
        raster_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        min_width_threshold = max(0, int(min_source_width))
        min_bytes_threshold = max(0, int(min_raster_file_bytes))
        for row in rows:
            source_url = str(row["source_url"] or "")
            width_hint = parse_min_source_width(source_url)
            if width_hint is not None and min_width_threshold > 0 and width_hint < min_width_threshold:
                filtered_low_quality += 1
                continue

            local_path = str(row["local_path"] or "").strip()
            local_file = distillery_db.parent / local_path
            suffix = local_file.suffix.lower()
            if min_bytes_threshold > 0 and suffix in raster_exts and local_file.exists():
                try:
                    if local_file.stat().st_size < min_bytes_threshold:
                        filtered_low_quality += 1
                        continue
                except OSError:
                    pass

            filtered_rows.append(row)

        rows = filtered_rows

        log_event(
            "Image labeling phase: "
            f"{pre_quality_count} candidate(s) after relevance/junk filters; "
            f"{filtered_low_quality} removed for low quality; "
            f"{len(rows)} queued; workers={worker_count}"
        )

        records = []
        counts = {k: 0 for k in sorted(ALLOWED_IMAGE_LABELS)}
        total = len(rows)
        completed = 0
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(_label_one, row): row for row in rows}
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                log_event(
                    "Image labeling phase: completed "
                    f"{completed}/{total} ({result['image_id']}, label={result['label']})"
                )

                conn.execute(
                    """
                    UPDATE images
                    SET ai_label = ?,
                        ai_label_confidence = ?,
                        ai_label_reason = ?,
                        ai_labeled_at = ?,
                        ai_label_model = ?,
                        ai_label_prompt_version = ?
                    WHERE id = ?
                    """,
                    (
                        result["label"],
                        result["confidence"],
                        result["reason"],
                        result["reviewed_at"],
                        model,
                        "image-label-v1",
                        result["db_id"],
                    ),
                )

                counts[result["label"]] += 1
                records.append(
                    {
                        "image_id": result["image_id"],
                        "source_url": result["source_url"],
                        "local_path": result["local_path"],
                        "page_url": result["page_url"],
                        "label": result["label"],
                        "confidence": result["confidence"],
                        "reason": result["reason"],
                        "reviewed_at": result["reviewed_at"],
                    }
                )

        conn.commit()

        payload = {
            "run_id": manifest_dir.name,
            "generated_at": now_iso(),
            "model": model,
            "prompt_version": "image-label-v1",
            "allowed_labels": sorted(ALLOWED_IMAGE_LABELS),
            "records": records,
        }
        out_path = manifest_dir / "image_labels.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        log_event(f"Image labeling phase: completed -> {out_path}")

        phase = {
            "status": "completed",
            "output_file": str(out_path),
            "model": model,
            "prompt_version": "image-label-v1",
            "images_total": len(rows),
            "images_labeled": len(records),
            "label_counts": counts,
            "filters": {
                "excluded_pre_labeled_junk": True,
                "min_image_score": int(min_image_score),
                "min_page_relevance_score": int(min_page_relevance_score),
                "min_source_width": int(min_source_width),
                "min_raster_file_bytes": int(min_raster_file_bytes),
                "candidates_after_relevance": pre_quality_count,
                "excluded_low_quality": filtered_low_quality,
                "queued_for_labeling": len(rows),
            },
        }
        return phase, counts
    finally:
        try:
            conn.execute("DETACH DATABASE state")
        except Exception:
            pass
        conn.close()


def run_cmd(
    cmd: list[str],
    stream_prefix: str = "",
    activity_label: str = "subprocess",
    heartbeat_seconds: int = 20,
    max_silence_seconds: int = 0,
) -> tuple[int, str]:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        lines: list[str] = []
        assert proc.stdout is not None
        fd = proc.stdout.fileno()
        last_output = time.monotonic()
        heartbeat = max(5, int(heartbeat_seconds))
        hard_silence_limit = max(0, int(max_silence_seconds))
        terminated_for_silence = False
        while True:
            ready, _, _ = select.select([fd], [], [], heartbeat)
            if ready:
                raw_line = proc.stdout.readline()
                if raw_line == "":
                    if proc.poll() is not None:
                        break
                    continue
                lines.append(raw_line)
                line = raw_line.rstrip("\n")
                if stream_prefix:
                    print(f"{stream_prefix}{line}", flush=True)
                else:
                    print(line, flush=True)
                last_output = time.monotonic()
                continue

            if proc.poll() is not None:
                break
            silent_for = int(time.monotonic() - last_output)
            log_event(f"{activity_label}: still running ({silent_for}s since last output)")

            if hard_silence_limit > 0 and silent_for >= hard_silence_limit:
                log_event(
                    f"{activity_label}: no output for {silent_for}s (limit={hard_silence_limit}s); terminating child process"
                )
                proc.terminate()
                terminated_for_silence = True
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    log_event(f"{activity_label}: child did not exit after terminate; killing")
                    proc.kill()
                break

        remainder = proc.stdout.read()
        if remainder:
            for raw_line in remainder.splitlines(True):
                lines.append(raw_line)
                line = raw_line.rstrip("\n")
                if stream_prefix:
                    print(f"{stream_prefix}{line}", flush=True)
                else:
                    print(line, flush=True)

        proc.wait()
        output = "".join(lines)
        if terminated_for_silence:
            output += (
                "\n[pipeline] child terminated due to output silence timeout"
                f" ({hard_silence_limit}s)\n"
            )
            return 124, output
        return proc.returncode, output
    except KeyboardInterrupt as exc:
        raise PipelineTerminated("Interrupted while waiting for a child process") from exc


def load_manifest_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def latest_manifest_path(run_manifests_root: Path) -> Path | None:
    if not run_manifests_root.exists():
        return None
    candidates: list[Path] = []
    for child in run_manifests_root.iterdir():
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if manifest_path.exists():
            candidates.append(manifest_path)
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.parent.name, reverse=True)[0]


def load_previous_review_payload(previous_manifest_path: Path | None) -> dict[str, Any] | None:
    if previous_manifest_path is None:
        return None
    review_path = previous_manifest_path.parent / "review.json"
    if not review_path.exists():
        return None
    try:
        payload = json.loads(review_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def derive_review_crawl_overrides(review_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not review_payload:
        return {
            "enabled": False,
            "reasons": [],
            "chunk_size_min": None,
            "max_pages_per_site_min": None,
            "force_rescrape_first_iteration": False,
        }

    priorities = review_payload.get("priorities_next_run")
    action_items = review_payload.get("action_items")
    pr_list = priorities if isinstance(priorities, list) else []
    ai_list = action_items if isinstance(action_items, list) else []

    haystack_parts: list[str] = []
    for item in pr_list:
        if not isinstance(item, dict):
            continue
        haystack_parts.extend([
            str(item.get("type", "")),
            str(item.get("name", "")),
            str(item.get("reason", "")),
        ])
    for item in ai_list:
        if not isinstance(item, dict):
            continue
        haystack_parts.extend([
            str(item.get("category", "")),
            str(item.get("title", "")),
            str(item.get("details", "")),
            str(item.get("suggested_fix", "")),
        ])

    haystack = "\n".join(haystack_parts).lower()
    if not haystack.strip():
        return {
            "enabled": False,
            "reasons": [],
            "chunk_size_min": None,
            "max_pages_per_site_min": None,
            "force_rescrape_first_iteration": False,
        }

    needs_page_processing = any(
        token in haystack
        for token in [
            "process pages",
            "no pages processed",
            "configure page processing",
            "page processing",
            "data_collection",
        ]
    )
    quality_concern = any(
        token in haystack
        for token in [
            "relevance",
            "noisy",
            "content filtering",
            "data_quality",
        ]
    )

    reasons: list[str] = []
    chunk_size_min: int | None = None
    max_pages_min: int | None = None
    force_first = False

    if needs_page_processing:
        reasons.append("review requested stronger page processing coverage")
        chunk_size_min = 25
        max_pages_min = 40
        force_first = True

    if quality_concern:
        reasons.append("review flagged relevance/noise quality issues")
        if max_pages_min is None:
            max_pages_min = 40

    return {
        "enabled": bool(reasons),
        "reasons": reasons,
        "chunk_size_min": chunk_size_min,
        "max_pages_per_site_min": max_pages_min,
        "force_rescrape_first_iteration": force_first,
    }


def run_content_generation_phase(manifest_dir: Path, min_unique_per_phase: int = 0) -> dict[str, Any]:
    log_event("Content generation phase: starting")
    cmd = [sys.executable, "scripts/generate_content.py"]
    if min_unique_per_phase != 15:  # only pass if non-default
        cmd += ["--min-unique-per-phase", str(min_unique_per_phase)]
    rc, out = run_cmd(
        cmd,
        stream_prefix="[content] ",
        activity_label="content generation",
        heartbeat_seconds=20,
    )
    gen_log = manifest_dir / "generate_content.log"
    gen_log.write_text(out, encoding="utf-8")
    if rc != 0:
        raise RuntimeError("generate_content.py failed")
    log_event(f"Content generation phase: completed; log={gen_log}")
    return {"status": "completed", "log": str(gen_log), "returncode": int(rc)}


def resume_last_run_postprocessing(
    previous_manifest_path: Path | None,
    *,
    base_url: str,
    timeout: int,
    models: dict[str, str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if previous_manifest_path is None:
        return {"status": "skipped", "reason": "no previous run manifest"}

    previous_manifest = load_manifest_file(previous_manifest_path)
    if previous_manifest is None:
        return {"status": "skipped", "reason": f"invalid manifest JSON: {previous_manifest_path}"}

    previous_run_id = str(previous_manifest.get("run_id") or previous_manifest_path.parent.name)
    previous_phases = previous_manifest.get("phases") if isinstance(previous_manifest.get("phases"), dict) else {}
    previous_crawl = previous_phases.get("crawl") if isinstance(previous_phases, dict) else {}
    previous_crawl_status = str(previous_crawl.get("status") or "") if isinstance(previous_crawl, dict) else ""
    if previous_crawl_status and previous_crawl_status != "completed":
        return {
            "status": "skipped",
            "reason": "last run crawl phase not completed",
            "last_run_id": previous_run_id,
        }

    image_phase_prev = previous_phases.get("image_labeling") if isinstance(previous_phases, dict) else {}
    review_phase_prev = previous_phases.get("review") if isinstance(previous_phases, dict) else {}
    content_phase_prev = previous_phases.get("content_generation") if isinstance(previous_phases, dict) else {}

    image_completed = isinstance(image_phase_prev, dict) and str(image_phase_prev.get("status") or "") == "completed"
    review_completed = isinstance(review_phase_prev, dict) and str(review_phase_prev.get("status") or "") == "completed"
    content_completed = isinstance(content_phase_prev, dict) and str(content_phase_prev.get("status") or "") == "completed"

    need_image = bool(args.enable_image_labeling) and not image_completed
    need_content = not bool(args.skip_generate_content) and not content_completed
    need_review = bool(args.enable_run_review) and not review_completed

    if not (need_image or need_content or need_review):
        return {
            "status": "skipped",
            "reason": "last run has no incomplete post-processing phases",
            "last_run_id": previous_run_id,
        }

    previous_manifest_dir = previous_manifest_path.parent
    log_event(
        "Pre-crawl recovery: detected incomplete post-processing in last run "
        f"{previous_run_id}; resuming before crawl"
    )

    if not isinstance(previous_manifest.get("phases"), dict):
        previous_manifest["phases"] = {}

    image_counts = {k: 0 for k in sorted(ALLOWED_IMAGE_LABELS)}
    if image_completed and isinstance(image_phase_prev, dict):
        existing_counts = image_phase_prev.get("label_counts")
        if isinstance(existing_counts, dict):
            for label in image_counts:
                value = existing_counts.get(label)
                if isinstance(value, int):
                    image_counts[label] = value

    try:
        if need_image:
            phase, image_counts = run_image_label_phase(
                base_url=base_url,
                model=models["image_labeling"],
                prompt_path=Path("prompts/image_label/image-label-v1.md"),
                timeout=timeout,
                distillery_db=Path(args.distillery_db),
                manifest_dir=previous_manifest_dir,
                label_all=args.image_label_all,
                max_images=args.image_label_max_images,
                workers=args.image_label_workers,
                state_db=Path(args.state_db),
                min_image_score=args.image_label_min_image_score,
                min_page_relevance_score=args.image_label_min_page_relevance_score,
                min_source_width=args.image_label_min_source_width,
                min_raster_file_bytes=args.image_label_min_raster_bytes,
            )
            previous_manifest["phases"]["image_labeling"] = phase

        if need_content:
            previous_manifest["phases"]["content_generation"] = run_content_generation_phase(previous_manifest_dir, min_unique_per_phase=args.min_unique_per_phase)

        if need_review:
            run_summary = parse_run_summary_from_report(Path("data/crawl_report.md"))
            review_phase = run_review_phase(
                base_url=base_url,
                model=models["review"],
                prompt_path=Path("prompts/review/review-v1.md"),
                timeout=timeout,
                run_summary=run_summary,
                manifest_dir=previous_manifest_dir,
                triage_json=Path("data/resource_triage.json"),
                quality_csv=Path("data/crawl_quality_audit.csv"),
                image_label_counts=image_counts,
            )
            previous_manifest["phases"]["review"] = review_phase

        previous_manifest["status"] = "completed"
        previous_manifest["ended_at"] = now_iso()
        previous_manifest_path.write_text(
            json.dumps(previous_manifest, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

        log_event(f"Pre-crawl recovery: completed for last run {previous_run_id}")
        return {
            "status": "completed",
            "last_run_id": previous_run_id,
            "manifest": str(previous_manifest_path),
            "resumed": {
                "image_labeling": need_image,
                "content_generation": need_content,
                "review": need_review,
            },
        }
    except Exception as exc:
        previous_manifest["status"] = "failed"
        previous_manifest["error"] = f"{type(exc).__name__}: {exc}"
        previous_manifest["ended_at"] = now_iso()
        previous_manifest_path.write_text(
            json.dumps(previous_manifest, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified scrape pipeline with Gemma review and image labeling.")
    parser.add_argument("--model-policy", default="config/model_policy.json")
    parser.add_argument("--lmstudio-url", default="")
    parser.add_argument("--lmstudio-model", default="")
    parser.add_argument("--lmstudio-screen-model", default="")
    parser.add_argument("--lmstudio-review-model", default="")
    parser.add_argument("--lmstudio-image-label-model", default="")
    parser.add_argument("--site-types", default="both", choices=["both", "distillery", "resource"])
    parser.add_argument("--chunk-size", type=int, default=15)
    parser.add_argument("--continue-count", type=int, default=1)
    parser.add_argument("--filter-name", default="")
    parser.add_argument("--max-pages-per-site", type=int, default=30)
    parser.add_argument("--lmstudio-extract-timeout", type=int, default=600)
    parser.add_argument("--max-audio-files-per-page", type=int, default=1)
    parser.add_argument(
        "--crawl-max-silence-seconds",
        type=int,
        default=240,
        help="Terminate crawl subprocess if no output is observed for this many seconds (0 disables).",
    )
    parser.add_argument("--force-rescrape", action="store_true")
    parser.add_argument(
        "--recovery-mode",
        default="normal",
        choices=["normal", "incomplete"],
        help="Pass through crawler recovery mode. 'incomplete' revisits only known incomplete pages.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--enable-run-review", action="store_true", default=True)
    parser.add_argument("--enable-image-labeling", action="store_true", default=True)
    parser.add_argument("--strict-image-labeling", action="store_true", default=True)
    parser.add_argument("--skip-generate-content", action="store_true")
    parser.add_argument(
        "--min-unique-per-phase",
        type=int,
        default=0,
        help="Minimum unique queue items required per phase in content generation (0 disables the check).",
    )
    parser.add_argument("--image-label-all", action="store_true")
    parser.add_argument("--image-label-max-images", type=int, default=0)
    parser.add_argument(
        "--image-label-workers",
        type=int,
        default=8,
        help="Number of parallel final image-label requests to dispatch (LM Studio queues them).",
    )
    parser.add_argument(
        "--image-label-min-image-score",
        type=int,
        default=70,
        help="Minimum image score required before sending to Gemma image labeling.",
    )
    parser.add_argument(
        "--image-label-min-page-relevance-score",
        type=int,
        default=20,
        help="Minimum page relevance score required before sending page images to Gemma (0 disables).",
    )
    parser.add_argument(
        "--image-label-min-source-width",
        type=int,
        default=240,
        help="Minimum source URL width hint allowed (width/w query params below this are filtered).",
    )
    parser.add_argument(
        "--image-label-min-raster-bytes",
        type=int,
        default=12000,
        help="Minimum local raster file size in bytes; smaller files are filtered as low quality.",
    )
    parser.add_argument("--whisper-service-url", default="http://127.0.0.1:10010")
    parser.add_argument("--state-db", default="data/site_crawl_state.db")
    parser.add_argument("--distillery-db", default="data/distilleries.db")
    parser.add_argument("--resource-db", default="data/resources.db")
    parser.add_argument(
        "--skip-pre-crawl-postprocess",
        action="store_true",
        help="Skip automatic recovery of incomplete post-processing from the latest previous run.",
    )
    args = parser.parse_args()

    termination_state: dict[str, int | None] = {"signal": None}

    def handle_termination(signum: int, _frame: Any) -> None:
        termination_state["signal"] = signum
        signal_name = signal.Signals(signum).name
        raise PipelineTerminated(f"Received {signal_name}")

    signal.signal(signal.SIGTERM, handle_termination)
    signal.signal(signal.SIGINT, handle_termination)

    policy_path = Path(args.model_policy)
    policy = load_model_policy(policy_path)

    base_url = args.lmstudio_url or str(((policy.get("lmstudio") or {}).get("base_url") or "http://127.0.0.1:1234/v1"))
    timeout = int(((policy.get("lmstudio") or {}).get("request_timeout_seconds") or 3600))
    models = resolve_models(policy, args)

    required_models = [models["summarization"], models["review"], models["image_labeling"], models["relevance_screening"]]
    log_event("Validating required LM Studio models")
    ensure_models_available(base_url=base_url, required_models=required_models)
    log_event("LM Studio model validation complete")

    run_manifests_root = Path("data/run_manifests")
    previous_manifest = latest_manifest_path(run_manifests_root)
    previous_review = load_previous_review_payload(previous_manifest)
    review_bridge = derive_review_crawl_overrides(previous_review)

    effective_chunk_size = int(args.chunk_size)
    effective_max_pages_per_site = int(args.max_pages_per_site)
    effective_force_rescrape = bool(args.force_rescrape)
    bridge_force_rescrape_first_iteration = False

    if review_bridge.get("enabled"):
        chunk_min = review_bridge.get("chunk_size_min")
        pages_min = review_bridge.get("max_pages_per_site_min")
        if isinstance(chunk_min, int):
            effective_chunk_size = max(effective_chunk_size, chunk_min)
        if isinstance(pages_min, int):
            effective_max_pages_per_site = max(effective_max_pages_per_site, pages_min)
        bridge_force_rescrape_first_iteration = bool(review_bridge.get("force_rescrape_first_iteration", False))
        log_event(
            "Review action bridge: applying overrides "
            f"chunk_size={effective_chunk_size} max_pages_per_site={effective_max_pages_per_site} "
            f"force_first_iteration={bridge_force_rescrape_first_iteration}"
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    manifest_dir = run_manifests_root / run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    log_event(f"Starting run {run_id}; manifest dir: {manifest_dir}")

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at": now_iso(),
        "status": "running",
        "model_policy": {
            "path": str(policy_path),
            "version": int(policy.get("version", 1)),
            "resolved": models,
        },
        "phases": {
            "pre_crawl_recovery": {"status": "pending", "enabled": not bool(args.skip_pre_crawl_postprocess)},
            "review_action_bridge": {"status": "pending", "enabled": True},
            "crawl": {"status": "pending"},
            "content_generation": {"enabled": not bool(args.skip_generate_content), "status": "pending"},
            "review": {"enabled": bool(args.enable_run_review), "status": "pending"},
            "image_labeling": {"enabled": bool(args.enable_image_labeling), "status": "pending"},
        },
        "iterations": [],
    }

    def write_manifest() -> None:
        (manifest_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    write_manifest()

    exit_code = 0

    try:
        if review_bridge.get("enabled"):
            manifest["phases"]["review_action_bridge"] = {
                "status": "completed",
                "source_run_manifest": str(previous_manifest) if previous_manifest else "",
                "reasons": review_bridge.get("reasons", []),
                "overrides": {
                    "chunk_size": effective_chunk_size,
                    "max_pages_per_site": effective_max_pages_per_site,
                    "force_rescrape_first_iteration": bridge_force_rescrape_first_iteration,
                },
            }
        else:
            manifest["phases"]["review_action_bridge"] = {
                "status": "skipped",
                "reason": "no actionable previous review data",
            }

        if args.skip_pre_crawl_postprocess:
            manifest["phases"]["pre_crawl_recovery"] = {"status": "skipped", "reason": "disabled by --skip-pre-crawl-postprocess"}
        else:
            recovery_result = resume_last_run_postprocessing(
                previous_manifest,
                base_url=base_url,
                timeout=timeout,
                models=models,
                args=args,
            )
            manifest["phases"]["pre_crawl_recovery"] = recovery_result
        write_manifest()

        loops = args.continue_count if args.continue_count != 0 else 1
        for i in range(1, loops + 1):
            log_event(f"Crawl phase: starting iteration {i}/{loops}")
            cmd = [
                sys.executable,
                "-u",
                "scripts/crawl_whisky_sites.py",
                "--site-types",
                args.site_types,
                "--max-sites",
                str(effective_chunk_size),
                "--max-pages-per-site",
                str(effective_max_pages_per_site),
                "--recovery-mode",
                args.recovery_mode,
                "--state-db",
                args.state_db,
                "--distillery-db",
                args.distillery_db,
                "--resource-db",
                args.resource_db,
                "--lmstudio-url",
                base_url,
                "--lmstudio-screen-model",
                models["relevance_screening"],
                "--lmstudio-model",
                models["summarization"],
                "--lmstudio-extract-timeout",
                str(args.lmstudio_extract_timeout),
                "--max-audio-files-per-page",
                str(args.max_audio_files_per_page),
                "--whisper-service-url",
                args.whisper_service_url,
            ]
            if args.filter_name:
                cmd += ["--filter-name", args.filter_name]
            force_this_iteration = effective_force_rescrape or (bridge_force_rescrape_first_iteration and i == 1)
            if force_this_iteration:
                cmd.append("--force-rescrape")
            if args.headless:
                cmd.append("--headless")

            log_event("Crawl phase: launching crawler process")
            rc, out = run_cmd(
                cmd,
                stream_prefix=f"[crawl:{i}] ",
                activity_label=f"crawl iteration {i}/{loops}",
                heartbeat_seconds=20,
                max_silence_seconds=args.crawl_max_silence_seconds,
            )
            iter_log = manifest_dir / f"crawl_iteration_{i}.log"
            iter_log.write_text(out, encoding="utf-8")
            manifest["iterations"].append({"index": i, "returncode": rc, "log": str(iter_log), "completed_at": now_iso()})
            log_event(f"Crawl phase: iteration {i}/{loops} finished with rc={rc}; log={iter_log}")
            if rc != 0:
                raise RuntimeError(f"Crawl iteration {i} failed with rc={rc}")

        manifest["phases"]["crawl"] = {"status": "completed", "iterations": len(manifest["iterations"])}
        log_event("Crawl phase: completed")

        # Post-crawl content generation
        if not args.skip_generate_content:
            manifest["phases"]["content_generation"] = run_content_generation_phase(manifest_dir, min_unique_per_phase=args.min_unique_per_phase)
        else:
            manifest["phases"]["content_generation"] = {"status": "skipped", "reason": "disabled by --skip-generate-content"}

        run_summary = parse_run_summary_from_report(Path("data/crawl_report.md"))

        image_counts = {k: 0 for k in sorted(ALLOWED_IMAGE_LABELS)}
        if args.enable_image_labeling:
            log_event("Image labeling phase: starting")
            phase, image_counts = run_image_label_phase(
                base_url=base_url,
                model=models["image_labeling"],
                prompt_path=Path("prompts/image_label/image-label-v1.md"),
                timeout=timeout,
                distillery_db=Path(args.distillery_db),
                manifest_dir=manifest_dir,
                label_all=args.image_label_all,
                max_images=args.image_label_max_images,
                workers=args.image_label_workers,
                state_db=Path(args.state_db),
                min_image_score=args.image_label_min_image_score,
                min_page_relevance_score=args.image_label_min_page_relevance_score,
                min_source_width=args.image_label_min_source_width,
                min_raster_file_bytes=args.image_label_min_raster_bytes,
            )
            manifest["phases"]["image_labeling"] = phase
            log_event(f"Image labeling phase: done; labeled={phase.get('images_labeled', 0)}")

        if args.enable_run_review:
            log_event("Review phase: starting")
            review_phase = run_review_phase(
                base_url=base_url,
                model=models["review"],
                prompt_path=Path("prompts/review/review-v1.md"),
                timeout=timeout,
                run_summary=run_summary,
                manifest_dir=manifest_dir,
                triage_json=Path("data/resource_triage.json"),
                quality_csv=Path("data/crawl_quality_audit.csv"),
                image_label_counts=image_counts,
            )
            manifest["phases"]["review"] = review_phase
            log_event("Review phase: done")

        manifest["status"] = "completed"
        log_event("Pipeline status: completed")
    except PipelineTerminated as exc:
        manifest["status"] = "terminated"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        signum = termination_state.get("signal")
        if signum is not None:
            manifest["termination_signal"] = int(signum)
            exit_code = 128 + int(signum)
        else:
            exit_code = 143
        log_event(f"Pipeline status: terminated ({manifest.get('error')})")
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        if args.strict_image_labeling and manifest["phases"].get("image_labeling", {}).get("status") == "failed":
            pass
        log_event(f"Pipeline status: failed ({manifest.get('error')})")
        raise
    finally:
        manifest["ended_at"] = now_iso()
        write_manifest()
        log_event(f"Manifest written: {manifest_dir / 'manifest.json'}")

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
