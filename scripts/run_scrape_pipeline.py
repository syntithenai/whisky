#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ALLOWED_IMAGE_LABELS = {"bottle", "logo", "award", "lifestyle", "equipment", "junk"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    data = payload.get("data") if isinstance(payload, dict) else []
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
        "summarization": str(args.lmstudio_model or models.get("summarization") or "google/gemma-3-27b"),
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


def run_review_phase(base_url: str, model: str, prompt_path: Path, timeout: int, run_summary: dict[str, Any],
                     manifest_dir: Path, triage_json: Path, quality_csv: Path, image_label_counts: dict[str, int]) -> dict[str, Any]:
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
    return {"status": "completed", "output_file": str(out_path), "model": model, "prompt_version": "review-v1"}


def run_image_label_phase(base_url: str, model: str, prompt_path: Path, timeout: int, distillery_db: Path,
                          manifest_dir: Path, label_all: bool = False, max_images: int = 0) -> tuple[dict[str, Any], dict[str, int]]:
    prompt = load_text(prompt_path)

    conn = sqlite3.connect(distillery_db)
    conn.row_factory = sqlite3.Row
    try:
        ensure_image_label_columns(conn)
        where = "" if label_all else "WHERE COALESCE(ai_label, '') = ''"
        limit_clause = f"LIMIT {int(max_images)}" if max_images > 0 else ""
        rows = conn.execute(
            f"""
            SELECT id, source_url, page_url, local_path, alt_text, category
            FROM images
            {where}
            ORDER BY id ASC
            {limit_clause}
            """
        ).fetchall()

        records = []
        counts = {k: 0 for k in sorted(ALLOWED_IMAGE_LABELS)}
        for row in rows:
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
                (label, conf, reason, reviewed_at, model, "image-label-v1", int(row["id"])),
            )

            counts[label] += 1
            records.append(
                {
                    "image_id": image_id,
                    "source_url": str(row["source_url"] or ""),
                    "local_path": str(row["local_path"] or ""),
                    "page_url": str(row["page_url"] or ""),
                    "label": label,
                    "confidence": conf,
                    "reason": reason,
                    "reviewed_at": reviewed_at,
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

        phase = {
            "status": "completed",
            "output_file": str(out_path),
            "model": model,
            "prompt_version": "image-label-v1",
            "images_total": len(rows),
            "images_labeled": len(records),
            "label_counts": counts,
        }
        return phase, counts
    finally:
        conn.close()


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


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
    parser.add_argument("--force-rescrape", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--enable-run-review", action="store_true", default=True)
    parser.add_argument("--enable-image-labeling", action="store_true", default=True)
    parser.add_argument("--strict-image-labeling", action="store_true", default=True)
    parser.add_argument("--skip-generate-content", action="store_true")
    parser.add_argument("--image-label-all", action="store_true")
    parser.add_argument("--image-label-max-images", type=int, default=0)
    parser.add_argument("--whisper-service-url", default="http://127.0.0.1:10010")
    parser.add_argument("--state-db", default="data/site_crawl_state.db")
    parser.add_argument("--distillery-db", default="data/distilleries.db")
    parser.add_argument("--resource-db", default="data/resources.db")
    args = parser.parse_args()

    policy_path = Path(args.model_policy)
    policy = load_model_policy(policy_path)

    base_url = args.lmstudio_url or str(((policy.get("lmstudio") or {}).get("base_url") or "http://127.0.0.1:1234/v1"))
    timeout = int(((policy.get("lmstudio") or {}).get("request_timeout_seconds") or 3600))
    models = resolve_models(policy, args)

    required_models = [models["summarization"], models["review"], models["image_labeling"], models["relevance_screening"]]
    ensure_models_available(base_url=base_url, required_models=required_models)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    manifest_dir = Path("data/run_manifests") / run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at": now_iso(),
        "status": "running",
        "model_policy": {
            "path": str(policy_path),
            "version": int(policy.get("version", 1)),
            "resolved": models,
        },
        "phases": {"crawl": {"status": "pending"}, "review": {"enabled": bool(args.enable_run_review), "status": "pending"}, "image_labeling": {"enabled": bool(args.enable_image_labeling), "status": "pending"}},
        "iterations": [],
    }

    def write_manifest() -> None:
        (manifest_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    write_manifest()

    try:
        loops = args.continue_count if args.continue_count != 0 else 1
        for i in range(1, loops + 1):
            cmd = [
                sys.executable,
                "scripts/crawl_whisky_sites.py",
                "--site-types",
                args.site_types,
                "--max-sites",
                str(args.chunk_size),
                "--max-pages-per-site",
                str(args.max_pages_per_site),
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
            if args.force_rescrape:
                cmd.append("--force-rescrape")
            if args.headless:
                cmd.append("--headless")

            rc, out = run_cmd(cmd)
            iter_log = manifest_dir / f"crawl_iteration_{i}.log"
            iter_log.write_text(out, encoding="utf-8")
            manifest["iterations"].append({"index": i, "returncode": rc, "log": str(iter_log), "completed_at": now_iso()})
            if rc != 0:
                raise RuntimeError(f"Crawl iteration {i} failed with rc={rc}")

        manifest["phases"]["crawl"] = {"status": "completed", "iterations": len(manifest["iterations"])}

        # Post-crawl content generation
        if not args.skip_generate_content:
            rc, out = run_cmd([sys.executable, "scripts/generate_content.py"])
            gen_log = manifest_dir / "generate_content.log"
            gen_log.write_text(out, encoding="utf-8")
            if rc != 0:
                raise RuntimeError("generate_content.py failed")

        run_summary = parse_run_summary_from_report(Path("data/crawl_report.md"))

        image_counts = {k: 0 for k in sorted(ALLOWED_IMAGE_LABELS)}
        if args.enable_image_labeling:
            phase, image_counts = run_image_label_phase(
                base_url=base_url,
                model=models["image_labeling"],
                prompt_path=Path("prompts/image_label/image-label-v1.md"),
                timeout=timeout,
                distillery_db=Path(args.distillery_db),
                manifest_dir=manifest_dir,
                label_all=args.image_label_all,
                max_images=args.image_label_max_images,
            )
            manifest["phases"]["image_labeling"] = phase

        if args.enable_run_review:
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

        manifest["status"] = "completed"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        if args.strict_image_labeling and manifest["phases"].get("image_labeling", {}).get("status") == "failed":
            pass
        raise
    finally:
        manifest["ended_at"] = now_iso()
        write_manifest()


if __name__ == "__main__":
    main()
