#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import importlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any
from io import BytesIO
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class SiteTarget:
    site_type: str
    name: str
    url: str
    podcast_rss: str = ""


@dataclass
class PagePayload:
    requested_url: str
    depth: int
    current_url: str
    title: str
    content: str
    content_kind: str
    fetch_mode: str


@dataclass
class PreparedPage:
    requested_url: str
    current_url: str
    depth: int
    page_title: str
    description: str
    combined_text: str
    content_hash: str
    audio_urls: list[str]
    transcript_keywords: list[str]
    audio_items: list[dict[str, str]]
    unique_links: list[str]
    existing: sqlite3.Row | None
    fetch_mode: str


class ContentCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.audio_sources: list[str] = []
        self.title_parts: list[str] = []
        self.description = ""
        self._skip_depth = 0
        self._in_title = False
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

        if tag == "a":
            href = attr_map.get("href", "").strip()
            if href:
                self.links.append(href)

        if tag == "audio":
            src = attr_map.get("src", "").strip()
            if src:
                self.audio_sources.append(src)

        if tag == "source":
            src = attr_map.get("src", "").strip()
            source_type = attr_map.get("type", "").strip().lower()
            if src and source_type.startswith("audio/"):
                self.audio_sources.append(src)

        if tag == "iframe":
            src = attr_map.get("src", "").strip()
            if src and _is_podcast_iframe_src(src):
                self.audio_sources.append(src)

        if tag == "meta":
            key = (attr_map.get("name", "") or attr_map.get("property", "")).lower()
            if key in {"description", "og:description"} and not self.description:
                self.description = attr_map.get("content", "").strip()

        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._skip_depth == 0:
            self.text_parts.append(text)

    @property
    def title(self) -> str:
        return normalize_ws(" ".join(self.title_parts))

    @property
    def visible_text(self) -> str:
        return normalize_ws(" ".join(self.text_parts))


def normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_type TEXT NOT NULL,
            name TEXT NOT NULL,
            root_url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_crawled_at TEXT,
            last_status TEXT,
            UNIQUE(site_type, root_url)
        );

        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            description TEXT,
            text_content TEXT,
            content_hash TEXT,
            extracted_links_json TEXT,
            summary_markdown TEXT,
            summary_json TEXT,
            extracted_products_json TEXT,
            extracted_reviews_json TEXT,
            keyword_sets_json TEXT,
            blog_topics_json TEXT,
            course_topics_json TEXT,
            db_enrichment_json TEXT,
            llm_model TEXT,
            keywords_json TEXT,
            crawl_status TEXT,
            last_crawled_at TEXT,
            crawl_count INTEGER NOT NULL DEFAULT 0,
            html_path TEXT,
            markdown_path TEXT,
            UNIQUE(site_id, url),
            FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS keyword_index (
            keyword TEXT NOT NULL,
            site_id INTEGER NOT NULL,
            page_url TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (keyword, site_id, page_url),
            FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_pages_site ON pages(site_id);
        CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash);
        CREATE INDEX IF NOT EXISTS idx_keyword_keyword ON keyword_index(keyword);
        """
    )

    existing_cols = {
        str(row[1]).lower()
        for row in conn.execute("PRAGMA table_info(pages)").fetchall()
    }
    additions: list[tuple[str, str]] = []
    if "summary_json" not in existing_cols:
        additions.append(("summary_json", "TEXT"))
    if "extracted_products_json" not in existing_cols:
        additions.append(("extracted_products_json", "TEXT"))
    if "extracted_reviews_json" not in existing_cols:
        additions.append(("extracted_reviews_json", "TEXT"))
    if "keyword_sets_json" not in existing_cols:
        additions.append(("keyword_sets_json", "TEXT"))
    if "blog_topics_json" not in existing_cols:
        additions.append(("blog_topics_json", "TEXT"))
    if "course_topics_json" not in existing_cols:
        additions.append(("course_topics_json", "TEXT"))
    if "db_enrichment_json" not in existing_cols:
        additions.append(("db_enrichment_json", "TEXT"))
    if "is_content_excluded" not in existing_cols:
        additions.append(("is_content_excluded", "INTEGER DEFAULT 0"))

    for col, typ in additions:
        conn.execute(f"ALTER TABLE pages ADD COLUMN {col} {typ}")

    conn.commit()


def connect_state_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def load_distillery_targets(db_path: Path) -> list[SiteTarget]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT name, official_site
            FROM distilleries
            WHERE official_site LIKE 'http%'
            ORDER BY country, region, name
            """
        ).fetchall()
        return [SiteTarget(site_type="distillery", name=str(r["name"]), url=str(r["official_site"])) for r in rows]
    finally:
        conn.close()


def load_resource_targets(db_path: Path, seed_path: Path) -> list[SiteTarget]:
    # Always build a url->podcast_rss lookup from the seed so DB-loaded targets still
    # get the podcast_rss value even though the resources DB has no such column.
    podcast_rss_by_url: dict[str, str] = {}
    if seed_path.exists():
        try:
            _seed = json.loads(seed_path.read_text(encoding="utf-8"))
            for _entry in _seed.get("resources", []):
                _url = str(_entry.get("url", "")).strip().rstrip("/")
                _rss = str(_entry.get("podcast_rss", "")).strip()
                if _url and _rss:
                    podcast_rss_by_url[_url] = _rss
        except Exception:
            pass

    targets: list[SiteTarget] = []
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT name, url
                FROM resources
                WHERE url LIKE 'http%'
                ORDER BY category, name
                """
            ).fetchall()
            targets.extend([
                SiteTarget(
                    site_type="resource",
                    name=str(r["name"]),
                    url=str(r["url"]),
                    podcast_rss=podcast_rss_by_url.get(str(r["url"]).rstrip("/"), ""),
                )
                for r in rows
            ])
        finally:
            conn.close()

    if not targets and seed_path.exists():
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        for entry in payload.get("resources", []):
            url = str(entry.get("url", "")).strip()
            name = str(entry.get("name", "")).strip()
            podcast_rss = str(entry.get("podcast_rss", "")).strip()
            if url.startswith("http") and name:
                targets.append(SiteTarget(site_type="resource", name=name, url=url, podcast_rss=podcast_rss))

    return targets


def dedupe_targets(targets: list[SiteTarget]) -> list[SiteTarget]:
    out: list[SiteTarget] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        parsed = urlparse(target.url)
        normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path or '/'}"
        key = (target.site_type, normalized.rstrip("/"))
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def lmstudio_summarize(base_url: str, model: str, name: str, url: str, page_title: str, text: str) -> tuple[str, list[str]]:
    trimmed = text[:12000]
    prompt = (
        "You are summarizing whisky research content from a website page. "
        "Return strict JSON with keys summary_markdown and keywords. "
        "summary_markdown should preserve the page's substance and structure using concise markdown headings and bullets that fit the actual content; do not force a fixed template. "
        "If useful, you may include distillery-relevant sections such as Key Facts, Production Signals, Commercial Signals, and Risks/Unknowns, but only when they genuinely match the source material. "
        "Do not omit important source details just to fit pre-defined headings. "
        "keywords should be an array of 8 to 20 lower-case topical phrases focused on whisky, distilling, regulation, history, production, maturation, sensory, and brand positioning."
    )

    user_payload = {
        "site_name": name,
        "site_url": url,
        "page_title": page_title,
        "page_text": trimmed,
    }

    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ],
    }

    req = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read().decode("utf-8", errors="replace"))

    content = raw["choices"][0]["message"]["content"]
    parsed = try_parse_json_block(content)
    summary_md = str(parsed.get("summary_markdown", "")).strip()
    keywords = [
        normalize_ws(str(k).lower())
        for k in ((parsed.get("keywords") if isinstance(parsed, dict) else None) or [])
        if isinstance(k, str) and normalize_ws(k)
    ]
    if not summary_md:
        raise ValueError("LM Studio response missing summary_markdown")
    if not keywords:
        keywords = fallback_keywords(text)
    return summary_md, sorted(set(keywords))


def _safe_json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return default


def _to_markdown_list(items: list[str], prefix: str = "- ") -> list[str]:
    out: list[str] = []
    for item in items:
        cleaned = normalize_ws(item)
        if cleaned:
            out.append(f"{prefix}{cleaned}")
    return out


def _flatten_keyword_sets(keyword_sets: dict[str, Any]) -> list[str]:
    flattened: list[str] = []
    for key in [
        "flavour_descriptions",
        "glossary_terms",
        "production_terms",
        "chemistry_terms_observations",
    ]:
        flattened.extend(_coerce_string_list(keyword_sets.get(key, []), limit=80))
    return sorted(set(flattened))


def _extract_price_mentions(text: str) -> list[str]:
    matches = re.findall(r"(?:\$|AUD\s*\$?)\s?\d{1,4}(?:[\.,]\d{2})?", text)
    return sorted(set(normalize_ws(m) for m in matches))[:30]


def _fallback_structured_summary(
    site_name: str,
    site_url: str,
    page_title: str,
    page_url: str,
    text: str,
    page_links: list[str],
) -> dict[str, Any]:
    base_keywords = fallback_keywords(text)
    product_like_links = [
        link for link in page_links
        if any(token in link.lower() for token in ["product", "products", "shop", "store", "buy", "checkout", "cart"])
    ][:20]
    price_mentions = _extract_price_mentions(text)

    keyword_sets = {
        "flavour_descriptions": [k for k in base_keywords if any(t in k for t in ["flavor", "flavour", "vanilla", "oak", "spice", "fruit", "peat", "smoke", "nose", "palate"])],
        "glossary_terms": [k for k in base_keywords if any(t in k for t in ["abv", "proof", "single malt", "bourbon", "rye", "cask", "mash bill", "finish"])],
        "production_terms": [k for k in base_keywords if any(t in k for t in ["distill", "ferment", "mash", "barrel", "cask", "warehouse", "maturation"])],
        "chemistry_terms_observations": [k for k in base_keywords if any(t in k for t in ["ester", "phenol", "lactone", "tannin", "congener", "sulfur", "abv"])],
    }

    products: list[dict[str, Any]] = []
    if product_like_links or price_mentions:
        products.append(
            {
                "name": page_title or "possible product listing",
                "facts": [],
                "price_mentions": price_mentions,
                "purchase_links": product_like_links,
                "source_url": page_url,
                "confidence": "low",
            }
        )

    snippet = normalize_ws(text)[:1400]
    summary_markdown = "\n".join(
        [
            "## Page Summary",
            f"- Source: {site_name}",
            f"- URL: {page_url}",
            f"- Summary snippet: {snippet}",
            "",
            "## Metadata Highlights",
            f"- Product records detected: {len(products)}",
            f"- Purchase-like links detected: {len(product_like_links)}",
            f"- Price mentions detected: {len(price_mentions)}",
        ]
    ).strip()

    return {
        "summary_markdown": summary_markdown,
        "summary_text": snippet,
        "distillery_facts": [],
        "resource_facts": [],
        "product_facts": products,
        "reviews": [],
        "keyword_sets": keyword_sets,
        "legacy_sections": {
            "key_facts": [],
            "production_signals": [],
            "commercial_signals": [],
            "risks_unknowns": [],
        },
        "db_enrichment_candidates": {
            "distilleries": [],
            "resources": [],
            "products": products,
        },
        "blog_topic_suggestions": [],
        "course_material_candidates": [],
        "keywords": sorted(set(base_keywords + _flatten_keyword_sets(keyword_sets))),
    }


def _normalize_product_records(raw_products: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_products, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw_products[:80]:
        if not isinstance(item, dict):
            continue
        name = normalize_ws(str(item.get("name", "")))
        raw_purchase_links = item.get("purchase_links")
        raw_price_mentions = item.get("price_mentions")
        raw_facts = item.get("facts")
        purchase_links = [
            str(link).strip() for link in (raw_purchase_links if isinstance(raw_purchase_links, list) else [])
            if isinstance(link, str) and str(link).startswith(("http://", "https://"))
        ][:20]
        price_mentions = [
            normalize_ws(str(p)) for p in (raw_price_mentions if isinstance(raw_price_mentions, list) else []) if isinstance(p, str)
        ][:20]
        facts = [normalize_ws(str(f)) for f in (raw_facts if isinstance(raw_facts, list) else []) if isinstance(f, str)][:25]
        if not (name or purchase_links or facts or price_mentions):
            continue
        out.append(
            {
                "name": name,
                "facts": facts,
                "price_mentions": price_mentions,
                "purchase_links": purchase_links,
                "source_url": normalize_ws(str(item.get("source_url", ""))),
                "confidence": normalize_ws(str(item.get("confidence", ""))) or "medium",
            }
        )
    return out


def _normalize_review_records(raw_reviews: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_reviews, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw_reviews[:120]:
        if not isinstance(item, dict):
            continue
        review_text = str(item.get("review_text", "")).strip()
        if not review_text:
            continue
        out.append(
            {
                "review_text": review_text,
                "reviewer": normalize_ws(str(item.get("reviewer", ""))),
                "rating": normalize_ws(str(item.get("rating", ""))),
                "review_date": normalize_ws(str(item.get("review_date", ""))),
                "product_name": normalize_ws(str(item.get("product_name", ""))),
                "product_url": normalize_ws(str(item.get("product_url", ""))),
                "source_url": normalize_ws(str(item.get("source_url", ""))),
                "confidence": normalize_ws(str(item.get("confidence", ""))) or "medium",
            }
        )
    return out


def lmstudio_screen_page_relevance(
    base_url: str,
    model: str,
    site_name: str,
    page_url: str,
    page_title: str,
    text: str,
    timeout_seconds: int = 180,
) -> bool:
    """Quick screening to check if page contains whisky-relevant content.
    Uses granite model with short timeout for fast filtering.
    Returns True if page should be processed, False if it should be excluded.
    """
    trimmed_text = text[:8000]
    prompt = (
        "You are screening web page content for whisky relevance. "
        "Return strict JSON with a single key 'is_relevant' (boolean). "
        "Mark as True only if page contains actual whisky product information, "
        "distillery details, production processes, tasting notes, reviews, or educational content about whisky/spirits. "
        "Mark as False if page is: login forms, member benefits, account settings, navigation pages, "
        "legal/privacy, general company info without whisky specifics, or membership signup. "
        "Be strict: exclude pages that are primarily administrative or not directly about whisky."
    )

    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "site_name": site_name,
                        "page_url": page_url,
                        "page_title": page_title,
                        "page_text": trimmed_text,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
    }

    req = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        content = raw["choices"][0]["message"]["content"]
        parsed = try_parse_json_block(content)
        return bool(parsed.get("is_relevant", False))
    except Exception:
        # On screening error (network, timeout, etc.), assume content is relevant to avoid false exclusions
        return True


def lmstudio_extract_page_structured(
    base_url: str,
    model: str,
    site_name: str,
    site_type: str,
    site_url: str,
    page_url: str,
    page_title: str,
    text: str,
    page_links: list[str],
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    trimmed_text = text[:22000]
    prompt = (
        "You are extracting and summarizing whisky page content for downstream databases. "
        "Return strict JSON only. Do not force a fixed heading template. "
        "Capture what the page actually contains. "
        "Required keys: summary_markdown, summary_text, distillery_facts, resource_facts, product_facts, reviews, keyword_sets, legacy_sections, db_enrichment_candidates, blog_topic_suggestions, course_material_candidates, keywords. "
        "summary_markdown: concise faithful markdown summary focused on source substance, not metadata schema. "
        "distillery_facts/resource_facts: arrays of concrete factual statements useful for database updates. "
        "product_facts: array of objects with keys name, facts, price_mentions, purchase_links, source_url, confidence. Include pricing and purchase links whenever present. "
        "reviews: array of full review objects with keys review_text, reviewer, rating, review_date, product_name, product_url, source_url, confidence. Preserve full review text. "
        "keyword_sets must contain arrays: flavour_descriptions, glossary_terms, production_terms, chemistry_terms_observations. "
        "legacy_sections must contain arrays: key_facts, production_signals, commercial_signals, risks_unknowns, but keep them optional/empty when not present. "
        "db_enrichment_candidates must contain objects/arrays for distilleries, resources, products. "
        "blog_topic_suggestions and course_material_candidates should be concise evidence-driven suggestions. "
        "keywords should be 12-80 lower-case phrases covering product, process, flavour, regulation, and chemistry where present."
    )

    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "site_name": site_name,
                        "site_type": site_type,
                        "site_url": site_url,
                        "page_url": page_url,
                        "page_title": page_title,
                        "page_links": (page_links or [])[:80],
                        "page_text": trimmed_text,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
    }

    req = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = json.loads(resp.read().decode("utf-8", errors="replace"))

    content = raw["choices"][0]["message"]["content"]
    parsed = try_parse_json_block(content)

    summary_markdown = str(parsed.get("summary_markdown", "")).strip()
    summary_text = str(parsed.get("summary_text", "")).strip()
    distillery_facts = _coerce_string_list(parsed.get("distillery_facts", []), limit=120)
    resource_facts = _coerce_string_list(parsed.get("resource_facts", []), limit=120)
    product_facts = _normalize_product_records(parsed.get("product_facts", []))
    reviews = _normalize_review_records(parsed.get("reviews", []))

    raw_keyword_sets_val = parsed.get("keyword_sets")
    raw_keyword_sets = raw_keyword_sets_val if isinstance(raw_keyword_sets_val, dict) else {}
    keyword_sets = {
        "flavour_descriptions": _coerce_string_list(raw_keyword_sets.get("flavour_descriptions", []), limit=120),
        "glossary_terms": _coerce_string_list(raw_keyword_sets.get("glossary_terms", []), limit=120),
        "production_terms": _coerce_string_list(raw_keyword_sets.get("production_terms", []), limit=120),
        "chemistry_terms_observations": _coerce_string_list(raw_keyword_sets.get("chemistry_terms_observations", []), limit=120),
    }

    raw_legacy_val = parsed.get("legacy_sections")
    raw_legacy = raw_legacy_val if isinstance(raw_legacy_val, dict) else {}
    legacy_sections = {
        "key_facts": _coerce_string_list(raw_legacy.get("key_facts", []), limit=80),
        "production_signals": _coerce_string_list(raw_legacy.get("production_signals", []), limit=80),
        "commercial_signals": _coerce_string_list(raw_legacy.get("commercial_signals", []), limit=80),
        "risks_unknowns": _coerce_string_list(raw_legacy.get("risks_unknowns", []), limit=80),
    }

    db_enrichment = parsed.get("db_enrichment_candidates")
    if not isinstance(db_enrichment, dict):
        db_enrichment = {
            "distilleries": distillery_facts,
            "resources": resource_facts,
            "products": product_facts,
        }

    blog_topics = _coerce_string_list(parsed.get("blog_topic_suggestions", []), limit=60)
    course_topics = _coerce_string_list(parsed.get("course_material_candidates", []), limit=60)
    keywords = _coerce_string_list(parsed.get("keywords", []), limit=160)
    if not keywords:
        keywords = sorted(set(fallback_keywords(text) + _flatten_keyword_sets(keyword_sets)))[:120]

    if not summary_markdown:
        raise ValueError("LM response missing summary_markdown")

    return {
        "summary_markdown": summary_markdown,
        "summary_text": summary_text,
        "distillery_facts": distillery_facts,
        "resource_facts": resource_facts,
        "product_facts": product_facts,
        "reviews": reviews,
        "keyword_sets": keyword_sets,
        "legacy_sections": legacy_sections,
        "db_enrichment_candidates": db_enrichment,
        "blog_topic_suggestions": blog_topics,
        "course_material_candidates": course_topics,
        "keywords": sorted(set(keywords)),
    }


def _clean_markdown_for_prompt(value: str, max_chars: int = 1600) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:max_chars]


def _coerce_string_list(value: Any, limit: int = 30) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        token = normalize_ws(item.lower())
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= limit:
            break
    return out


def lmstudio_summarize_distillery_site(
    base_url: str,
    model: str,
    distillery_name: str,
    distillery_url: str,
    page_payloads: list[dict[str, Any]],
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    prompt = (
        "You synthesize whole-site distillery research for a searchable whisky database. "
        "Return strict JSON with keys: description, key_focus, source_headers, notes, search_terms, metadata. "
        "description must be concise, factual, and non-redundant; do not repeat details that are already captured in metadata fields. "
        "key_focus should be 3 to 8 compact comma-separated focus phrases suitable for a table field. "
        "source_headers should be a compact comma-separated list of dominant source themes. "
        "notes should be concise operational context that avoids repeating metadata. "
        "search_terms must be 12 to 40 lower-case topical phrases for search matching. "
        "metadata must be an object with these keys: "
        "product_lines, whisky_styles, grain_mentions, still_mentions, cask_mentions, maturation_mentions, "
        "visitor_experiences, commerce_features, compliance_signals, location_markers, claimed_founders_or_dates, "
        "age_gate_present, ecommerce_present, tours_or_bookings_present, awards_or_press_present. "
        "List values should be lower-case phrase arrays; booleans should be true/false."
    )

    trimmed_pages: list[dict[str, Any]] = []
    approx_chars = 0
    for page in page_payloads:
        page_summary = _clean_markdown_for_prompt(str(page.get("summary_markdown", "")), max_chars=1800)
        entry = {
            "url": str(page.get("url", "")),
            "title": str(page.get("title", "")),
            "description": str(page.get("description", ""))[:300],
            "keywords": _coerce_string_list(page.get("keywords", []), limit=20),
            "keyword_sets": page.get("keyword_sets", {}),
            "products": page.get("products", [])[:20],
            "reviews": page.get("reviews", [])[:20],
            "blog_topics": _coerce_string_list(page.get("blog_topics", []), limit=20),
            "course_topics": _coerce_string_list(page.get("course_topics", []), limit=20),
            "db_enrichment_candidates": page.get("db_enrichment_candidates", {}),
            "summary_markdown": page_summary,
        }
        entry_size = len(json.dumps(entry, ensure_ascii=True))
        if trimmed_pages and (approx_chars + entry_size) > 48000:
            break
        trimmed_pages.append(entry)
        approx_chars += entry_size

    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "distillery_name": distillery_name,
                        "distillery_url": distillery_url,
                        "page_count": len(page_payloads),
                        "pages": trimmed_pages,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
    }

    req = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = json.loads(resp.read().decode("utf-8", errors="replace"))

    content = raw["choices"][0]["message"]["content"]
    parsed = try_parse_json_block(content)

    raw_metadata = parsed.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    clean_metadata = {
        "product_lines": _coerce_string_list(metadata.get("product_lines", [])),
        "whisky_styles": _coerce_string_list(metadata.get("whisky_styles", [])),
        "grain_mentions": _coerce_string_list(metadata.get("grain_mentions", [])),
        "still_mentions": _coerce_string_list(metadata.get("still_mentions", [])),
        "cask_mentions": _coerce_string_list(metadata.get("cask_mentions", [])),
        "maturation_mentions": _coerce_string_list(metadata.get("maturation_mentions", [])),
        "visitor_experiences": _coerce_string_list(metadata.get("visitor_experiences", [])),
        "commerce_features": _coerce_string_list(metadata.get("commerce_features", [])),
        "compliance_signals": _coerce_string_list(metadata.get("compliance_signals", [])),
        "location_markers": _coerce_string_list(metadata.get("location_markers", [])),
        "claimed_founders_or_dates": _coerce_string_list(metadata.get("claimed_founders_or_dates", [])),
        "age_gate_present": bool(metadata.get("age_gate_present", False)),
        "ecommerce_present": bool(metadata.get("ecommerce_present", False)),
        "tours_or_bookings_present": bool(metadata.get("tours_or_bookings_present", False)),
        "awards_or_press_present": bool(metadata.get("awards_or_press_present", False)),
    }

    search_terms = _coerce_string_list(parsed.get("search_terms", []), limit=40)
    if not search_terms:
        aggregate = []
        for page in page_payloads:
            aggregate.extend(_coerce_string_list(page.get("keywords", []), limit=20))
        search_terms = sorted(set(aggregate))[:40]

    description = normalize_ws(str(parsed.get("description", "")))
    if not description:
        top_titles = [str(p.get("title", "")).strip() for p in page_payloads if str(p.get("title", "")).strip()]
        description = (
            f"{distillery_name} crawl synthesis from {len(page_payloads)} pages. "
            f"Primary site themes include: {', '.join(top_titles[:4])}."
        )

    key_focus = normalize_ws(str(parsed.get("key_focus", "")))
    if not key_focus:
        key_focus = ", ".join(search_terms[:6])

    source_headers = normalize_ws(str(parsed.get("source_headers", "")))
    if not source_headers:
        source_headers = ", ".join([
            "products",
            "production",
            "visitor experience",
            "brand positioning",
        ])

    notes = normalize_ws(str(parsed.get("notes", "")))
    if not notes:
        notes = "Synthesized from crawled site pages and LM Studio analysis."

    return {
        "description": description,
        "key_focus": key_focus,
        "source_headers": source_headers,
        "notes": notes,
        "search_terms": search_terms,
        "metadata": clean_metadata,
    }


def try_parse_json_block(value: str) -> dict[str, Any]:
    value = value.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        value = "\n".join(lines).strip()

    return json.loads(value)


def fallback_keywords(text: str) -> list[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "from",
        "this",
        "have",
        "your",
        "into",
        "their",
        "about",
        "will",
        "they",
        "more",
        "than",
        "were",
        "been",
        "whisky",
        "whiskey",
    }
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for token in tokens:
        if token in stop_words:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:15]]


def fallback_summary(name: str, page_title: str, text: str, keywords: list[str]) -> str:
    snippet = text[:1200]
    return (
        f"## Source Context\n"
        f"- Source: {name}\n"
        f"- Page: {page_title or 'Untitled'}\n\n"
        f"## Extracted Summary Snippet\n"
        f"- Automated extraction fallback was used in this run.\n"
        f"- Snippet: {snippet}\n\n"
        f"## Candidate Keywords\n"
        f"- Candidate keywords: {', '.join(keywords[:10]) if keywords else 'none'}\n\n"
        f"## Validation Notes\n"
        f"- Verify details directly from source page.\n"
        f"- This fallback is intentionally non-prescriptive and may not reflect final content structure."
    )


def normalize_url(base_url: str, href: str) -> str:
    href = href.strip()
    if not href:
        return ""
    if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
        return ""
    resolved = urljoin(base_url, href)
    resolved, _ = urldefrag(resolved)
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return resolved


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm", ".mpga"}

# Known podcast CDN/player iframe hostnames whose src signals a direct audio episode.
_PODCAST_IFRAME_HOSTS = {
    "html5-player.libsyn.com",
    "player.buzzsprout.com",
    "player.simplecast.com",
    "embed.podcasts.apple.com",
    "open.spotify.com",
    "player.transistor.fm",
    "www.podbean.com",
    "anchor.fm",
    "podcasters.spotify.com",
}


def _is_podcast_iframe_src(src: str) -> bool:
    """Return True if the iframe src is from a known podcast player CDN."""
    try:
        host = urlparse(src).hostname or ""
        return host in _PODCAST_IFRAME_HOSTS
    except Exception:
        return False


def fetch_rss_audio_map(rss_url: str, timeout: int = 30) -> dict[str, list[str]]:
    """Fetch a podcast RSS feed and return a mapping of episode page URL -> [mp3 url, ...].

    Falls back gracefully; returns an empty dict on any error.
    """
    try:
        req = Request(rss_url, headers={"User-Agent": "WhiskyCrawler/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            rss_bytes = resp.read()
    except Exception:
        return {}

    result: dict[str, list[str]] = {}
    try:
        root = ET.fromstring(rss_bytes.decode("utf-8", errors="replace"))
        ns: dict[str, str] = {}  # ElementTree handles default namespace via tag matching
        for item in root.iter("item"):
            link_el = item.find("link")
            page_url = (link_el.text or "").strip() if link_el is not None else ""
            # Normalise: strip trailing slash
            page_url = page_url.rstrip("/")
            audio_urls: list[str] = []
            for enc in item.iter("enclosure"):
                enc_url = (enc.get("url") or "").strip()
                enc_type = (enc.get("type") or "").strip().lower()
                if enc_url and enc_type.startswith("audio/"):
                    audio_urls.append(enc_url)
            if page_url and audio_urls:
                result.setdefault(page_url, []).extend(audio_urls)
    except Exception:
        pass

    return result


def is_audio_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in AUDIO_EXTENSIONS)


def collect_audio_urls(base_url: str, collector: ContentCollector) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for raw in collector.audio_sources + collector.links:
        normalized = normalize_url(base_url, raw)
        if not normalized or not is_audio_url(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def download_binary(url: str, timeout: int = 90) -> bytes:
    req = Request(url, headers={"User-Agent": "WhiskyCrawler/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _derive_whisper_model_name(ggml_path: Path) -> str:
    """Extract an openai-whisper model name from a ggml filename.

    e.g. ``ggml-large-v3.bin`` -> ``large-v3``, ``ggml-medium.bin`` -> ``medium``.
    Falls back to returning the stem as-is if it does not match the pattern.
    """
    stem = ggml_path.stem  # strip extension
    if stem.startswith("ggml-"):
        stem = stem[5:]
    return stem


def transcribe_audio_with_python_api(
    audio_url: str,
    model_name: str,
    timeout_seconds: int,
    _model_cache: dict = {},  # noqa: B006 - intentional mutable default for caching
) -> str:
    """Transcribe audio using the openai-whisper Python library (no subprocess required).

    The loaded model is cached in ``_model_cache`` to avoid re-loading between calls.
    """
    try:
        import whisper as _whisper  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("openai-whisper Python package not installed") from exc

    content = download_binary(audio_url)
    suffix = Path(urlparse(audio_url).path).suffix or ".mp3"

    with tempfile.TemporaryDirectory(prefix="whisky-audio-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        input_path = tmp_dir / f"input{suffix}"
        input_path.write_bytes(content)

        # Avoid timeout threads for Whisper Python API. A timed-out thread cannot be
        # safely cancelled and can keep downloading/loading the model in the
        # background, which can corrupt the local model cache and starve retries.
        if model_name not in _model_cache:
            _model_cache[model_name] = _whisper.load_model(model_name)
        transcription = _model_cache[model_name].transcribe(str(input_path))
        return str(transcription.get("text", "")).strip()


def page_needs_audio_retry(
    existing_row: sqlite3.Row,
    page_url: str,
    rss_audio_map: dict[str, list[str]],
) -> bool:
    # Retry only when we know audio should exist (RSS hit) but no saved audio
    # section is present in the stored summary.
    if not rss_audio_map.get(page_url.rstrip("/")):
        return False
    summary_markdown = str(existing_row["summary_markdown"] or "")
    return "## Audio Content" not in summary_markdown


def find_whisper_executable(explicit: str | None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    candidates.extend(["whisper-cli", "whisper", str(PROJECT_ROOT / "whisper" / "main")])

    for candidate in candidates:
        resolved = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        if resolved and Path(resolved).exists():
            return resolved
    raise RuntimeError("Whisper executable not found. Install whisper-cli or pass --whisper-executable.")


def transcribe_audio_with_whisper(
    audio_url: str,
    whisper_executable: str,
    whisper_model_path: Path,
    timeout_seconds: int,
) -> str:
    content = download_binary(audio_url)
    suffix = Path(urlparse(audio_url).path).suffix or ".mp3"

    with tempfile.TemporaryDirectory(prefix="whisky-audio-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        input_path = tmp_dir / f"input{suffix}"
        input_path.write_bytes(content)

        out_prefix = tmp_dir / "transcript"
        exe_name = Path(whisper_executable).name.lower()

        if "whisper-cli" in exe_name or exe_name == "main":
            cmd = [
                whisper_executable,
                "-m",
                str(whisper_model_path),
                "-f",
                str(input_path),
                "-otxt",
                "-of",
                str(out_prefix),
            ]
            subprocess.run(cmd, check=True, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            txt_path = out_prefix.with_suffix(".txt")
            if not txt_path.exists():
                raise RuntimeError("Whisper CLI did not produce transcript file")
            return txt_path.read_text(encoding="utf-8", errors="replace").strip()

        cmd = [
            # openai-whisper CLI: --model takes a name (e.g. large-v3), not a ggml file path
            whisper_executable,
            str(input_path),
            "--model",
            _derive_whisper_model_name(whisper_model_path),
            "--output_format",
            "txt",
            "--output_dir",
            str(tmp_dir),
        ]
        subprocess.run(cmd, check=True, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        txt_path = tmp_dir / f"{input_path.stem}.txt"
        if not txt_path.exists():
            raise RuntimeError("Whisper command did not produce transcript file")
        return txt_path.read_text(encoding="utf-8", errors="replace").strip()


def lmstudio_summarize_transcript(
    base_url: str,
    model: str,
    site_name: str,
    page_url: str,
    audio_url: str,
    transcript: str,
    timeout_seconds: int = 1800,
) -> tuple[str, list[str]]:
    trimmed = transcript[:14000]
    prompt = (
        "You summarize whisky-related audio transcripts. "
        "Return strict JSON with keys summary_markdown and keywords. "
        "summary_markdown should reflect the transcript faithfully with clear markdown headings chosen to fit the actual content; avoid forcing a fixed section template. "
        "You may use sections such as Key Takeaways, Production Signals, Commercial Signals, or Risks/Unknowns when they naturally fit, but they are optional. "
        "keywords must be 8 to 20 lower-case topical phrases."
    )
    user_payload = {
        "site_name": site_name,
        "page_url": page_url,
        "audio_url": audio_url,
        "transcript": trimmed,
    }
    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ],
    }
    req = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = json.loads(resp.read().decode("utf-8", errors="replace"))

    content = raw["choices"][0]["message"]["content"]
    parsed = try_parse_json_block(content)
    summary_md = str(parsed.get("summary_markdown", "")).strip()
    keywords = [
        normalize_ws(str(k).lower())
        for k in ((parsed.get("keywords") if isinstance(parsed, dict) else None) or [])
        if isinstance(k, str) and normalize_ws(k)
    ]
    if not summary_md:
        summary_md = "- Transcript captured; summary unavailable in this run."
    if not keywords:
        keywords = fallback_keywords(transcript)
    return summary_md, sorted(set(keywords))


def build_audio_markdown(audio_items: list[dict[str, str]]) -> str:
    if not audio_items:
        return ""
    chunks = ["## Audio Content", ""]
    for idx, item in enumerate(audio_items, start=1):
        chunks.extend(
            [
                f"### Audio {idx}",
                f"- URL: {item['url']}",
                "",
                "#### Transcript Summary",
                item["summary"].strip(),
                "",
                "#### Full Transcript",
                item["transcript"].strip() or "(empty transcript)",
                "",
            ]
        )
    return "\n".join(chunks).strip()


def same_domain(url_a: str, url_b: str) -> bool:
    def _bare(netloc: str) -> str:
        return netloc.lower().removeprefix("www.")
    return _bare(urlparse(url_a).netloc) == _bare(urlparse(url_b).netloc)


def should_skip_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".mp4", ".mp3"]):
        return True
    return False


def canonicalize_site_root(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def open_selenium_driver(headless: bool):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except Exception as exc:
        raise RuntimeError("selenium is not installed. Install with: pip install selenium") from exc

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--lang=en-US")
    options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

    for candidate in ["chromium-browser", "chromium", "google-chrome"]:
        binary_path = shutil.which(candidate)
        if binary_path:
            options.binary_location = binary_path
            break

    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception:
        chromedriver_path = PROJECT_ROOT / "tools" / "chromedriver"
        if chromedriver_path.exists():
            service = Service(executable_path=str(chromedriver_path))
            return webdriver.Chrome(service=service, options=options)
        raise


def _build_pdf_markdown(url: str, title: str, text: str) -> str:
    cleaned = text.strip()
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- Source PDF: {url}",
            "",
            "## Document Text",
            "",
            cleaned,
            "",
        ]
    )


def _extract_pdf_with_pypdf(body: bytes, url: str) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore[import]
    except Exception as exc:
        raise RuntimeError("pypdf_unavailable") from exc

    reader = PdfReader(BytesIO(body))
    metadata_title = ""
    try:
        metadata_title = str((reader.metadata or {}).get("/Title") or "").strip()
    except Exception:
        metadata_title = ""

    chunks: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            chunks.append(page_text)

    text = "\n\n".join(chunks).strip()
    if not text:
        raise RuntimeError("empty_pdf_text")

    fallback_title = Path(urlparse(url).path).name or "PDF Document"
    title = metadata_title or fallback_title
    return _build_pdf_markdown(url=url, title=title, text=text), title


def _extract_pdf_with_pdftotext(body: bytes, url: str) -> tuple[str, str]:
    pdftotext_bin = shutil.which("pdftotext")
    if not pdftotext_bin:
        raise RuntimeError("pdftotext_unavailable")

    with tempfile.TemporaryDirectory(prefix="whisky-pdf-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        pdf_path = tmp_dir / "input.pdf"
        pdf_path.write_bytes(body)

        result = subprocess.run(
            [pdftotext_bin, "-layout", str(pdf_path), "-"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        text = result.stdout.strip()
        if not text:
            raise RuntimeError("empty_pdf_text")

    title = Path(urlparse(url).path).name or "PDF Document"
    return _build_pdf_markdown(url=url, title=title, text=text), title


def extract_pdf_to_markdown(body: bytes, url: str) -> tuple[str, str]:
    first_error: Exception | None = None
    for extractor in (_extract_pdf_with_pypdf, _extract_pdf_with_pdftotext):
        try:
            return extractor(body, url)
        except Exception as exc:
            if first_error is None:
                first_error = exc
            continue
    raise RuntimeError(f"pdf_extract_failed:{first_error}")


def fetch_with_direct(url: str, page_timeout: int) -> tuple[str, str, str, str]:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=page_timeout) as resp:
        content_type = str(resp.headers.get("Content-Type", "")).lower()
        body = resp.read()
        final_url = resp.geturl() or url

    parsed_final = urlparse(final_url)
    looks_like_pdf = parsed_final.path.lower().endswith(".pdf") or "application/pdf" in content_type

    if looks_like_pdf:
        markdown, title = extract_pdf_to_markdown(body=body, url=final_url)
        return markdown, title, final_url, "pdf"

    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise RuntimeError(f"non_html_response:{content_type or 'unknown'}")

    html = body.decode("utf-8", errors="replace")
    collector = ContentCollector()
    collector.feed(html)
    return html, collector.title, final_url, "html"


class CdpSession:
    def __init__(self, cdp_url: str, page_timeout: int) -> None:
        self.cdp_url = cdp_url
        self.page_timeout = page_timeout
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "CdpSession":
        try:
            playwright_module = importlib.import_module("playwright.sync_api")
            sync_playwright = getattr(playwright_module, "sync_playwright")
        except Exception as exc:
            raise RuntimeError("playwright is required for CDP fetch mode") from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
        self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        self._page = self._context.new_page()
        self._page.set_default_navigation_timeout(self.page_timeout * 1000)
        self._page.set_default_timeout(self.page_timeout * 1000)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._page is not None:
            self._page.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def fetch(self, url: str) -> tuple[str, str, str]:
        if self._page is None:
            raise RuntimeError("CDP session is not initialized")
        try:
            self._page.goto(url, wait_until="networkidle", timeout=self.page_timeout * 1000)
        except Exception:
            # networkidle can time out on busy pages; fall back and still grab content
            pass
        try:
            self._page.wait_for_timeout(1500)
            html = self._page.content() or ""
            title = self._page.title() or ""
            current_url = self._page.url or url
        except Exception as exc:
            raise RuntimeError(f"cdp_page_read_failed:{exc}") from exc
        return html, title, current_url


def handle_age_gate(driver, wait_seconds: int) -> bool:
    # Keep this broad and text-based because every distillery implements age-gates differently.
    candidates = [
        "I am 18",
        "I'm 18",
        "I am over 18",
        "Yes",
        "Enter",
        "Accept",
        "Continue",
        "Over 18",
        "I am of legal drinking age",
    ]
    clicked = False
    end_time = time.time() + wait_seconds

    try:
        from selenium.webdriver.common.by import By
    except Exception:
        return False

    while time.time() < end_time:
        buttons = driver.find_elements(By.XPATH, "//button | //a | //input[@type='button'] | //input[@type='submit']")
        for button in buttons:
            try:
                text = normalize_ws((button.text or button.get_attribute("value") or "").lower())
                if not text:
                    continue
                if any(candidate.lower() in text for candidate in candidates):
                    button.click()
                    clicked = True
                    time.sleep(1.0)
            except Exception:
                continue

        if clicked:
            break
        time.sleep(0.5)

    return clicked


def fetch_with_selenium(driver, url: str, page_timeout: int, age_gate_wait: int) -> tuple[str, str, str]:
    driver.set_page_load_timeout(page_timeout)
    driver.get(url)
    handle_age_gate(driver, age_gate_wait)
    time.sleep(0.6)
    html = driver.page_source or ""
    title = driver.title or ""
    current_url = driver.current_url or url
    return html, title, current_url


def get_or_create_site(conn: sqlite3.Connection, target: SiteTarget) -> sqlite3.Row:
    root_url = canonicalize_site_root(target.url)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO sites(site_type, name, root_url, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(site_type, root_url) DO UPDATE SET
            name=excluded.name
        """,
        (target.site_type, target.name, root_url, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM sites WHERE site_type = ? AND root_url = ?",
        (target.site_type, root_url),
    ).fetchone()
    if not row:
        raise RuntimeError("Failed to create site row")
    return row


def page_recent_enough(last_crawled_at: str | None, recrawl_days: int) -> bool:
    if not last_crawled_at:
        return False
    try:
        ts = datetime.fromisoformat(last_crawled_at)
    except ValueError:
        return False
    threshold = datetime.now(timezone.utc) - timedelta(days=recrawl_days)
    return ts >= threshold


def write_markdown_output(base_dir: Path, site_slug: str, page_url: str, title: str, summary_markdown: str, keywords: list[str]) -> Path:
    parsed = urlparse(page_url)
    path_slug = slugify((parsed.path or "home").replace("/", "-")) or "home"
    file_path = base_dir / site_slug / f"{path_slug}.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    body = [
        f"# {title or 'Untitled'}",
        "",
        f"- URL: {page_url}",
        f"- Captured: {datetime.now(timezone.utc).isoformat()}",
        f"- Keywords: {', '.join(keywords)}",
        "",
        summary_markdown.strip(),
        "",
    ]
    file_path.write_text("\n".join(body), encoding="utf-8")
    return file_path


def update_keyword_index(conn: sqlite3.Connection, site_id: int, page_url: str, keywords: list[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "DELETE FROM keyword_index WHERE site_id = ? AND page_url = ?",
        (site_id, page_url),
    )
    for word in sorted(set(k for k in keywords if k)):
        conn.execute(
            """
            INSERT OR REPLACE INTO keyword_index(keyword, site_id, page_url, score, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (word, site_id, page_url, 1, now),
        )


def _ensure_distillery_summary_schema(conn: sqlite3.Connection) -> None:
    cols = {
        str(row[1]).lower()
        for row in conn.execute("PRAGMA table_info(distilleries)").fetchall()
    }
    additions: list[tuple[str, str]] = []
    if "description" not in cols:
        additions.append(("description", "TEXT"))
    if "search_terms" not in cols:
        additions.append(("search_terms", "TEXT"))
    if "search_metadata_json" not in cols:
        additions.append(("search_metadata_json", "TEXT"))
    if "last_summarized_at" not in cols:
        additions.append(("last_summarized_at", "TEXT"))

    for col, typ in additions:
        conn.execute(f"ALTER TABLE distilleries ADD COLUMN {col} {typ}")
    if additions:
        conn.commit()


def _normalize_site_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = parsed.path or "/"
    return f"{host}{path}".rstrip("/")


def _find_distillery_row(conn: sqlite3.Connection, target: SiteTarget) -> sqlite3.Row | None:
    row = conn.execute(
        "SELECT * FROM distilleries WHERE lower(name) = lower(?) LIMIT 1",
        (target.name,),
    ).fetchone()
    if row is not None:
        return row

    target_norm = _normalize_site_url(target.url)
    if not target_norm:
        return None

    rows = conn.execute(
        "SELECT * FROM distilleries WHERE official_site LIKE 'http%'",
    ).fetchall()
    for candidate in rows:
        if _normalize_site_url(str(candidate["official_site"] or "")) == target_norm:
            return candidate
    return None


def _sync_distillery_summary_from_state(
    state_conn: sqlite3.Connection,
    distillery_db_path: Path,
    site_id: int,
    target: SiteTarget,
    lmstudio_url: str,
    lmstudio_model: str,
    lmstudio_extract_timeout: int,
) -> dict[str, Any]:
    rows = state_conn.execute(
        """
        SELECT
            url,
            title,
            description,
            summary_markdown,
            summary_json,
            extracted_products_json,
            extracted_reviews_json,
            keyword_sets_json,
            blog_topics_json,
            course_topics_json,
            db_enrichment_json,
            keywords_json,
            last_crawled_at,
            crawl_status
        FROM pages
        WHERE site_id = ? AND crawl_status LIKE 'ok:%'
        ORDER BY COALESCE(last_crawled_at, '') DESC, url ASC
        """,
        (site_id,),
    ).fetchall()

    page_payloads: list[dict[str, Any]] = []
    for row in rows:
        keywords = []
        try:
            keywords = _coerce_string_list(json.loads(str(row["keywords_json"] or "[]")), limit=25)
        except Exception:
            keywords = []
        page_payloads.append(
            {
                "url": str(row["url"] or ""),
                "title": str(row["title"] or ""),
                "description": str(row["description"] or ""),
                "summary_markdown": str(row["summary_markdown"] or ""),
                "summary_json": _safe_json_loads(str(row["summary_json"] or "{}"), {}),
                "products": _safe_json_loads(str(row["extracted_products_json"] or "[]"), []),
                "reviews": _safe_json_loads(str(row["extracted_reviews_json"] or "[]"), []),
                "keyword_sets": _safe_json_loads(str(row["keyword_sets_json"] or "{}"), {}),
                "blog_topics": _safe_json_loads(str(row["blog_topics_json"] or "[]"), []),
                "course_topics": _safe_json_loads(str(row["course_topics_json"] or "[]"), []),
                "db_enrichment_candidates": _safe_json_loads(str(row["db_enrichment_json"] or "{}"), {}),
                "keywords": keywords,
            }
        )

    if not page_payloads:
        return {
            "updated": False,
            "reason": "no_ok_pages",
            "site_name": target.name,
            "site_id": site_id,
        }

    enrichment = lmstudio_summarize_distillery_site(
        base_url=lmstudio_url,
        model=lmstudio_model,
        distillery_name=target.name,
        distillery_url=target.url,
        page_payloads=page_payloads,
        timeout_seconds=lmstudio_extract_timeout,
    )

    dist_conn = sqlite3.connect(distillery_db_path)
    dist_conn.row_factory = sqlite3.Row
    try:
        _ensure_distillery_summary_schema(dist_conn)
        dist_row = _find_distillery_row(dist_conn, target)
        if dist_row is None:
            return {
                "updated": False,
                "reason": "distillery_not_found",
                "site_name": target.name,
                "site_id": site_id,
            }

        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(enrichment["metadata"], ensure_ascii=True, sort_keys=True)
        search_terms = ", ".join(enrichment["search_terms"])[:2500]

        dist_conn.execute(
            """
            UPDATE distilleries
            SET
                description = ?,
                key_focus = ?,
                source_headers = ?,
                notes = ?,
                search_terms = ?,
                search_metadata_json = ?,
                last_summarized_at = ?,
                study_status = CASE
                    WHEN COALESCE(study_status, '') IN ('', 'Not started')
                        THEN 'Crawl summarized'
                    ELSE study_status
                END
            WHERE id = ?
            """,
            (
                enrichment["description"],
                enrichment["key_focus"],
                enrichment["source_headers"],
                enrichment["notes"],
                search_terms,
                metadata_json,
                now,
                int(dist_row["id"]),
            ),
        )
        dist_conn.commit()
        return {
            "updated": True,
            "site_name": target.name,
            "site_id": site_id,
            "distillery_id": int(dist_row["id"]),
            "pages_used": len(page_payloads),
            "search_terms_count": len(enrichment["search_terms"]),
            "metadata": enrichment["metadata"],
        }
    finally:
        dist_conn.close()


def export_site_index(conn: sqlite3.Connection, output_path: Path) -> Path:
    rows = conn.execute(
        """
        SELECT k.keyword, s.site_type, s.name, p.url
        FROM keyword_index k
        JOIN sites s ON s.id = k.site_id
        JOIN pages p ON p.site_id = s.id AND p.url = k.page_url
        ORDER BY k.keyword, s.name, p.url
        """
    ).fetchall()

    bucket: dict[str, list[tuple[str, str, str]]] = {}
    for row in rows:
        bucket.setdefault(str(row["keyword"]), []).append((str(row["site_type"]), str(row["name"]), str(row["url"])))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Whisky Crawl Keyword Index",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]

    for keyword in sorted(bucket.keys()):
        lines.append(f"## {keyword}")
        for site_type, name, url in bucket[keyword][:50]:
            lines.append(f"- [{site_type}] {name}: {url}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def crawl_site(
    conn: sqlite3.Connection,
    target: SiteTarget,
    distillery_db_path: Path,
    markdown_dir: Path,
    max_pages_per_site: int,
    recrawl_days: int,
    force_rescrape: bool,
    page_timeout: int,
    lmstudio_url: str,
    lmstudio_model: str,
    lmstudio_extract_timeout: int,
    throttle_seconds: float,
    whisper_model_path: Path,
    whisper_executable: str | None,
    max_audio_files_per_page: int,
    audio_transcribe_timeout: int,
    parallel_page_loads: int,
    direct_fetch_timeout: int,
    cdp_url: str,
    verbose_crawl: bool,
    distillery_sync: bool,
) -> dict[str, Any]:
    site_row = get_or_create_site(conn, target)
    site_id = int(site_row["id"])
    site_slug = slugify(f"{target.site_type}-{target.name}")

    # Pre-fetch podcast RSS audio map (page_url -> [mp3_url]) if configured.
    rss_audio_map: dict[str, list[str]] = {}
    if target.podcast_rss:
        print(f"  [rss] fetching podcast feed: {target.podcast_rss}")
        rss_audio_map = fetch_rss_audio_map(target.podcast_rss)
        print(f"  [rss] {len(rss_audio_map)} episode(s) found in feed")

    queue: list[tuple[str, int]] = [(canonicalize_site_root(target.url), 0)]
    seen: set[str] = set()

    # Seed episode URLs from RSS directly into the queue at depth=1 so they are
    # visited even if the homepage does not link to them directly.
    if rss_audio_map:
        for episode_url in list(rss_audio_map.keys()):
            if same_domain(target.url, episode_url) and episode_url not in seen:
                queue.append((episode_url, 1))

    processed_pages = 0
    skipped_pages = 0
    failed_pages = 0
    newly_summarized = 0

    cdp_session: CdpSession | None = None
    parallel_slots = max(1, parallel_page_loads)

    def log(msg: str) -> None:
        if verbose_crawl:
            print(msg)

    def classify_fetch_mode(existing_row: sqlite3.Row | None) -> str:
        if existing_row:
            last_status = str(existing_row["crawl_status"] or "")
            if last_status.startswith("error:direct"):
                return "cdp"
            # If CDP is available and the previous direct fetch extracted no links,
            # re-try via CDP so JS-rendered navigation is followed.
            if cdp_url and last_status.startswith("ok:direct") and existing_row is not None:
                links = json.loads(existing_row["extracted_links_json"] or "[]")
                if not links:
                    return "cdp"
            return "direct-rescrape"
        # When a CDP URL is provided, use CDP for new pages to handle JS-rendered
        # navigation and age-gates from the first visit.
        if cdp_url:
            return "cdp"
        return "direct"

    try:
        while queue and processed_pages < max_pages_per_site:
            pending: list[tuple[str, int, sqlite3.Row | None, str]] = []
            while queue and len(pending) < parallel_slots and (processed_pages + len(pending)) < max_pages_per_site:
                page_url, depth = queue.pop(0)
                if page_url in seen:
                    continue
                seen.add(page_url)

                if should_skip_path(page_url):
                    continue

                existing = conn.execute(
                    "SELECT * FROM pages WHERE site_id = ? AND url = ?",
                    (site_id, page_url),
                ).fetchone()

                if existing and not force_rescrape and page_recent_enough(existing["last_crawled_at"], recrawl_days):
                    if page_needs_audio_retry(existing, page_url, rss_audio_map):
                        pending.append((page_url, depth, existing, "audio-retry"))
                        log(f"  [retry] audio-only retry for {page_url}")
                        continue
                    skipped_pages += 1
                    existing_links = json.loads(existing["extracted_links_json"] or "[]")
                    for link in existing_links:
                        if same_domain(target.url, link) and link not in seen:
                            queue.append((link, depth + 1))
                    log(f"  [skip] fresh cache {page_url}")
                    continue

                pending.append((page_url, depth, existing, classify_fetch_mode(existing)))

            if not pending:
                continue

            fetch_results: list[tuple[str, int, PagePayload | None, sqlite3.Row | None, Exception | None]] = []
            parallel_candidates = [p for p in pending if p[3] == "direct" and not force_rescrape and parallel_slots > 1]
            sequential_candidates = [p for p in pending if p not in parallel_candidates]

            if parallel_candidates:
                log(f"  [batch] parallel loading {len(parallel_candidates)} page(s)")
                with ThreadPoolExecutor(max_workers=min(parallel_slots, len(parallel_candidates))) as executor:
                    future_map = {
                        executor.submit(fetch_with_direct, page_url, direct_fetch_timeout): (page_url, depth, existing_row)
                        for page_url, depth, existing_row, _mode in parallel_candidates
                    }
                    for future in as_completed(future_map):
                        page_url, depth, existing_row = future_map[future]
                        try:
                            content, browser_title, current_url, content_kind = future.result()
                            fetch_results.append(
                                (
                                    page_url,
                                    depth,
                                    PagePayload(
                                        requested_url=page_url,
                                        depth=depth,
                                        current_url=current_url,
                                        title=browser_title,
                                        content=content,
                                        content_kind=content_kind,
                                        fetch_mode="direct-parallel",
                                    ),
                                    existing_row,
                                    None,
                                )
                            )
                            log(f"  [visit] loaded {page_url} via direct-parallel")
                        except Exception as exc:
                            fetch_results.append((page_url, depth, None, existing_row, RuntimeError(f"direct-parallel {page_url}: {exc}")))
                            log(f"  [fail] direct-parallel {page_url}: {type(exc).__name__}: {exc}")

            for page_url, depth, existing, mode in sequential_candidates:
                try:
                    log(f"  [visit] loading {page_url} via {mode}")
                    if mode == "audio-retry":
                        fetch_results.append(
                            (
                                page_url,
                                depth,
                                PagePayload(
                                    requested_url=page_url,
                                    depth=depth,
                                    current_url=page_url,
                                    title=str((existing["title"] if existing is not None else "") or ""),
                                    content="",
                                    content_kind="cached",
                                    fetch_mode="audio-retry",
                                ),
                                existing,
                                None,
                            )
                        )
                        continue
                    if mode == "cdp":
                        if cdp_session is None:
                            cdp_session = CdpSession(cdp_url=cdp_url, page_timeout=page_timeout)
                            cdp_session.__enter__()
                        try:
                            html, browser_title, current_url = cdp_session.fetch(page_url)
                        except Exception:
                            if cdp_session is not None:
                                try:
                                    cdp_session.__exit__(None, None, None)
                                except Exception:
                                    pass
                            cdp_session = CdpSession(cdp_url=cdp_url, page_timeout=page_timeout)
                            cdp_session.__enter__()
                            html, browser_title, current_url = cdp_session.fetch(page_url)
                        content = html
                        content_kind = "html"
                        fetch_mode = "cdp"
                    else:
                        content, browser_title, current_url, content_kind = fetch_with_direct(page_url, direct_fetch_timeout)
                        fetch_mode = "direct-sequential" if mode == "direct-rescrape" else "direct"
                    fetch_results.append(
                        (
                            page_url,
                            depth,
                            PagePayload(
                                requested_url=page_url,
                                depth=depth,
                                current_url=current_url,
                                title=browser_title,
                                content=content,
                                content_kind=content_kind,
                                fetch_mode=fetch_mode,
                            ),
                            existing,
                            None,
                        )
                    )
                except Exception as exc:
                    fetch_results.append((page_url, depth, None, existing, RuntimeError(f"{mode} {page_url}: {exc}")))
                    log(f"  [fail] {mode} {page_url}: {type(exc).__name__}: {exc}")

            prepared_pages: list[PreparedPage] = []

            for requested_url, depth, payload, existing, fetch_error in fetch_results:
                now = datetime.now(timezone.utc).isoformat()
                if fetch_error is not None or payload is None:
                    failed_pages += 1
                    status_url = requested_url or "unknown"
                    status_prefix = "error:direct"
                    message = str(fetch_error or "unknown fetch error")
                    if message.startswith("cdp"):
                        status_prefix = "error:cdp"
                    conn.execute(
                        """
                        INSERT INTO pages (site_id, url, crawl_status, last_crawled_at, crawl_count)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(site_id, url) DO UPDATE SET
                            crawl_status=excluded.crawl_status,
                            last_crawled_at=excluded.last_crawled_at,
                            crawl_count=pages.crawl_count + 1
                        """,
                        (site_id, status_url, f"{status_prefix}:{message}", now),
                    )
                    conn.commit()
                    continue

                try:
                    content = payload.content
                    browser_title = payload.title
                    current_url = payload.current_url
                    page_url = payload.requested_url
                    if payload.fetch_mode == "audio-retry":
                        page_title = str((existing["title"] if existing is not None else "") or browser_title)
                        text_content = str((existing["text_content"] if existing is not None else "") or "")
                        description = str((existing["description"] if existing is not None else "") or "")
                        unique_links = json.loads((existing["extracted_links_json"] if existing is not None else "[]") or "[]")
                        audio_urls: list[str] = []
                    elif payload.content_kind == "pdf":
                        page_title = browser_title or (Path(urlparse(current_url).path).name or "PDF Document")
                        text_content = content
                        description = "PDF document"
                        audio_urls = []
                        unique_links = []
                        log(f"  [pdf] extracted markdown text for {current_url}")
                    else:
                        collector = ContentCollector()
                        collector.feed(content)
                        page_title = collector.title or browser_title
                        text_content = collector.visible_text
                        description = collector.description
                        audio_urls = collect_audio_urls(current_url, collector)

                        normalized_links: list[str] = []
                        for href in collector.links:
                            normalized = normalize_url(current_url, href)
                            if not normalized:
                                continue
                            if not same_domain(target.url, normalized):
                                continue
                            if should_skip_path(normalized):
                                continue
                            normalized_links.append(normalized)

                        unique_links = []
                        seen_links: set[str] = set()
                        for link in normalized_links:
                            if link in seen_links:
                                continue
                            seen_links.add(link)
                            unique_links.append(link)
                            if link not in seen:
                                queue.append((link, depth + 1))

                    # Supplement with RSS-derived MP3 URLs (matched on stripped URL).
                    rss_key = current_url.rstrip("/")
                    rss_mp3s = rss_audio_map.get(rss_key, [])
                    if rss_mp3s:
                        log(f"  [rss] matched {len(rss_mp3s)} audio URL(s) for {current_url}")
                        seen_audio: set[str] = set(audio_urls)
                        for mp3 in rss_mp3s:
                            if mp3 not in seen_audio:
                                audio_urls.append(mp3)
                                seen_audio.add(mp3)
                    audio_urls = audio_urls[: max(0, max_audio_files_per_page)]

                    audio_items: list[dict[str, str]] = []
                    transcript_blob_parts: list[str] = []
                    transcript_keywords: list[str] = []
                    if audio_urls:
                        # Determine transcription method: Python API preferred, CLI fallback.
                        try:
                            import whisper as _whisper_check  # noqa: F401
                            use_python_api = True
                        except ImportError:
                            use_python_api = False

                        if not use_python_api:
                            try:
                                whisper_bin = find_whisper_executable(whisper_executable)
                            except Exception:
                                whisper_bin = ""
                        else:
                            whisper_bin = ""

                        whisper_model_name = _derive_whisper_model_name(whisper_model_path)

                        for audio_url in audio_urls:
                            if not use_python_api and not whisper_bin:
                                log("  [transcribe] No Whisper available (install openai-whisper); skipping audio transcription")
                                break
                            try:
                                log(f"  [transcribe] {current_url} -> {audio_url}")
                                if use_python_api:
                                    transcript = transcribe_audio_with_python_api(
                                        audio_url=audio_url,
                                        model_name=whisper_model_name,
                                        timeout_seconds=audio_transcribe_timeout,
                                    )
                                else:
                                    transcript = transcribe_audio_with_whisper(
                                        audio_url=audio_url,
                                        whisper_executable=whisper_bin,
                                        whisper_model_path=whisper_model_path,
                                        timeout_seconds=audio_transcribe_timeout,
                                    )
                                log(f"  [summarize] transcript summary for {audio_url}")
                                try:
                                    t_summary, t_keywords = lmstudio_summarize_transcript(
                                        base_url=lmstudio_url,
                                        model=lmstudio_model,
                                        site_name=target.name,
                                        page_url=current_url,
                                        audio_url=audio_url,
                                        transcript=transcript,
                                        timeout_seconds=lmstudio_extract_timeout,
                                    )
                                except Exception as exc:
                                    log(f"  [fail] transcript-summary {audio_url}: {type(exc).__name__}: {exc}")
                                    t_summary = "- Transcript captured; summary unavailable in this run."
                                    t_keywords = fallback_keywords(transcript)
                                transcript_keywords.extend(t_keywords)
                                transcript_blob_parts.append(f"Audio URL: {audio_url}\nTranscript: {transcript}")
                                audio_items.append({"url": audio_url, "transcript": transcript, "summary": t_summary})
                            except Exception as exc:
                                log(f"  [fail] transcribe {audio_url}: {type(exc).__name__}: {exc}")
                                continue

                    transcript_blob = "\n\n".join(transcript_blob_parts)
                    combined_text = text_content + ("\n\n" + transcript_blob if transcript_blob else "")
                    content_hash = hashlib.sha256(
                        (combined_text + "\n" + json.dumps(audio_urls, ensure_ascii=True)).encode("utf-8", errors="ignore")
                    ).hexdigest()
                    prepared_pages.append(
                        PreparedPage(
                            requested_url=page_url,
                            current_url=current_url,
                            depth=depth,
                            page_title=page_title,
                            description=description,
                            combined_text=combined_text,
                            content_hash=content_hash,
                            audio_urls=audio_urls,
                            transcript_keywords=transcript_keywords,
                            audio_items=audio_items,
                            unique_links=unique_links,
                            existing=existing,
                            fetch_mode=payload.fetch_mode,
                        )
                    )
                except Exception as exc:
                    failed_pages += 1
                    status_url = payload.requested_url
                    conn.execute(
                        """
                        INSERT INTO pages (site_id, url, crawl_status, last_crawled_at, crawl_count)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(site_id, url) DO UPDATE SET
                            crawl_status=excluded.crawl_status,
                            last_crawled_at=excluded.last_crawled_at,
                            crawl_count=pages.crawl_count + 1
                        """,
                        (site_id, status_url, f"error:processing:{type(exc).__name__}:{exc}", now),
                    )
                    log(f"  [fail] processing {status_url}: {type(exc).__name__}: {exc}")

                conn.commit()

            summary_results: dict[str, tuple[dict[str, Any], bool]] = {}
            excluded_pages: set[str] = set()
            
            # Stage 1: Screen pages for whisky relevance using granite (quick)
            screening_targets = [
                page for page in prepared_pages if not (page.existing and page.existing["content_hash"] == page.content_hash and not force_rescrape)
            ]
            if screening_targets:
                log(f"  [batch] screening {len(screening_targets)} page(s) for relevance")
                for page in screening_targets:
                    try:
                        is_relevant = lmstudio_screen_page_relevance(
                            base_url=lmstudio_url,
                            model="ibm/granite-4-h-tiny",
                            site_name=target.name,
                            page_url=page.current_url,
                            page_title=page.page_title,
                            text=page.combined_text,
                            timeout_seconds=min(600, lmstudio_extract_timeout),
                        )
                        if not is_relevant:
                            excluded_pages.add(page.current_url)
                            log(f"  [exclude] {page.current_url}: content not whisky-relevant")
                    except Exception as exc:
                        log(f"  [screen] error for {page.current_url}: {type(exc).__name__}: {exc}; assuming relevant")
            
            # Stage 2: Full extraction only for relevant pages using qwen
            summarize_targets = [
                page for page in prepared_pages 
                if not (page.existing and page.existing["content_hash"] == page.content_hash and not force_rescrape)
                and page.current_url not in excluded_pages
            ]
            if summarize_targets:
                log(f"  [batch] parallel summarizing {len(summarize_targets)} page(s)")
                with ThreadPoolExecutor(max_workers=min(parallel_slots, len(summarize_targets))) as executor:
                    future_map = {
                        executor.submit(
                            lmstudio_extract_page_structured,
                            lmstudio_url,
                            lmstudio_model,
                            target.name,
                            target.site_type,
                            target.url,
                            page.current_url,
                            page.page_title,
                            page.combined_text,
                            page.unique_links,
                            lmstudio_extract_timeout,
                        ): page.current_url
                        for page in summarize_targets
                    }
                    for future in as_completed(future_map):
                        current_url = future_map[future]
                        try:
                            structured = future.result()
                            summary_results[current_url] = (structured, True)
                        except Exception as exc:
                            page_ctx = next(p for p in prepared_pages if p.current_url == current_url)
                            structured = _fallback_structured_summary(
                                site_name=target.name,
                                site_url=target.url,
                                page_title=page_ctx.page_title,
                                page_url=page_ctx.current_url,
                                text=page_ctx.combined_text,
                                page_links=page_ctx.unique_links,
                            )
                            summary_results[current_url] = (structured, True)
                            log(f"  [fail] summarize {current_url}: {type(exc).__name__}: {exc}")

            # Handle excluded pages: mark in database and delete markdown
            for page in prepared_pages:
                if page.current_url in excluded_pages:
                    now = datetime.now(timezone.utc).isoformat()
                    conn.execute(
                        """
                        INSERT INTO pages (site_id, url, title, is_content_excluded, crawl_status, last_crawled_at, crawl_count)
                        VALUES (?, ?, ?, 1, ?, ?, 1)
                        ON CONFLICT(site_id, url) DO UPDATE SET
                            is_content_excluded=1,
                            crawl_status=excluded.crawl_status,
                            last_crawled_at=excluded.last_crawled_at,
                            crawl_count=pages.crawl_count + 1
                        """,
                        (site_id, page.current_url, page.page_title, "excluded:not-whisky-relevant", now),
                    )
                    conn.commit()
                    
                    # Delete markdown file if it exists
                    if page.existing and page.existing["markdown_path"]:
                        markdown_file = Path(str(page.existing["markdown_path"]))
                        if markdown_file.exists():
                            markdown_file.unlink()
                            log(f"  [cleanup] deleted markdown for excluded page: {markdown_file}")
                    elif page.current_url not in [p.current_url for p in prepared_pages if p.existing is None]:
                        # Try to find and delete generated markdown file
                        page_slug = slugify(urlparse(page.current_url).path.split("/")[-1] or "page")
                        markdown_file = markdown_dir / site_slug / f"{page_slug}.md"
                        if markdown_file.exists():
                            markdown_file.unlink()
                            log(f"  [cleanup] deleted markdown for excluded page: {markdown_file}")

            for page in prepared_pages:
                now = datetime.now(timezone.utc).isoformat()
                summary_md = ""
                keywords: list[str] = []
                summary_json: dict[str, Any] = {}
                product_records: list[dict[str, Any]] = []
                review_records: list[dict[str, Any]] = []
                keyword_sets: dict[str, Any] = {}
                blog_topics: list[str] = []
                course_topics: list[str] = []
                db_enrichment: dict[str, Any] = {}

                if page.existing and page.existing["content_hash"] == page.content_hash and not force_rescrape:
                    summary_md = str(page.existing["summary_markdown"] or "")
                    keywords = json.loads(page.existing["keywords_json"] or "[]")
                    summary_json = _safe_json_loads(str(page.existing["summary_json"] or "{}"), {})
                    product_records = _safe_json_loads(str(page.existing["extracted_products_json"] or "[]"), [])
                    review_records = _safe_json_loads(str(page.existing["extracted_reviews_json"] or "[]"), [])
                    keyword_sets = _safe_json_loads(str(page.existing["keyword_sets_json"] or "{}"), {})
                    blog_topics = _safe_json_loads(str(page.existing["blog_topics_json"] or "[]"), [])
                    course_topics = _safe_json_loads(str(page.existing["course_topics_json"] or "[]"), [])
                    db_enrichment = _safe_json_loads(str(page.existing["db_enrichment_json"] or "{}"), {})
                    log(f"  [summarize] unchanged content; reused summary for {page.current_url}")
                else:
                    structured, counted = summary_results.get(
                        page.current_url,
                        (
                            _fallback_structured_summary(
                                site_name=target.name,
                                site_url=target.url,
                                page_title=page.page_title,
                                page_url=page.current_url,
                                text=page.combined_text,
                                page_links=page.unique_links,
                            ),
                            True,
                        ),
                    )
                    summary_md = str(structured.get("summary_markdown", "")).strip()
                    keywords = _coerce_string_list(structured.get("keywords", []), limit=200)
                    summary_json = structured
                    product_records = _normalize_product_records(structured.get("product_facts", []))
                    review_records = _normalize_review_records(structured.get("reviews", []))
                    keyword_sets = structured.get("keyword_sets", {}) if isinstance(structured.get("keyword_sets"), dict) else {}
                    blog_topics = _coerce_string_list(structured.get("blog_topic_suggestions", []), limit=80)
                    course_topics = _coerce_string_list(structured.get("course_material_candidates", []), limit=80)
                    db_enrichment = (
                        structured.get("db_enrichment_candidates", {})
                        if isinstance(structured.get("db_enrichment_candidates"), dict)
                        else {}
                    )
                    if counted:
                        newly_summarized += 1

                if page.transcript_keywords:
                    keywords.extend(page.transcript_keywords)
                if keyword_sets:
                    keywords.extend(_flatten_keyword_sets(keyword_sets))
                audio_markdown = build_audio_markdown(page.audio_items)
                if audio_markdown:
                    summary_md = summary_md.rstrip() + "\n\n" + audio_markdown

                keywords = sorted(set(_coerce_string_list(keywords, limit=260)))

                markdown_path = write_markdown_output(
                    markdown_dir,
                    site_slug=site_slug,
                    page_url=page.current_url,
                    title=page.page_title,
                    summary_markdown=summary_md,
                    keywords=keywords,
                )

                conn.execute(
                    """
                    INSERT INTO pages (
                        site_id, url, title, description, text_content, content_hash,
                        extracted_links_json, summary_markdown, summary_json,
                        extracted_products_json, extracted_reviews_json, keyword_sets_json,
                        blog_topics_json, course_topics_json, db_enrichment_json,
                        llm_model, keywords_json, is_content_excluded,
                        crawl_status, last_crawled_at, crawl_count, markdown_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(site_id, url) DO UPDATE SET
                        title=excluded.title,
                        description=excluded.description,
                        text_content=excluded.text_content,
                        content_hash=excluded.content_hash,
                        extracted_links_json=excluded.extracted_links_json,
                        summary_markdown=excluded.summary_markdown,
                        summary_json=excluded.summary_json,
                        extracted_products_json=excluded.extracted_products_json,
                        extracted_reviews_json=excluded.extracted_reviews_json,
                        keyword_sets_json=excluded.keyword_sets_json,
                        blog_topics_json=excluded.blog_topics_json,
                        course_topics_json=excluded.course_topics_json,
                        db_enrichment_json=excluded.db_enrichment_json,
                        llm_model=excluded.llm_model,
                        keywords_json=excluded.keywords_json,
                        is_content_excluded=excluded.is_content_excluded,
                        crawl_status=excluded.crawl_status,
                        last_crawled_at=excluded.last_crawled_at,
                        crawl_count=pages.crawl_count + 1,
                        markdown_path=excluded.markdown_path
                    """,
                    (
                        site_id,
                        page.current_url,
                        page.page_title,
                        page.description,
                        page.combined_text,
                        page.content_hash,
                        json.dumps(page.unique_links, ensure_ascii=True),
                        summary_md,
                        json.dumps(summary_json, ensure_ascii=True),
                        json.dumps(product_records, ensure_ascii=True),
                        json.dumps(review_records, ensure_ascii=True),
                        json.dumps(keyword_sets, ensure_ascii=True),
                        json.dumps(blog_topics, ensure_ascii=True),
                        json.dumps(course_topics, ensure_ascii=True),
                        json.dumps(db_enrichment, ensure_ascii=True),
                        lmstudio_model,
                        json.dumps(sorted(set(keywords)), ensure_ascii=True),
                                                0,
                        f"ok:{page.fetch_mode}",
                        now,
                        1,
                        str(markdown_path),
                    ),
                )

                update_keyword_index(conn, site_id=site_id, page_url=page.current_url, keywords=keywords)
                processed_pages += 1
                conn.commit()
                time.sleep(max(0.0, throttle_seconds))
    finally:
        if cdp_session is not None:
            cdp_session.__exit__(None, None, None)

    conn.execute(
        "UPDATE sites SET last_crawled_at = ?, last_status = ? WHERE id = ?",
        (
            datetime.now(timezone.utc).isoformat(),
            f"ok pages={processed_pages} skipped={skipped_pages} failed={failed_pages}",
            site_id,
        ),
    )
    conn.commit()

    sync_result: dict[str, Any] | None = None
    if distillery_sync and target.site_type == "distillery" and processed_pages > 0:
        try:
            sync_result = _sync_distillery_summary_from_state(
                state_conn=conn,
                distillery_db_path=distillery_db_path,
                site_id=site_id,
                target=target,
                lmstudio_url=lmstudio_url,
                lmstudio_model=lmstudio_model,
                lmstudio_extract_timeout=lmstudio_extract_timeout,
            )
            if verbose_crawl:
                sync_meta = sync_result or {}
                print(
                    f"  [distillery-sync] updated={sync_meta.get('updated')} "
                    f"pages={sync_meta.get('pages_used', 0)}"
                )
        except Exception as exc:
            sync_result = {
                "updated": False,
                "reason": f"sync_error:{type(exc).__name__}:{exc}",
                "site_name": target.name,
                "site_id": site_id,
            }
            print(f"  [distillery-sync] fail {target.name}: {type(exc).__name__}: {exc}")

    return {
        "site_id": site_id,
        "site_type": target.site_type,
        "name": target.name,
        "root_url": target.url,
        "pages_processed": processed_pages,
        "pages_skipped": skipped_pages,
        "pages_failed": failed_pages,
        "pages_summarized": newly_summarized,
        "distillery_sync": sync_result,
    }


def write_run_report(report_path: Path, run_summary: dict[str, Any], per_site: list[dict[str, Any]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Whisky Site Crawl Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Run Summary",
        "",
        f"- Sites processed: {run_summary['sites_processed']}",
        f"- Sites succeeded: {run_summary['sites_succeeded']}",
        f"- Sites failed: {run_summary['sites_failed']}",
        f"- Pages processed: {run_summary['pages_processed']}",
        f"- Pages skipped: {run_summary['pages_skipped']}",
        f"- Pages failed: {run_summary['pages_failed']}",
        f"- Pages summarized: {run_summary['pages_summarized']}",
        "",
        "## Sites",
        "",
        "| Type | Name | Root URL | Processed | Skipped | Failed | Summarized |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in per_site:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["site_type"]).replace("|", " "),
                    str(row["name"]).replace("|", " "),
                    str(row["root_url"]).replace("|", " "),
                    str(row["pages_processed"]),
                    str(row["pages_skipped"]),
                    str(row["pages_failed"]),
                    str(row["pages_summarized"]),
                ]
            )
            + " |"
        )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resumable Selenium crawler for distillery/resource websites with LM Studio summarization and keyword index."
    )
    parser.add_argument("--distillery-db", default="data/distilleries.db", help="Path to distillery SQLite database.")
    parser.add_argument("--resource-db", default="data/resources.db", help="Path to resource SQLite database.")
    parser.add_argument("--resource-seed", default="data/resource_sites_seed.json", help="Resource seed JSON fallback.")
    parser.add_argument(
        "--site-types",
        default="both",
        choices=["both", "distillery", "resource"],
        help="Which site classes to process.",
    )
    parser.add_argument("--max-sites", type=int, default=5, help="Maximum number of sites to process before stopping.")
    parser.add_argument("--filter-name", default="", help="Only crawl sites whose name contains this string (case-insensitive).")
    parser.add_argument("--max-pages-per-site", type=int, default=30, help="Maximum pages to crawl per site.")
    parser.add_argument("--recrawl-days", type=int, default=14, help="Skip recrawl if page was fetched within this many days.")
    parser.add_argument("--force-rescrape", action="store_true", help="Re-fetch and re-summarize even when cache is fresh.")
    parser.add_argument("--state-db", default="data/site_crawl_state.db", help="SQLite DB for crawler state.")
    parser.add_argument("--output-markdown", default="data/crawl_markdown", help="Directory for per-page markdown output.")
    parser.add_argument("--report", default="data/crawl_report.md", help="Markdown report output path.")
    parser.add_argument("--keyword-report", default="data/keyword_index.md", help="Keyword index markdown report.")
    parser.add_argument("--page-timeout", type=int, default=60, help="Selenium page-load timeout in seconds.")
    parser.add_argument("--throttle-seconds", type=float, default=0.8, help="Delay between page fetches.")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    parser.add_argument(
        "--parallel-page-loads",
        type=int,
        default=4,
        help="Number of pages to load in parallel for new direct crawls.",
    )
    parser.add_argument(
        "--direct-fetch-timeout",
        type=int,
        default=45,
        help="Timeout in seconds for direct HTTP page fetches.",
    )
    parser.add_argument(
        "--cdp-url",
        default="http://127.0.0.1:9222",
        help="CDP endpoint used when a prior direct fetch failed.",
    )
    parser.add_argument(
        "--quiet-crawl",
        action="store_true",
        help="Reduce verbose per-page stage logging.",
    )
    parser.add_argument("--lmstudio-url", default="http://127.0.0.1:1234/v1", help="LM Studio OpenAI-compatible base URL.")
    parser.add_argument(
        "--lmstudio-model",
        default="qwen3.5-27b-claude-4.6-opus-reasoning-distilled-v2",
        help="LM model name to use for summaries.",
    )
    parser.add_argument(
        "--whisper-model-path",
        default="/home/stever/projects/whisper models/ggml-large-v3.bin",
        help="Path to Whisper model file used for audio transcription.",
    )
    parser.add_argument(
        "--whisper-executable",
        default="",
        help="Optional explicit Whisper executable path (for example whisper-cli).",
    )
    parser.add_argument(
        "--max-audio-files-per-page",
        type=int,
        default=3,
        help="Maximum number of audio files to transcribe per crawled page.",
    )
    parser.add_argument(
        "--audio-transcribe-timeout",
        type=int,
        default=900,
        help="Timeout in seconds for each audio transcription job.",
    )
    parser.add_argument(
        "--no-distillery-sync",
        action="store_true",
        help="Disable post-crawl distillery summary/metadata sync into distilleries.db.",
    )
    parser.add_argument(
        "--lmstudio-extract-timeout",
        type=int,
        default=1800,
        help="Timeout in seconds for LM Studio summaries and structured extraction (default 1800 for slow local inference).",
    )
    parser.add_argument(
        "--sync-distillery-from-state",
        action="store_true",
        help="Skip crawling and synthesize distillery summaries/metadata from existing state DB pages.",
    )
    args = parser.parse_args()

    distillery_db = Path(args.distillery_db).resolve()
    resource_db = Path(args.resource_db).resolve()
    resource_seed = Path(args.resource_seed).resolve()
    state_db = Path(args.state_db).resolve()
    markdown_dir = Path(args.output_markdown).resolve()
    report_path = Path(args.report).resolve()
    keyword_report = Path(args.keyword_report).resolve()
    whisper_model_path = Path(args.whisper_model_path).expanduser().resolve()

    targets: list[SiteTarget] = []
    if args.site_types in {"both", "distillery"}:
        targets.extend(load_distillery_targets(distillery_db))
    if args.site_types in {"both", "resource"}:
        targets.extend(load_resource_targets(resource_db, resource_seed))

    targets = dedupe_targets(targets)
    if getattr(args, "filter_name", None):
        needle = args.filter_name.lower()
        targets = [t for t in targets if needle in t.name.lower()]
    targets = targets[: max(0, args.max_sites)] if args.max_sites > 0 else targets

    conn = connect_state_db(state_db)

    if args.sync_distillery_from_state:
        sync_rows = conn.execute(
            """
            SELECT id, name, root_url
            FROM sites
            WHERE site_type = 'distillery'
            ORDER BY COALESCE(last_crawled_at, '') DESC, name ASC
            """
        ).fetchall()
        if args.filter_name:
            needle = args.filter_name.lower()
            sync_rows = [r for r in sync_rows if needle in str(r["name"]).lower()]
        if args.max_sites > 0:
            sync_rows = sync_rows[: args.max_sites]

        if not sync_rows:
            print("No distillery sites found in state DB for sync mode.")
            return

        updated = 0
        failed = 0
        for idx, row in enumerate(sync_rows, start=1):
            target = SiteTarget(site_type="distillery", name=str(row["name"]), url=str(row["root_url"]))
            print(f"[{idx}/{len(sync_rows)}] Sync distillery summary: {target.name}")
            try:
                result = _sync_distillery_summary_from_state(
                    state_conn=conn,
                    distillery_db_path=distillery_db,
                    site_id=int(row["id"]),
                    target=target,
                    lmstudio_url=args.lmstudio_url,
                    lmstudio_model=args.lmstudio_model,
                    lmstudio_extract_timeout=args.lmstudio_extract_timeout,
                )
                if result.get("updated"):
                    updated += 1
                    print(
                        f"  updated distillery_id={result.get('distillery_id')} "
                        f"pages={result.get('pages_used')} terms={result.get('search_terms_count')}"
                    )
                    print(json.dumps(result.get("metadata", {}), ensure_ascii=True, indent=2))
                else:
                    failed += 1
                    print(f"  skipped: {result.get('reason', 'unknown')}")
            except Exception as exc:
                failed += 1
                print(f"  failed: {type(exc).__name__}: {exc}")

        print("\nDistillery sync complete")
        print(json.dumps({"updated": updated, "not_updated_or_failed": failed}, ensure_ascii=True, indent=2))
        return

    if not targets:
        print("No crawl targets found. Check DB paths and seed data.")
        return

    per_site: list[dict[str, Any]] = []
    try:
        for idx, target in enumerate(targets, start=1):
            print(f"[{idx}/{len(targets)}] Crawling {target.site_type}: {target.name} ({target.url})")
            try:
                stats = crawl_site(
                    conn=conn,
                    target=target,
                    distillery_db_path=distillery_db,
                    markdown_dir=markdown_dir,
                    max_pages_per_site=args.max_pages_per_site,
                    recrawl_days=args.recrawl_days,
                    force_rescrape=args.force_rescrape,
                    page_timeout=args.page_timeout,
                    lmstudio_url=args.lmstudio_url,
                    lmstudio_model=args.lmstudio_model,
                    lmstudio_extract_timeout=args.lmstudio_extract_timeout,
                    throttle_seconds=args.throttle_seconds,
                    whisper_model_path=whisper_model_path,
                    whisper_executable=(args.whisper_executable.strip() or None),
                    max_audio_files_per_page=args.max_audio_files_per_page,
                    audio_transcribe_timeout=args.audio_transcribe_timeout,
                    parallel_page_loads=args.parallel_page_loads,
                    direct_fetch_timeout=args.direct_fetch_timeout,
                    cdp_url=args.cdp_url,
                    verbose_crawl=not args.quiet_crawl,
                    distillery_sync=not args.no_distillery_sync,
                )
                per_site.append(stats)
                print(
                    f"  pages={stats['pages_processed']} skipped={stats['pages_skipped']} "
                    f"failed={stats['pages_failed']} summarized={stats['pages_summarized']}"
                )
                sync_meta = stats.get("distillery_sync")
                if isinstance(sync_meta, dict) and stats.get("site_type") == "distillery":
                    print(
                        f"  distillery_sync updated={sync_meta.get('updated', False)} "
                        f"reason={sync_meta.get('reason', '')}"
                    )
                    if sync_meta.get("metadata"):
                        print(json.dumps(sync_meta.get("metadata", {}), ensure_ascii=True, indent=2))
            except Exception as exc:
                per_site.append(
                    {
                        "site_type": target.site_type,
                        "name": target.name,
                        "root_url": target.url,
                        "pages_processed": 0,
                        "pages_skipped": 0,
                        "pages_failed": 1,
                        "pages_summarized": 0,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"  failed: {type(exc).__name__}: {exc}")
    finally:
        conn.commit()

    run_summary = {
        "sites_processed": len(per_site),
        "sites_succeeded": sum(1 for row in per_site if int(row.get("pages_failed", 0)) == 0),
        "sites_failed": sum(1 for row in per_site if int(row.get("pages_failed", 0)) > 0),
        "pages_processed": sum(int(row.get("pages_processed", 0)) for row in per_site),
        "pages_skipped": sum(int(row.get("pages_skipped", 0)) for row in per_site),
        "pages_failed": sum(int(row.get("pages_failed", 0)) for row in per_site),
        "pages_summarized": sum(int(row.get("pages_summarized", 0)) for row in per_site),
    }

    write_run_report(report_path, run_summary, per_site)
    keyword_path = export_site_index(conn, output_path=keyword_report)

    print("\nRun complete")
    print(json.dumps(run_summary, ensure_ascii=True, indent=2))
    print(f"Report: {report_path}")
    print(f"Keyword index: {keyword_path}")


if __name__ == "__main__":
    main()
