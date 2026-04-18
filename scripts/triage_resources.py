#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
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

SECTION_TITLES = {
    "product_names": "product names",
    "distillery_names": "distillery names",
    "chemical_names": "chemical names",
    "glossary_terms": "glossary terms",
    "distillery_tool_names": "distillery tool names",
    "flavor_profile_words": "flavor profile words",
}

REGULATORY_RE = re.compile(r"\b(regulation|legal|standard|label|gi|excise)\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:\$|\bAUD\b|\bUSD\b|\bGBP\b|\bEUR\b|\bprice\b)", re.IGNORECASE)
ABV_RE = re.compile(r"(?:\babv\b|\b\d{1,2}(?:\.\d)?\s*%)", re.IGNORECASE)


def has_any_token(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)


def parse_counts(metadata_text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, pattern in COUNT_PATTERNS.items():
        match = pattern.search(metadata_text)
        out[key] = int(match.group(1)) if match else 0

    # Fallback for section-style metadata files:
    # ## Product Names
    # - item
    lines = metadata_text.splitlines()
    for key, section_title in SECTION_TITLES.items():
        if out.get(key, 0) > 0:
            continue
        in_section = False
        section_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                header = stripped[3:].strip().lower()
                in_section = header == section_title
                continue
            if in_section:
                if stripped.startswith("## "):
                    break
                if stripped.startswith("- "):
                    item = stripped[2:].strip()
                    if item:
                        section_count += 1
        out[key] = section_count
    return out


def compute_bucket(counts: dict[str, int], main_text: str, main_path: str) -> tuple[str, dict[str, bool]]:
    abv_mentioned = bool(ABV_RE.search(main_text))
    price_mentioned = bool(PRICE_RE.search(main_text))
    regulatory_overlap = bool(REGULATORY_RE.search(main_text))
    main_path_lower = main_path.lower()

    product_path_signal = has_any_token(
        main_path_lower,
        ("/shop", "-shop", "/store", "-store", "/product", "-product", "/products", "/collections"),
    )
    technical_path_signal = has_any_token(
        main_path_lower,
        ("/process", "-process", "/distillation", "-distillation", "/ferment", "-ferment", "/mash", "-mash", "/cask", "-cask", "/barrel", "-barrel", "/chem", "-chem"),
    )
    is_nav_generic = has_any_token(main_path_lower, ("/home.md", "/site.md", "/author-", "all-press"))
    is_news_or_cocktail = has_any_token(main_path_lower, ("/news", "blogs-news", "/cocktails", "cocktails-", "/journal", "/blog"))

    product_signal = counts.get("product_names", 0) >= 1 or product_path_signal
    technical_signal = (
        counts.get("distillery_tool_names", 0) >= 1
        or counts.get("chemical_names", 0) >= 1
        or counts.get("glossary_terms", 0) >= 4
        or technical_path_signal
    )

    if product_signal and (abv_mentioned or price_mentioned or counts.get("product_names", 0) >= 2):
        return "product_catalog", {
            "abv_mentioned": abv_mentioned,
            "price_mentioned": price_mentioned,
            "regulatory_overlap": regulatory_overlap,
            "is_nav_generic": is_nav_generic,
            "is_news_or_cocktail": is_news_or_cocktail,
        }
    if technical_signal and not product_signal:
        return "technical_process", {
            "abv_mentioned": abv_mentioned,
            "price_mentioned": price_mentioned,
            "regulatory_overlap": regulatory_overlap,
            "is_nav_generic": is_nav_generic,
            "is_news_or_cocktail": is_news_or_cocktail,
        }
    if regulatory_overlap and not product_signal and not technical_signal:
        return "regulatory", {
            "abv_mentioned": abv_mentioned,
            "price_mentioned": price_mentioned,
            "regulatory_overlap": regulatory_overlap,
            "is_nav_generic": is_nav_generic,
            "is_news_or_cocktail": is_news_or_cocktail,
        }
    return "noisy", {
        "abv_mentioned": abv_mentioned,
        "price_mentioned": price_mentioned,
        "regulatory_overlap": regulatory_overlap,
        "is_nav_generic": is_nav_generic,
        "is_news_or_cocktail": is_news_or_cocktail,
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

    # Down-rank navigational/news/cocktail style pages to reduce false positives.
    if flags.get("is_nav_generic"):
        score -= 14
    if flags.get("is_news_or_cocktail") and bucket in {"technical_process", "noisy"}:
        score -= 10

    if score < 0:
        score = 0

    return round(score, 2)


def infer_phase_fit_tags(main_path: str, counts: dict[str, int], flags: dict[str, bool], bucket: str) -> list[str]:
    tags: list[str] = []
    low = main_path.lower()

    if flags.get("regulatory_overlap") or bucket == "regulatory" or has_any_token(low, ("excise", "duty", "tariff", "policy", "label", "regulation")):
        tags.extend(["history", "compliance"])
    if bucket == "product_catalog" and not flags.get("is_news_or_cocktail"):
        tags.extend(["region", "culture"])
    if counts.get("chemical_names", 0) >= 1 or counts.get("flavor_profile_words", 0) >= 3 or has_any_token(low, ("chem", "ester", "phenol", "sulfur", "ferment", "biochem")):
        tags.append("chemistry")
    if counts.get("distillery_tool_names", 0) >= 1 or counts.get("glossary_terms", 0) >= 8 or has_any_token(low, ("process", "distillation", "mash", "cask", "equipment", "cip")):
        tags.append("process")

    unique = sorted(set(tags))
    return unique


def build_records(crawl_markdown_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for metadata_path in sorted(crawl_markdown_dir.rglob("*-metadata.md")):
        metadata_text = metadata_path.read_text(encoding="utf-8", errors="replace")
        counts = parse_counts(metadata_text)

        main_path = metadata_path.with_name(metadata_path.name.replace("-metadata.md", ".md"))
        main_text = ""
        if main_path.exists():
            main_text = main_path.read_text(encoding="utf-8", errors="replace")

        metadata_stat = metadata_path.stat()
        main_mtime = 0.0
        main_size = 0
        if main_path.exists():
            main_stat = main_path.stat()
            main_mtime = float(main_stat.st_mtime)
            main_size = int(main_stat.st_size)

        signature_seed = {
            "main_path": str(main_path),
            "metadata_path": str(metadata_path),
            "metadata_mtime": float(metadata_stat.st_mtime),
            "metadata_size": int(metadata_stat.st_size),
            "main_mtime": main_mtime,
            "main_size": main_size,
            "counts": counts,
        }
        source_signature = hashlib.sha256(
            json.dumps(signature_seed, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()

        bucket, flags = compute_bucket(counts=counts, main_text=main_text, main_path=str(main_path))
        score = score_record(bucket=bucket, counts=counts, flags=flags)

        records.append(
            {
                "metadata_path": str(metadata_path),
                "main_path": str(main_path),
                "source_signature": source_signature,
                "main_mtime": main_mtime,
                "bucket": bucket,
                "score": score,
                "phase_fit_tags": infer_phase_fit_tags(str(main_path), counts, flags, bucket),
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
        "source_signature",
        "main_mtime",
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
        "is_nav_generic",
        "is_news_or_cocktail",
        "phase_fit_tags",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in records:
            csv_row = {k: row.get(k) for k in fields}
            tags = csv_row.get("phase_fit_tags")
            if isinstance(tags, list):
                csv_row["phase_fit_tags"] = "|".join(str(t) for t in tags)
            writer.writerow(csv_row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage crawled resource metadata into bucketed quality output.")
    parser.add_argument("--crawl-markdown", default="data/crawl_markdown", help="Root crawl markdown directory.")
    parser.add_argument("--json-out", default="data/resource_triage.json", help="JSON output path.")
    parser.add_argument("--csv-out", default="data/resource_triage.csv", help="CSV output path.")
    args = parser.parse_args()

    crawl_dir = Path(args.crawl_markdown)
    records = build_records(crawl_dir)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
