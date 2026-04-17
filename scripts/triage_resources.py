#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


COUNT_PATTERNS = {
    "product_names": re.compile(r"-\s*Product names:\s*(\d+)", re.IGNORECASE),
    "distillery_names": re.compile(r"-\s*Distillery names:\s*(\d+)", re.IGNORECASE),
    "chemical_names": re.compile(r"-\s*Chemical names:\s*(\d+)", re.IGNORECASE),
    "glossary_terms": re.compile(r"-\s*Glossary terms:\s*(\d+)", re.IGNORECASE),
    "distillery_tool_names": re.compile(r"-\s*Distillery tool names:\s*(\d+)", re.IGNORECASE),
    "flavor_profile_words": re.compile(r"-\s*Flavor profile words:\s*(\d+)", re.IGNORECASE),
}

REGULATORY_RE = re.compile(r"\b(regulation|legal|standard|label|gi|excise)\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:\$|\bAUD\b|\bUSD\b|\bGBP\b|\bEUR\b|\bprice\b)", re.IGNORECASE)
ABV_RE = re.compile(r"(?:\babv\b|\b\d{1,2}(?:\.\d)?\s*%)", re.IGNORECASE)


def parse_counts(metadata_text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, pattern in COUNT_PATTERNS.items():
        match = pattern.search(metadata_text)
        out[key] = int(match.group(1)) if match else 0
    return out


def compute_bucket(counts: dict[str, int], main_text: str) -> tuple[str, dict[str, bool]]:
    abv_mentioned = bool(ABV_RE.search(main_text))
    price_mentioned = bool(PRICE_RE.search(main_text))
    regulatory_overlap = bool(REGULATORY_RE.search(main_text))

    if counts.get("product_names", 0) >= 3 and (abv_mentioned or price_mentioned):
        return "product_catalog", {
            "abv_mentioned": abv_mentioned,
            "price_mentioned": price_mentioned,
            "regulatory_overlap": regulatory_overlap,
        }
    if regulatory_overlap:
        return "regulatory", {
            "abv_mentioned": abv_mentioned,
            "price_mentioned": price_mentioned,
            "regulatory_overlap": regulatory_overlap,
        }
    if counts.get("distillery_tool_names", 0) >= 1 or counts.get("chemical_names", 0) >= 1:
        return "technical_process", {
            "abv_mentioned": abv_mentioned,
            "price_mentioned": price_mentioned,
            "regulatory_overlap": regulatory_overlap,
        }
    return "noisy", {
        "abv_mentioned": abv_mentioned,
        "price_mentioned": price_mentioned,
        "regulatory_overlap": regulatory_overlap,
    }


def score_record(bucket: str, counts: dict[str, int], flags: dict[str, bool]) -> float:
    score = 0.0
    if bucket == "product_catalog":
        score += 50
    elif bucket == "technical_process":
        score += 40
    elif bucket == "regulatory":
        score += 35
    else:
        score += 10

    score += min(20, counts.get("product_names", 0) * 2)
    score += min(15, counts.get("chemical_names", 0) * 2)
    score += min(10, counts.get("distillery_tool_names", 0) * 2)
    score += min(10, counts.get("flavor_profile_words", 0))

    if flags.get("abv_mentioned"):
        score += 3
    if flags.get("price_mentioned"):
        score += 3
    if flags.get("regulatory_overlap"):
        score += 4

    return round(score, 2)


def build_records(crawl_markdown_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for metadata_path in sorted(crawl_markdown_dir.rglob("*-metadata.md")):
        metadata_text = metadata_path.read_text(encoding="utf-8", errors="replace")
        counts = parse_counts(metadata_text)

        main_path = metadata_path.with_name(metadata_path.name.replace("-metadata.md", ".md"))
        main_text = ""
        if main_path.exists():
            main_text = main_path.read_text(encoding="utf-8", errors="replace")

        bucket, flags = compute_bucket(counts=counts, main_text=main_text)
        score = score_record(bucket=bucket, counts=counts, flags=flags)

        records.append(
            {
                "metadata_path": str(metadata_path),
                "main_path": str(main_path),
                "bucket": bucket,
                "score": score,
                **counts,
                **flags,
            }
        )
    return records


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "metadata_path",
        "main_path",
        "bucket",
        "score",
        "product_names",
        "distillery_names",
        "chemical_names",
        "glossary_terms",
        "distillery_tool_names",
        "flavor_profile_words",
        "abv_mentioned",
        "price_mentioned",
        "regulatory_overlap",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({k: row.get(k) for k in fields})


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage crawled resource metadata into bucketed quality output.")
    parser.add_argument("--crawl-markdown", default="data/crawl_markdown", help="Root crawl markdown directory.")
    parser.add_argument("--json-out", default="data/resource_triage.json", help="JSON output path.")
    parser.add_argument("--csv-out", default="data/resource_triage.csv", help="CSV output path.")
    args = parser.parse_args()

    crawl_dir = Path(args.crawl_markdown)
    records = build_records(crawl_dir)

    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "records": records,
        "counts": {
            "total": len(records),
            "product_catalog": sum(1 for r in records if r["bucket"] == "product_catalog"),
            "technical_process": sum(1 for r in records if r["bucket"] == "technical_process"),
            "regulatory": sum(1 for r in records if r["bucket"] == "regulatory"),
            "noisy": sum(1 for r in records if r["bucket"] == "noisy"),
        },
    }

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    write_csv(Path(args.csv_out), records)

    print(json.dumps(payload["counts"], ensure_ascii=True))


if __name__ == "__main__":
    main()
