#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRICE_RE = re.compile(r"(?:\*\*)?Price(?:\*\*)?\s*:\s*(.+)", re.IGNORECASE)
ABV_RE = re.compile(r"(?:\*\*)?ABV(?:\*\*)?\s*:\s*(.+)", re.IGNORECASE)
TYPE_RE = re.compile(r"(?:\*\*)?Type(?:\*\*)?\s*:\s*(.+)", re.IGNORECASE)
DIST_RE = re.compile(r"(?:\*\*)?Distillery(?:\*\*)?\s*:\s*(.+)", re.IGNORECASE)
SCORE_RE = re.compile(r"(?:\*\*)?Score(?:\*\*)?\s*:\s*(.+)", re.IGNORECASE)
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
BUY_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)", re.IGNORECASE)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def first_match(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def extract_product(main_text: str, source_url: str) -> dict[str, Any]:
    title = first_match(HEADING_RE, main_text)
    distillery = first_match(DIST_RE, main_text)
    abv = first_match(ABV_RE, main_text)
    price = first_match(PRICE_RE, main_text)
    ptype = first_match(TYPE_RE, main_text)
    score = first_match(SCORE_RE, main_text)

    links = [u for u in BUY_LINK_RE.findall(main_text) if any(k in u.lower() for k in ["shop", "buy", "product", "store"])]
    purchase_link = links[0] if links else ""

    img = ""
    for raw in IMAGE_RE.findall(main_text):
        if raw.startswith("http://") or raw.startswith("https://"):
            img = raw
            break

    return {
        "name": title,
        "distillery": distillery,
        "abv": abv,
        "price": price,
        "type": ptype,
        "score": score,
        "source_url": source_url,
        "purchase_link": purchase_link,
        "source_image": img,
    }


def confidence_ok(product: dict[str, Any]) -> bool:
    checks = 0
    if product.get("name"):
        checks += 1
    if product.get("distillery"):
        checks += 1
    if product.get("abv") or product.get("type"):
        checks += 1
    return checks >= 2


def existing_slug_set(products_dir: Path) -> set[str]:
    return {p.stem for p in products_dir.glob("*.md") if p.is_file()}


def write_product_md(products_dir: Path, product: dict[str, Any], image_hash: str) -> Path:
    slug = slugify(product.get("name") or "product")
    out = products_dir / f"{slug}.md"
    title = product.get("name") or slug.replace("-", " ").title()
    distillery = product.get("distillery") or ""
    category = product.get("type") or ""
    lines = [
        "---",
        f"title: {json.dumps(title)}",
        f"slug: {json.dumps(slug)}",
        f"distillery: {json.dumps(distillery)}",
        f"abv: {json.dumps(product.get('abv') or '')}",
        f"price: {json.dumps(product.get('price') or '')}",
        f"category: {json.dumps(category)}",
        f"source_url: {json.dumps(product.get('source_url') or '')}",
        f"purchase_link: {json.dumps(product.get('purchase_link') or '')}",
        f"source_image: {json.dumps(product.get('source_image') or '')}",
        f"source_image_hash: {json.dumps(image_hash)}",
        f"confidence: {json.dumps('medium')}",
        f"captured_at: {json.dumps(datetime.now(timezone.utc).isoformat())}",
        "available: true",
        "---",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product markdown records from triage output.")
    parser.add_argument("--triage-json", default="data/resource_triage.json", help="Triage JSON path.")
    parser.add_argument("--products-dir", default="data/products", help="Product markdown output dir.")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on products written.")
    args = parser.parse_args()

    triage = json.loads(Path(args.triage_json).read_text(encoding="utf-8"))
    records = triage.get("records", []) if isinstance(triage, dict) else []

    products_dir = Path(args.products_dir)
    products_dir.mkdir(parents=True, exist_ok=True)
    existing = existing_slug_set(products_dir)
    existing_keys: set[str] = set()
    existing_image_hashes: set[str] = set()

    written = 0
    skipped = 0
    for row in records:
        if not isinstance(row, dict) or row.get("bucket") != "product_catalog":
            continue
        main_path = Path(str(row.get("main_path") or ""))
        if not main_path.exists():
            skipped += 1
            continue
        text = main_path.read_text(encoding="utf-8", errors="replace")
        url_match = re.search(r"-\s*URL:\s*(https?://\S+)", text)
        source_url = url_match.group(1) if url_match else ""

        product = extract_product(main_text=text, source_url=source_url)
        if not confidence_ok(product):
            skipped += 1
            continue

        slug = slugify(product.get("name") or "product")
        key = f"{(product.get('name') or '').strip().lower()}::{(product.get('distillery') or '').strip().lower()}"
        image_hash = hashlib.sha256((product.get("source_image") or "").encode("utf-8")).hexdigest()

        if slug in existing or key in existing_keys or (product.get("source_image") and image_hash in existing_image_hashes):
            skipped += 1
            continue

        write_product_md(products_dir=products_dir, product=product, image_hash=image_hash)
        existing.add(slug)
        existing_keys.add(key)
        if product.get("source_image"):
            existing_image_hashes.add(image_hash)
        written += 1

        if args.limit > 0 and written >= args.limit:
            break

    print(json.dumps({"written": written, "skipped": skipped}, ensure_ascii=True))


if __name__ == "__main__":
    main()
