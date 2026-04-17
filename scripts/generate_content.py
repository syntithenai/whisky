#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_step(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stdout}")


def build_phase_queues(triage_json: Path, out_dir: Path) -> dict[str, int]:
    payload = json.loads(triage_json.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []

    out_dir.mkdir(parents=True, exist_ok=True)

    phase_map: dict[int, list[dict[str, Any]]] = {2: [], 3: [], 4: [], 5: [], 6: [], 9: [], 10: [], 11: []}

    for row in records:
        if not isinstance(row, dict):
            continue
        bucket = str(row.get("bucket") or "")
        main_path = str(row.get("main_path") or "")
        score = float(row.get("score") or 0)
        flavor_count = int(row.get("flavor_profile_words") or 0)

        entry = {
            "source": main_path,
            "bucket": bucket,
            "score": score,
            "rationale": "",
        }

        if bucket == "product_catalog":
            for p in [2, 4, 5]:
                e = dict(entry)
                e["rationale"] = "product catalog source with likely regional/history context"
                phase_map[p].append(e)
        if bucket == "technical_process":
            for p in [3, 6, 11]:
                e = dict(entry)
                e["rationale"] = "technical/process-heavy source"
                phase_map[p].append(e)
        if flavor_count >= 8:
            for p in [9, 10]:
                e = dict(entry)
                e["rationale"] = "flavor-dense source"
                phase_map[p].append(e)

    counts: dict[str, int] = {}
    for phase, items in phase_map.items():
        items_sorted = sorted(items, key=lambda x: float(x.get("score") or 0), reverse=True)
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "items": items_sorted[:200],
        }
        out_path = out_dir / f"phase_{phase}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        counts[str(phase)] = len(out["items"])

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate post-scrape content artifacts.")
    parser.add_argument("--triage-json", default="data/resource_triage.json")
    parser.add_argument("--triage-csv", default="data/resource_triage.csv")
    parser.add_argument("--phase-queue-dir", default="data/phase_insertion_queue")
    parser.add_argument("--products-dir", default="data/products")
    parser.add_argument("--product-limit", type=int, default=0)
    args = parser.parse_args()

    py = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
    py_cmd = str(py) if py.exists() else "python3"

    run_step([py_cmd, "scripts/triage_resources.py", "--json-out", args.triage_json, "--csv-out", args.triage_csv])
    run_step([
        py_cmd,
        "scripts/build_products_from_triage.py",
        "--triage-json",
        args.triage_json,
        "--products-dir",
        args.products_dir,
        "--limit",
        str(args.product_limit),
    ])

    queue_counts = build_phase_queues(Path(args.triage_json), Path(args.phase_queue_dir))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "triage_json": args.triage_json,
        "triage_csv": args.triage_csv,
        "phase_queue_counts": queue_counts,
    }
    out_report = Path("data/content_generation_report.json")
    out_report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
