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
INLINE_PRICE_RE = re.compile(r"\$(\d+(?:\.\d{1,2})?)")
INLINE_ABV_RE = re.compile(r"\b(\d{1,2}(?:\.\d)?)\s*%\s*(?:abv)?\b", re.IGNORECASE)
MAX_SLUG_LEN = 96


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def bounded_slug(value: str, *, max_len: int = MAX_SLUG_LEN) -> str:
    base = slugify(value or "") or "product"
    if len(base) <= max_len:
        return base

    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    keep = max(1, max_len - 9)
    trimmed = base[:keep].rstrip("-")
    return f"{trimmed}-{digest}"


def first_match(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def infer_type(text: str) -> str:
    lowered = (text or "").lower()
    for token, mapped in [
        ("whisky", "whisky"),
        ("whiskey", "whiskey"),
        ("gin", "gin"),
        ("vodka", "vodka"),
        ("rum", "rum"),
        ("brandy", "brandy"),
        ("liqueur", "liqueur"),
    ]:
        if token in lowered:
            return mapped
    return ""


def section_items(text: str, title: str) -> list[str]:
    lines = text.splitlines()
    items: list[str] = []
    in_section = False
    wanted = title.strip().lower()
    for raw in lines:
        line = raw.strip()
        if line.startswith("## "):
            in_section = line[3:].strip().lower() == wanted
            continue
        if in_section and line.startswith("- "):
            item = line[2:].strip()
            if item:
                items.append(item)
    return items


def extract_product(main_text: str, source_url: str) -> dict[str, Any]:
    title = first_match(HEADING_RE, main_text)
    distillery = first_match(DIST_RE, main_text)
    abv = first_match(ABV_RE, main_text)
    price = first_match(PRICE_RE, main_text)
    ptype = first_match(TYPE_RE, main_text)
    score = first_match(SCORE_RE, main_text)

    if not price:
        inline_price = INLINE_PRICE_RE.search(main_text)
        if inline_price:
            price = f"${inline_price.group(1)}"

    if not abv:
        inline_abv = INLINE_ABV_RE.search(main_text)
        if inline_abv:
            abv = f"{inline_abv.group(1)}%"

    if not ptype:
        ptype = infer_type(title or main_text[:300])

    links = [u for u in BUY_LINK_RE.findall(main_text) if any(k in u.lower() for k in ["shop", "buy", "product", "store"])]
    purchase_link = links[0] if links else ""
    if not purchase_link and source_url and any(k in source_url.lower() for k in ["shop", "product", "store", "collections"]):
        purchase_link = source_url

    if not distillery and source_url:
        host = source_url.split("//", 1)[-1].split("/", 1)[0].lower()
        if host.startswith("www."):
            host = host[4:]
        name = host.split(".")[0].replace("-", " ").strip()
        if name:
            distillery = name.title()

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


def is_blog_like_source(source_url: str, main_path: Path, title: str) -> bool:
    low_url = (source_url or "").lower()
    low_path = str(main_path).lower()
    low_title = (title or "").lower()
    return any(token in low_url or token in low_path or token in low_title for token in ["/blog", "-blog", "news", "journal", "story", "article"])


def confidence_ok(product: dict[str, Any]) -> bool:
    if not product.get("name"):
        return False
    checks = 0
    if product.get("distillery"):
        checks += 1
    if product.get("abv") or product.get("type"):
        checks += 1
    if product.get("price") or product.get("purchase_link"):
        checks += 1
    return checks >= 1


def existing_slug_set(products_dir: Path) -> set[str]:
    return {p.stem for p in products_dir.glob("*.md") if p.is_file()}


def write_product_md(products_dir: Path, product: dict[str, Any], image_hash: str, slug: str) -> Path:
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


def load_progress_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_progress_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product markdown records from triage output.")
    parser.add_argument("--triage-json", default="data/resource_triage.json", help="Triage JSON path.")
    parser.add_argument("--products-dir", default="data/products", help="Product markdown output dir.")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on products written.")
    parser.add_argument(
        "--only-sources-json",
        default="",
        help="Optional JSON array file of source main_path values to allow (incremental mode).",
    )
    parser.add_argument(
        "--progress-state",
        default="data/content_progress_state.json",
        help="Progress state file used to avoid source reuse across runs.",
    )
    parser.add_argument(
        "--ignore-used-sources",
        action="store_true",
        help="Ignore used_product_sources gating for this run (useful for full-redigest/backfills).",
    )
    args = parser.parse_args()

    triage = json.loads(Path(args.triage_json).read_text(encoding="utf-8"))
    records = triage.get("records", []) if isinstance(triage, dict) else []

    allowed_sources: set[str] | None = None
    if args.only_sources_json:
        raw = json.loads(Path(args.only_sources_json).read_text(encoding="utf-8"))
        if isinstance(raw, list):
            allowed_sources = {str(x) for x in raw if str(x).strip()}

    progress_path = Path(args.progress_state)
    progress = load_progress_state(progress_path)
    used_product_sources = {
        str(x)
        for x in progress.get("used_product_sources", [])
        if isinstance(x, str) and x.strip()
    }
    if args.ignore_used_sources:
        used_product_sources = set()

    products_dir = Path(args.products_dir)
    products_dir.mkdir(parents=True, exist_ok=True)
    existing = existing_slug_set(products_dir)
    existing_keys: set[str] = set()
    existing_image_hashes: set[str] = set()

    written = 0
    skipped = 0
    skipped_reused = 0
    skipped_out_of_scope = 0
    consumed_sources: list[str] = []
    for row in records:
        if not isinstance(row, dict) or row.get("bucket") != "product_catalog":
            continue
        main_path = Path(str(row.get("main_path") or ""))
        main_path_str = str(main_path)
        if allowed_sources is not None and main_path_str not in allowed_sources:
            skipped_out_of_scope += 1
            continue
        if main_path_str in used_product_sources:
            skipped_reused += 1
            continue
        if not main_path.exists():
            skipped += 1
            continue
        text = main_path.read_text(encoding="utf-8", errors="replace")
        url_match = re.search(r"-\s*URL:\s*(https?://\S+)", text)
        source_url = url_match.group(1) if url_match else ""

        product = extract_product(main_text=text, source_url=source_url)

        metadata_path = Path(str(row.get("metadata_path") or ""))
        metadata_text = metadata_path.read_text(encoding="utf-8", errors="replace") if metadata_path.exists() else ""
        metadata_product_names = section_items(metadata_text, "Product Names")

        # Some high-value pages are article-style sources that contain multiple footer products.
        # In that case, emit one product record per metadata product name.
        candidates: list[dict[str, Any]] = []
        if metadata_product_names and is_blog_like_source(source_url, main_path, product.get("name") or ""):
            for pname in metadata_product_names:
                candidate = dict(product)
                candidate["name"] = pname
                if not candidate.get("type"):
                    candidate["type"] = infer_type(pname)
                if not candidate.get("purchase_link"):
                    candidate["purchase_link"] = source_url
                candidates.append(candidate)
        else:
            candidates.append(product)
        source_emitted = False
        for candidate in candidates:
            if not confidence_ok(candidate):
                skipped += 1
                continue

            slug = bounded_slug(candidate.get("name") or "product")
            key = f"{(candidate.get('name') or '').strip().lower()}::{(candidate.get('distillery') or '').strip().lower()}"
            image_hash = hashlib.sha256((candidate.get("source_image") or "").encode("utf-8")).hexdigest()

            if slug in existing or key in existing_keys or (candidate.get("source_image") and image_hash in existing_image_hashes):
                skipped += 1
                continue

            write_product_md(products_dir=products_dir, product=candidate, image_hash=image_hash, slug=slug)
            existing.add(slug)
            existing_keys.add(key)
            if candidate.get("source_image"):
                existing_image_hashes.add(image_hash)
            written += 1
            source_emitted = True

            if args.limit > 0 and written >= args.limit:
                break

        if source_emitted:
            consumed_sources.append(main_path_str)

        if args.limit > 0 and written >= args.limit:
            break

    if consumed_sources:
        used_product_sources.update(consumed_sources)
        progress["used_product_sources"] = sorted(used_product_sources)
        progress["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_progress_state(progress_path, progress)

    print(
        json.dumps(
            {
                "written": written,
                "skipped": skipped,
                "skipped_reused": skipped_reused,
                "skipped_out_of_scope": skipped_out_of_scope,
                "consumed_sources": len(consumed_sources),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
