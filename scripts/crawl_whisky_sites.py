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
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urldefrag, urlparse, urlunparse
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
    prefilter_rules: dict[str, Any] | None = None


_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "src",
}

_VOLATILE_QUERY_KEYS = {
    "chash",
    "comment_id",
    "reply_comment_id",
    "showcomment",
    "yoreviewspage",
}


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _merge_prefilter_rules(*rulesets: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for rules in rulesets:
        if not isinstance(rules, dict):
            continue
        for key, value in rules.items():
            if isinstance(value, list):
                existing = merged.get(key, [])
                if isinstance(existing, list):
                    merged[key] = _dedupe_strings([*existing, *(str(v) for v in value)])
                else:
                    merged[key] = _dedupe_strings([str(v) for v in value])
            elif isinstance(value, dict):
                existing_dict = merged.get(key, {})
                if isinstance(existing_dict, dict):
                    merged[key] = {**existing_dict, **value}
                else:
                    merged[key] = dict(value)
            else:
                merged[key] = value
    return merged


def load_resource_prefilter_rules(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"global": {}, "domains": {}, "sites": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"global": {}, "domains": {}, "sites": {}}
    if not isinstance(payload, dict):
        return {"global": {}, "domains": {}, "sites": {}}
    return {
        "global": payload.get("global", {}) if isinstance(payload.get("global"), dict) else {},
        "domains": payload.get("domains", {}) if isinstance(payload.get("domains"), dict) else {},
        "sites": payload.get("sites", {}) if isinstance(payload.get("sites"), dict) else {},
    }


def resolve_resource_prefilter_rules(name: str, url: str, all_rules: dict[str, Any]) -> dict[str, Any]:
    global_rules = all_rules.get("global", {}) if isinstance(all_rules.get("global"), dict) else {}
    sites = all_rules.get("sites", {}) if isinstance(all_rules.get("sites"), dict) else {}
    domains = all_rules.get("domains", {}) if isinstance(all_rules.get("domains"), dict) else {}

    site_rules = sites.get(name, {}) if isinstance(sites.get(name), dict) else {}

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    host_bare = host.removeprefix("www.")
    domain_rules = domains.get(host, {}) if isinstance(domains.get(host), dict) else {}
    bare_domain_rules = domains.get(host_bare, {}) if isinstance(domains.get(host_bare), dict) else {}

    return _merge_prefilter_rules(global_rules, domain_rules, bare_domain_rules, site_rules)


class LMStudioUnavailableError(RuntimeError):
    pass


def _http_error_details(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    return f"HTTP {exc.code}: {body or exc.reason}"


def _is_terminal_lmstudio_error(exc: Exception) -> bool:
    if isinstance(exc, LMStudioUnavailableError):
        return True
    if isinstance(exc, URLError):
        return True
    if isinstance(exc, HTTPError):
        details = _http_error_details(exc).lower()
        return exc.code >= 500 or any(
            token in details
            for token in [
                "model",
                "not found",
                "unknown",
                "not loaded",
                "does not exist",
                "no such model",
                "unavailable",
                "not known",
            ]
        )
    message = str(exc).lower()
    return any(
        token in message
        for token in [
            "connection refused",
            "failed to establish a new connection",
            "name or service not known",
            "temporary failure in name resolution",
            "model not found",
            "unknown model",
            "model is not loaded",
            "model not loaded",
            "no such model",
            "not known",
        ]
    )


def _raise_if_terminal_lmstudio_error(exc: Exception) -> None:
    if not _is_terminal_lmstudio_error(exc):
        return
    if isinstance(exc, HTTPError):
        detail = _http_error_details(exc)
    else:
        detail = str(exc)
    raise LMStudioUnavailableError(f"LM Studio unavailable: {detail}") from exc


def _model_aliases(model_name: str) -> set[str]:
    cleaned = str(model_name or "").strip()
    if not cleaned:
        return set()
    aliases = {cleaned}
    if "/" in cleaned:
        aliases.add(cleaned.split("/")[-1])
    return aliases


def ensure_lmstudio_models_available(base_url: str, required_models: list[str], timeout_seconds: int = 20) -> None:
    wanted = [m.strip() for m in required_models if str(m or "").strip()]
    if not wanted:
        return

    req = Request(base_url.rstrip("/") + "/models", method="GET")
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        _raise_if_terminal_lmstudio_error(exc)
        raise LMStudioUnavailableError(f"Unable to query LM Studio models: {exc}") from exc

    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        raise LMStudioUnavailableError("LM Studio /models response missing data array")

    available_ids = {
        str(item.get("id", "")).strip()
        for item in raw_models
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    available_aliases: set[str] = set()
    for model_id in available_ids:
        available_aliases.update(_model_aliases(model_id))

    missing = [model for model in wanted if not (_model_aliases(model) & available_aliases)]
    if missing:
        available_preview = ", ".join(sorted(available_ids)[:20])
        raise LMStudioUnavailableError(
            "Required LM Studio model(s) not available: "
            f"{', '.join(missing)}. Available: {available_preview or 'none'}"
        )


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
            metadata_taxonomy_json TEXT,
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
    if "metadata_taxonomy_json" not in existing_cols:
        additions.append(("metadata_taxonomy_json", "TEXT"))
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


def load_resource_targets(db_path: Path, seed_path: Path, prefilter_rules_path: Path) -> list[SiteTarget]:
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
    all_prefilter_rules = load_resource_prefilter_rules(prefilter_rules_path)
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
                    prefilter_rules=resolve_resource_prefilter_rules(str(r["name"]), str(r["url"]), all_prefilter_rules),
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
                targets.append(
                    SiteTarget(
                        site_type="resource",
                        name=name,
                        url=url,
                        podcast_rss=podcast_rss,
                        prefilter_rules=resolve_resource_prefilter_rules(name, url, all_prefilter_rules),
                    )
                )

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
        "Always write the summary in English. If the source text is not in English, translate it to natural English while preserving specific names, product names, quoted terms, and factual details. "
        "If useful, you may include distillery-relevant sections such as Key Facts, Production Signals, Commercial Signals, and Risks/Unknowns, but only when they genuinely match the source material. "
        "Do not omit important source details just to fit pre-defined headings. "
        "keywords should be an array of 8 to 20 lower-case English topical phrases focused on whisky, distilling, regulation, history, production, maturation, sensory, and brand positioning."
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

    metadata_taxonomy = _metadata_from_text_fallback(text=text, page_title=page_title)

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
        "metadata_taxonomy": metadata_taxonomy,
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
            "people": metadata_taxonomy.get("people", []),
            "companies": metadata_taxonomy.get("company_names", []),
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


def _normalize_people_records(raw_people: Any) -> list[dict[str, str]]:
    if not isinstance(raw_people, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw_people[:120]:
        if isinstance(item, str):
            name = normalize_ws(item)
            role = ""
            distillery = ""
        elif isinstance(item, dict):
            name = normalize_ws(str(item.get("name", "")))
            role = normalize_ws(str(item.get("role", "")))
            distillery = normalize_ws(str(item.get("distillery", "")))
        else:
            continue
        if not name:
            continue
        key = (name.lower(), role.lower(), distillery.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "role": role, "distillery": distillery})
    return out


def _normalize_metadata_taxonomy(raw_meta: Any) -> dict[str, Any]:
    meta = raw_meta if isinstance(raw_meta, dict) else {}
    return {
        "distillery_names": _coerce_string_list(meta.get("distillery_names", []), limit=120),
        "people": _normalize_people_records(meta.get("people", [])),
        "product_names": _coerce_string_list(meta.get("product_names", []), limit=160),
        "company_names": _coerce_string_list(meta.get("company_names", []), limit=120),
        "flavor_profile_words": _coerce_string_list(meta.get("flavor_profile_words", []), limit=160),
        "chemical_names": _coerce_string_list(meta.get("chemical_names", []), limit=120),
        "distillery_tool_names": _coerce_string_list(meta.get("distillery_tool_names", []), limit=120),
        "glossary_terms": _coerce_string_list(meta.get("glossary_terms", []), limit=160),
    }


def _metadata_from_text_fallback(text: str, page_title: str) -> dict[str, Any]:
    full = f"{page_title}\n{text}"

    chem_pattern = re.compile(
        r"\b(?:esters?|aldehydes?|phenols?|lactones?|tannins?|vanillin|guaiacol|furfural|ethanol|methanol|acetate|congeners?)\b",
        flags=re.IGNORECASE,
    )
    flavor_pattern = re.compile(
        r"\b(?:smoky|peaty|vanilla|caramel|toffee|spice|spicy|fruity|floral|oak|oaky|citrus|honey|chocolate|nutty|briny|malty)\b",
        flags=re.IGNORECASE,
    )
    tool_pattern = re.compile(
        r"\b(?:pot still|column still|washback|mash tun|lautering|fermenter|condenser|worm tub|thumper|hydrometer|densitometer|cask|barrel|char level)\b",
        flags=re.IGNORECASE,
    )

    chemicals = sorted({normalize_ws(m.group(0).lower()) for m in chem_pattern.finditer(full)})
    flavors = sorted({normalize_ws(m.group(0).lower()) for m in flavor_pattern.finditer(full)})
    tools = sorted({normalize_ws(m.group(0).lower()) for m in tool_pattern.finditer(full)})

    people: list[dict[str, str]] = []
    people_pattern = re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,\s*(master distiller|distiller|founder|blender|owner|ceo|manager|head distiller)\b"
    )
    seen_people: set[tuple[str, str]] = set()
    for match in people_pattern.finditer(full):
        name = normalize_ws(match.group(1))
        role = normalize_ws(match.group(2).lower())
        key = (name.lower(), role)
        if key in seen_people:
            continue
        seen_people.add(key)
        people.append({"name": name, "role": role, "distillery": ""})

    return {
        "distillery_names": [],
        "people": people,
        "product_names": [],
        "company_names": [],
        "flavor_profile_words": flavors[:100],
        "chemical_names": chemicals[:100],
        "distillery_tool_names": tools[:100],
        "glossary_terms": [],
    }


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
        "Mark as True only if both conditions are met: "
        "(1) the page contains information that is genuinely relevant to whisky, whisky production, spirits regulation, distilling science, tasting, products, markets, or distilleries; and "
        "(2) the page contains sought metadata or significant factual content that would be worth preserving in a whisky research database. "
        "Examples of sought metadata or significant factual content include: product details, distillery details, labeling rules, production rules, maturation facts, ingredient/grain details, still or cask details, excise/compliance rules specific to spirits, technical findings, historical facts, review content, pricing, release details, or concrete market facts. "
        "Mark as False for low-value pages even if they mention spirits in passing. "
        "False pages include: login forms, member benefits, account settings, navigation pages, legal/privacy pages, general company or agency home pages, contact/about pages, accessibility pages, site maps, press or publication index pages, category landing pages, section entry pages, article listing pages, map hubs, and pages that mainly point to other sections without presenting meaningful facts themselves. "
        "Be strict: if a page is mostly a hub, overview, menu, or directory, mark False unless it also contains substantial whisky-relevant facts on the page itself."
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
    except Exception as exc:
        _raise_if_terminal_lmstudio_error(exc)
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
        "Required keys: summary_markdown, summary_text, distillery_facts, resource_facts, product_facts, reviews, metadata_taxonomy, keyword_sets, legacy_sections, db_enrichment_candidates, blog_topic_suggestions, course_material_candidates, keywords. "
        "All output text must be in English. If the source content is not in English, translate it to natural English while preserving proper nouns, product names, quoted phrases, and exact factual details. "
        "summary_markdown: concise faithful markdown summary focused on source substance, not metadata schema, written in English. "
        "summary_text: concise English plain-text summary of the same page substance. "
        "distillery_facts/resource_facts: arrays of concrete factual statements useful for database updates, written in English. "
        "product_facts: array of objects with keys name, facts, price_mentions, purchase_links, source_url, confidence. Include pricing and purchase links whenever present. "
        "reviews: array of full review objects with keys review_text, reviewer, rating, review_date, product_name, product_url, source_url, confidence. Translate review_text to English if needed while preserving meaning. "
        "metadata_taxonomy: object with keys distillery_names, people, product_names, company_names, flavor_profile_words, chemical_names, distillery_tool_names, glossary_terms. "
        "people must be array of objects with keys name, role, distillery. "
        "keyword_sets must contain arrays: flavour_descriptions, glossary_terms, production_terms, chemistry_terms_observations. "
        "legacy_sections must contain arrays: key_facts, production_signals, commercial_signals, risks_unknowns, but keep them optional/empty when not present. "
        "db_enrichment_candidates must contain objects/arrays for distilleries, resources, products, people, companies. "
        "blog_topic_suggestions and course_material_candidates should be concise evidence-driven suggestions. "
        "keywords should be 12-80 lower-case English phrases covering product, process, flavour, regulation, and chemistry where present."
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

    metadata_taxonomy = _normalize_metadata_taxonomy(parsed.get("metadata_taxonomy", {}))
    if not any(metadata_taxonomy.get(key) for key in [
        "distillery_names",
        "people",
        "product_names",
        "company_names",
        "flavor_profile_words",
        "chemical_names",
        "distillery_tool_names",
        "glossary_terms",
    ]):
        metadata_taxonomy = _metadata_from_text_fallback(text, page_title)

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
            "people": metadata_taxonomy.get("people", []),
            "companies": metadata_taxonomy.get("company_names", []),
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
        "metadata_taxonomy": metadata_taxonomy,
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
        "Return strict JSON with keys: short_description, long_description, key_focus, source_headers, notes, search_terms, metadata, products, people. "
        "All output text must be in English. If page summaries include non-English material, translate and normalize it into natural English while preserving proper nouns and exact factual claims. "
        "short_description must be one concise sentence for list views. "
        "long_description must be detailed markdown summary of the full site synthesis. "
        "key_focus should be 3 to 8 compact comma-separated focus phrases suitable for a table field. "
        "source_headers should be a compact comma-separated list of dominant source themes. "
        "notes should be concise operational context that avoids repeating metadata. "
        "search_terms must be 12 to 40 lower-case English topical phrases for search matching. "
        "metadata must be an object with these keys: "
        "product_lines, whisky_styles, grain_mentions, still_mentions, cask_mentions, maturation_mentions, "
        "visitor_experiences, commerce_features, compliance_signals, location_markers, claimed_founders_or_dates, "
        "distillery_names, company_names, flavor_profile_words, chemical_names, distillery_tool_names, glossary_terms, "
        "age_gate_present, ecommerce_present, tours_or_bookings_present, awards_or_press_present. "
        "products must be array of objects with keys name, distillery, image, purchase_link, price, notes. "
        "people must be array of objects with keys name, role, distillery. "
        "List values should be lower-case English phrase arrays; booleans should be true/false."
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
            "metadata_taxonomy": page.get("metadata_taxonomy", {}),
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
        "distillery_names": _coerce_string_list(metadata.get("distillery_names", [])),
        "company_names": _coerce_string_list(metadata.get("company_names", [])),
        "flavor_profile_words": _coerce_string_list(metadata.get("flavor_profile_words", [])),
        "chemical_names": _coerce_string_list(metadata.get("chemical_names", [])),
        "distillery_tool_names": _coerce_string_list(metadata.get("distillery_tool_names", [])),
        "glossary_terms": _coerce_string_list(metadata.get("glossary_terms", [])),
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

    long_description = str(parsed.get("long_description", "")).strip()
    if not long_description:
        top_titles = [str(p.get("title", "")).strip() for p in page_payloads if str(p.get("title", "")).strip()]
        long_description = (
            f"{distillery_name} crawl synthesis from {len(page_payloads)} pages. "
            f"Primary site themes include: {', '.join(top_titles[:4])}."
        )

    short_description = normalize_ws(str(parsed.get("short_description", "")))
    if not short_description:
        short_description = normalize_ws(long_description)[:220]

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

    raw_products = parsed.get("products", [])
    products: list[dict[str, str]] = []
    if isinstance(raw_products, list):
        for item in raw_products[:200]:
            if not isinstance(item, dict):
                continue
            name = normalize_ws(str(item.get("name", "")))
            if not name:
                continue
            products.append(
                {
                    "name": name,
                    "distillery": normalize_ws(str(item.get("distillery", ""))),
                    "image": normalize_ws(str(item.get("image", ""))),
                    "purchase_link": normalize_ws(str(item.get("purchase_link", ""))),
                    "price": normalize_ws(str(item.get("price", ""))),
                    "notes": normalize_ws(str(item.get("notes", ""))),
                }
            )

    people = _normalize_people_records(parsed.get("people", []))

    return {
        "short_description": short_description,
        "long_description": long_description,
        "key_focus": key_focus,
        "source_headers": source_headers,
        "notes": notes,
        "search_terms": search_terms,
        "metadata": clean_metadata,
        "products": products,
        "people": people,
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

    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        # Some LM responses contain invalid backslash escapes (e.g. "\x" or "\_").
        # Repair only those invalid escapes and retry to avoid dropping entire summaries.
        if "Invalid \\escape" not in str(exc):
            raise
        repaired = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", value)
        return json.loads(repaired)


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

    filtered_qs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        lower_key = key.lower()
        if lower_key.startswith("utm_"):
            continue
        if lower_key in _TRACKING_QUERY_KEYS or lower_key in _VOLATILE_QUERY_KEYS:
            continue
        filtered_qs.append((key, value))
    filtered_qs.sort()

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(filtered_qs, doseq=True),
            "",
        )
    )


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
    progress_log: Callable[[str], None] | None = None,
    _model_cache: dict = {},  # noqa: B006 - intentional mutable default for caching
) -> str:
    """Transcribe audio using the openai-whisper Python library (no subprocess required).

    The loaded model is cached in ``_model_cache`` to avoid re-loading between calls.
    """
    try:
        import whisper as _whisper  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("openai-whisper Python package not installed") from exc

    if progress_log:
        progress_log(f"  [transcribe] downloading audio: {audio_url}")
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
            if progress_log:
                progress_log(f"  [transcribe] loading whisper model: {model_name}")
            _model_cache[model_name] = _whisper.load_model(model_name)
        if progress_log:
            progress_log("  [transcribe] starting model inference")
        heartbeat = _TranscribeHeartbeat(progress_log, "python-whisper transcription") if progress_log else None
        if heartbeat:
            heartbeat.start()
        try:
            transcription = _model_cache[model_name].transcribe(str(input_path))
        finally:
            if heartbeat:
                heartbeat.stop()
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
    progress_log: Callable[[str], None] | None = None,
) -> str:
    if progress_log:
        progress_log(f"  [transcribe] downloading audio: {audio_url}")
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
            heartbeat = _TranscribeHeartbeat(progress_log, "whisper-cli transcription") if progress_log else None
            if heartbeat:
                heartbeat.start()
            try:
                subprocess.run(cmd, check=True, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            finally:
                if heartbeat:
                    heartbeat.stop()
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
        heartbeat = _TranscribeHeartbeat(progress_log, "whisper transcription") if progress_log else None
        if heartbeat:
            heartbeat.start()
        try:
            subprocess.run(cmd, check=True, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            if heartbeat:
                heartbeat.stop()
        txt_path = tmp_dir / f"{input_path.stem}.txt"
        if not txt_path.exists():
            raise RuntimeError("Whisper command did not produce transcript file")
        return txt_path.read_text(encoding="utf-8", errors="replace").strip()


class _TranscribeHeartbeat:
    def __init__(
        self,
        log_func: Callable[[str], None] | None,
        label: str,
        interval_seconds: int = 20,
    ) -> None:
        self._log = log_func
        self._label = label
        self._interval = interval_seconds
        self._started = time.monotonic()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="transcribe-heartbeat", daemon=True)

    def start(self) -> None:
        if self._log:
            self._log(f"  [transcribe] {self._label} started")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        if self._log:
            elapsed = int(time.monotonic() - self._started)
            self._log(f"  [transcribe] {self._label} finished in ~{elapsed}s")

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            if self._log:
                elapsed = int(time.monotonic() - self._started)
                self._log(f"  [transcribe] {self._label} still running (~{elapsed}s elapsed)")


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
        "Always write the summary in English. If the transcript is not in English, translate it to natural English while preserving speaker names, brand names, product names, and exact factual claims. "
        "You may use sections such as Key Takeaways, Production Signals, Commercial Signals, or Risks/Unknowns when they naturally fit, but they are optional. "
        "keywords must be 8 to 20 lower-case English topical phrases."
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


def should_skip_path(url: str, target: SiteTarget | None = None) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".mp4", ".mp3"]):
        return True

    if target and target.site_type == "resource" and isinstance(target.prefilter_rules, dict):
        rules = target.prefilter_rules
        url_lower = url.lower()

        deny_query_params = {
            str(param).lower().strip()
            for param in rules.get("deny_query_params", [])
            if str(param).strip()
        }
        if deny_query_params:
            query_keys = {key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
            if query_keys & deny_query_params:
                return True

        for pattern in rules.get("deny_url_regex", []):
            if re.search(str(pattern), url_lower):
                return True

        allow_url_regex = [str(pattern) for pattern in rules.get("allow_url_regex", []) if str(pattern).strip()]
        if allow_url_regex and path not in {"", "/"}:
            if not any(re.search(pattern, url_lower) for pattern in allow_url_regex):
                return True

    return False


def crawl_link_priority(url: str) -> tuple[int, int, int, str]:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    path_segments = [segment for segment in path.split("/") if segment]
    is_pdf = path.endswith(".pdf")

    priority_terms = {
        "journal": 0,
        "blog": 0,
        "article": 0,
        "articles": 0,
        "news": 0,
        "stories": 1,
        "story": 1,
        "press": 1,
        "post": 1,
        "posts": 1,
        "editorial": 1,
        "insights": 1,
    }

    best_rank = 3
    for segment in path_segments:
        for term, rank in priority_terms.items():
            if term in segment:
                best_rank = min(best_rank, rank)

    if best_rank == 3:
        for term, rank in priority_terms.items():
            if term in query:
                best_rank = min(best_rank, rank)

    return (0 if is_pdf else 1, best_rank, len(path_segments), url)


def sort_links_for_crawl(links: list[str]) -> list[str]:
    return sorted(links, key=crawl_link_priority)


def sort_queue_for_crawl(queue: list[tuple[str, int]]) -> None:
    queue.sort(key=lambda item: (crawl_link_priority(item[0]), item[1]))


def page_has_preservable_value_signals(url: str, title: str, text: str) -> bool:
    haystack = " ".join([url.lower(), (title or "").lower(), (text or "")[:5000].lower()])

    subject_patterns = [
        r"whisk(?:y|ey)",
        r"spirits?",
        r"distill",
        r"liquor",
        r"sake",
        r"shochu",
        r"malt",
        r"barley",
        r"grain",
        r"cask",
        r"oak",
        r"maturation",
        r"ferment",
        r"still",
    ]
    detail_patterns = [
        r"labell?ing",
        r"standard",
        r"definition",
        r"regulation",
        r"rule",
        r"requirement",
        r"guideline",
        r"notice",
        r"technical",
        r"research",
        r"analysis",
        r"excise",
        r"tax rate",
        r"tariff",
        r"age statement",
        r"specification",
        r"production process",
        r"maturation",
        r"distillation",
        r"fermentation",
        r"review",
        r"tasting note",
        r"release detail",
    ]

    has_subject = any(re.search(pattern, haystack) for pattern in subject_patterns)
    has_detail = any(re.search(pattern, haystack) for pattern in detail_patterns)
    return has_subject and has_detail


def should_preexclude_page(url: str, title: str, text: str, target: SiteTarget | None = None) -> bool:
    url_lower = url.lower()
    title_lower = (title or "").lower()
    rules = target.prefilter_rules if target and isinstance(target.prefilter_rules, dict) else {}

    strong_url_patterns = [
        # Account / auth
        r"/customer/account", r"/account/login", r"/account/register",
        r"/login", r"/logout", r"/signin", r"/signup", r"/register",
        r"/forgot-password", r"/reset-password", r"/auth/",
        # Member / subscription admin
        r"/member-benefits", r"/membership", r"/subscribe", r"/subscription",
        r"/my-account", r"/my-profile", r"/dashboard",
        # Commerce / cart
        r"/cart", r"/checkout", r"/order", r"/wishlist",
        # Legal / policy
        r"/privacy", r"/terms", r"/cookie", r"/legal", r"/gdpr",
        # Generic admin / utility
        r"/sitemap", r"/search\?", r"/404", r"/contact",
        r"/accessibility",
    ]
    strong_title_patterns = [
        r"log in", r"sign in", r"create account", r"member benefits",
        r"my account", r"shopping cart", r"checkout", r"404",
        r"privacy policy", r"terms of service", r"cookie policy",
        r"accessibility",
    ]
    for pattern in strong_url_patterns:
        if re.search(pattern, url_lower):
            return True
    for pattern in strong_title_patterns:
        if re.search(pattern, title_lower):
            return True

    listing_url_patterns = [
        r"/tag/",
        r"/category/",
        r"/archive(?:s)?(?:/|$)",
        r"/search(?:/|\?)",
        r"[?&]p=\d+",
        r"/page/\d+/?$",
        r"/newsroom(?:/|$)",
        r"/latest-news(?:/|$)",
        r"[?&]yoreviewspage=\d+",
        r"[?&]showcomment=",
    ]
    listing_title_patterns = [
        r"\barchives?\b",
        r"\bsearch\b",
        r"\blatest news\b",
        r"\bnewsletter\b",
        r"\bnewsroom\b",
        r"\bpage\s+\d+\b",
    ]
    is_listing_like = any(re.search(pattern, url_lower) for pattern in listing_url_patterns)
    if not is_listing_like:
        is_listing_like = any(re.search(pattern, title_lower) for pattern in listing_title_patterns)

    min_visible_text_chars = int(rules.get("min_visible_text_chars", 450) or 450)
    trimmed_text = normalize_ws(text)
    has_preservable_value = page_has_preservable_value_signals(url, title, text)

    chrome_markers = [
        str(v).lower()
        for v in rules.get("chrome_text_markers", [])
        if str(v).strip()
    ]
    if not chrome_markers:
        chrome_markers = [
            "skip to content",
            "toggle menu",
            "we use essential cookies",
            "close products",
            "view my delivery box",
            "community login",
            "where to buy",
            "from the editors",
        ]
    chrome_hits = sum(1 for marker in chrome_markers if marker in trimmed_text.lower())

    if is_listing_like and not has_preservable_value:
        return True

    if len(trimmed_text) < min_visible_text_chars and not has_preservable_value:
        return True

    if chrome_hits >= 2 and not has_preservable_value:
        return True

    low_value_url_patterns = [
        r"/(?:index|home)(?:\.|/|$)",
        r"/about(?:[-_/].*)?$",
        r"/about-us(?:/|$)",
        r"/organization(?:/|$)",
        r"/publication(?:/|$)",
        r"/press(?:/|$)",
        r"/release(?:/|$)",
        r"/related-sites(?:/|$)",
        r"/call-center(?:/|$)",
        r"/taxes(?:/|$)",
        r"/report(?:[_/-]|$)",
        r"/map(?:[_/-]|$)",
    ]
    low_value_title_patterns = [
        r"about us",
        r"contact us",
        r"organization",
        r"publication",
        r"press release",
        r"site map",
        r"page top",
        r"related sites",
        r"call center",
        r"information for taxpayers",
        r"national tax agency",
    ]

    is_low_value_theme = any(re.search(pattern, url_lower) for pattern in low_value_url_patterns)
    if not is_low_value_theme:
        is_low_value_theme = any(re.search(pattern, title_lower) for pattern in low_value_title_patterns)

    if not is_low_value_theme:
        return False

    return not has_preservable_value


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


_CDP_BROWSER_PROCESS: subprocess.Popen[str] | None = None


def _cdp_version_endpoint(cdp_url: str) -> str:
    parsed = urlparse(cdp_url)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else cdp_url.rstrip("/")
    return base.rstrip("/") + "/json/version"


def is_cdp_available(cdp_url: str, timeout_seconds: float = 2.0) -> bool:
    endpoint = _cdp_version_endpoint(cdp_url)
    req = Request(endpoint, headers={"User-Agent": "whisky-crawler/1.0"})
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        return bool(payload.get("webSocketDebuggerUrl"))
    except Exception:
        return False


def _select_chrome_binary() -> str | None:
    for env_name in ["CHROME_BIN", "CHROMIUM_BIN", "GOOGLE_CHROME_BIN"]:
        candidate = os.environ.get(env_name, "").strip()
        if candidate and Path(candidate).exists():
            return candidate
    for candidate in ["chromium-browser", "chromium", "google-chrome", "google-chrome-stable"]:
        binary = shutil.which(candidate)
        if binary:
            return binary
    return None


def ensure_cdp_browser(cdp_url: str, log: Callable[[str], None] | None = None) -> bool:
    global _CDP_BROWSER_PROCESS

    if is_cdp_available(cdp_url):
        return True

    parsed = urlparse(cdp_url)
    host = (parsed.hostname or "").lower()
    port = parsed.port or 9222
    if host not in {"127.0.0.1", "localhost", "::1"}:
        if log:
            log(f"  [cdp] endpoint unavailable and host is non-local ({host}); skipping auto-start")
        return False

    if _CDP_BROWSER_PROCESS is not None and _CDP_BROWSER_PROCESS.poll() is None:
        for _ in range(20):
            if is_cdp_available(cdp_url):
                return True
            time.sleep(0.5)
        return False

    chrome_binary = _select_chrome_binary()
    if not chrome_binary:
        if log:
            log("  [cdp] no Chrome/Chromium binary found for auto-start")
        return False

    args = [
        chrome_binary,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--user-data-dir=/tmp/whisky-cdp-profile",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--headless=new",
        "about:blank",
    ]

    try:
        _CDP_BROWSER_PROCESS = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
        )
        if log:
            log(f"  [cdp] auto-started browser for {host}:{port} using {Path(chrome_binary).name}")
    except Exception as exc:
        if log:
            log(f"  [cdp] failed to auto-start browser: {type(exc).__name__}: {exc}")
        return False

    for _ in range(40):
        if is_cdp_available(cdp_url):
            return True
        time.sleep(0.5)

    if log:
        log("  [cdp] browser started but endpoint did not become ready in time")
    return False


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


def _render_metadata_markdown(metadata_taxonomy: dict[str, Any], blog_topics: list[str]) -> str:
    parts: list[str] = ["# Page Metadata", ""]

    def _add_section(title: str, values: list[str]) -> None:
        cleaned = [normalize_ws(v) for v in values if normalize_ws(v)]
        if not cleaned:
            return
        parts.append(f"## {title}")
        for item in cleaned[:200]:
            parts.append(f"- {item}")
        parts.append("")

    def _add_people(people: list[dict[str, str]]) -> None:
        if not people:
            return
        parts.append("## People")
        for item in people[:200]:
            name = normalize_ws(str(item.get("name", "")))
            role = normalize_ws(str(item.get("role", "")))
            distillery = normalize_ws(str(item.get("distillery", "")))
            if not name:
                continue
            line = name
            if role:
                line += f" | role: {role}"
            if distillery:
                line += f" | distillery: {distillery}"
            parts.append(f"- {line}")
        parts.append("")

    _add_section("Distillery Names", _coerce_string_list(metadata_taxonomy.get("distillery_names", []), limit=200))
    _add_people(_normalize_people_records(metadata_taxonomy.get("people", [])))
    _add_section("Product Names", _coerce_string_list(metadata_taxonomy.get("product_names", []), limit=300))
    _add_section("Company Names", _coerce_string_list(metadata_taxonomy.get("company_names", []), limit=200))
    _add_section("Flavor Profile Words", _coerce_string_list(metadata_taxonomy.get("flavor_profile_words", []), limit=300))
    _add_section("Chemical Names", _coerce_string_list(metadata_taxonomy.get("chemical_names", []), limit=200))
    _add_section("Distillery Tool Names", _coerce_string_list(metadata_taxonomy.get("distillery_tool_names", []), limit=200))
    _add_section("Glossary Terms", _coerce_string_list(metadata_taxonomy.get("glossary_terms", []), limit=300))
    _add_section("Blog Suggestions", _coerce_string_list(blog_topics, limit=200))

    if len(parts) <= 2:
        parts.extend(["## Notes", "- No metadata extracted for this page.", ""])
    return "\n".join(parts).strip() + "\n"


def write_page_metadata_output(
    base_dir: Path,
    site_slug: str,
    page_url: str,
    metadata_taxonomy: dict[str, Any],
    blog_topics: list[str],
) -> Path:
    parsed = urlparse(page_url)
    path_slug = slugify((parsed.path or "home").replace("/", "-")) or "home"
    file_path = base_dir / site_slug / f"{path_slug}-metadata.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(_render_metadata_markdown(metadata_taxonomy, blog_topics), encoding="utf-8")
    return file_path


def write_markdown_output(
    base_dir: Path,
    site_slug: str,
    page_url: str,
    title: str,
    summary_markdown: str,
    keywords: list[str],
    metadata_taxonomy: dict[str, Any] | None = None,
    blog_topics: list[str] | None = None,
) -> Path:
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
    if isinstance(metadata_taxonomy, dict):
        body.extend(
            [
                "## Metadata Taxonomy",
                f"- Distillery names: {len(_coerce_string_list(metadata_taxonomy.get('distillery_names', []), limit=999))}",
                f"- People: {len(_normalize_people_records(metadata_taxonomy.get('people', [])))}",
                f"- Product names: {len(_coerce_string_list(metadata_taxonomy.get('product_names', []), limit=999))}",
                f"- Company names: {len(_coerce_string_list(metadata_taxonomy.get('company_names', []), limit=999))}",
                f"- Flavor profile words: {len(_coerce_string_list(metadata_taxonomy.get('flavor_profile_words', []), limit=999))}",
                f"- Chemical names: {len(_coerce_string_list(metadata_taxonomy.get('chemical_names', []), limit=999))}",
                f"- Distillery tool names: {len(_coerce_string_list(metadata_taxonomy.get('distillery_tool_names', []), limit=999))}",
                f"- Glossary terms: {len(_coerce_string_list(metadata_taxonomy.get('glossary_terms', []), limit=999))}",
                "",
            ]
        )
    if blog_topics:
        body.append("## Blog Suggestions")
        for topic in _coerce_string_list(blog_topics, limit=120):
            body.append(f"- {topic}")
        body.append("")
    file_path.write_text("\n".join(body), encoding="utf-8")
    return file_path


def write_site_summary_outputs(
    base_dir: Path,
    site_slug: str,
    site_name: str,
    site_url: str,
    short_description: str,
    long_description: str,
    metadata: dict[str, Any],
    products: list[dict[str, Any]] | None = None,
    people: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    site_dir = base_dir / site_slug
    site_dir.mkdir(parents=True, exist_ok=True)

    summary_path = site_dir / "site-summary.md"
    summary_lines = [
        f"# {site_name} Site Summary",
        "",
        f"- URL: {site_url}",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Short Description",
        short_description.strip() or "",
        "",
        "## Long Description",
        long_description.strip() or "",
        "",
    ]
    if products:
        summary_lines.append("## Products")
        for item in products[:300]:
            if not isinstance(item, dict):
                continue
            name = normalize_ws(str(item.get("name", "")))
            if not name:
                continue
            line = f"- {name}"
            price = normalize_ws(str(item.get("price", "")))
            link = normalize_ws(str(item.get("purchase_link", "")))
            if price:
                line += f" | price: {price}"
            if link:
                line += f" | purchase: {link}"
            summary_lines.append(line)
        summary_lines.append("")
    if people:
        summary_lines.append("## People")
        for person in people[:300]:
            if not isinstance(person, dict):
                continue
            name = normalize_ws(str(person.get("name", "")))
            if not name:
                continue
            role = normalize_ws(str(person.get("role", "")))
            distillery = normalize_ws(str(person.get("distillery", "")))
            line = f"- {name}"
            if role:
                line += f" | role: {role}"
            if distillery:
                line += f" | distillery: {distillery}"
            summary_lines.append(line)
        summary_lines.append("")
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    metadata_path = site_dir / "site-metadata.md"
    metadata_path.write_text(
        _render_metadata_markdown(_normalize_metadata_taxonomy(metadata), []),
        encoding="utf-8",
    )
    return summary_path, metadata_path


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
    if "long_description" not in cols:
        additions.append(("long_description", "TEXT"))
    if "short_description" not in cols:
        additions.append(("short_description", "TEXT"))
    if "search_terms" not in cols:
        additions.append(("search_terms", "TEXT"))
    if "search_metadata_json" not in cols:
        additions.append(("search_metadata_json", "TEXT"))
    if "products_json" not in cols:
        additions.append(("products_json", "TEXT"))
    if "people_json" not in cols:
        additions.append(("people_json", "TEXT"))
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
            metadata_taxonomy_json,
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
                "metadata_taxonomy": _safe_json_loads(str(row["metadata_taxonomy_json"] or "{}"), {}),
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
        products_json = json.dumps(enrichment.get("products", []), ensure_ascii=True, sort_keys=True)
        people_json = json.dumps(enrichment.get("people", []), ensure_ascii=True, sort_keys=True)
        search_terms = ", ".join(enrichment["search_terms"])[:2500]

        dist_conn.execute(
            """
            UPDATE distilleries
            SET
                description = ?,
                long_description = ?,
                short_description = ?,
                key_focus = ?,
                source_headers = ?,
                notes = ?,
                search_terms = ?,
                search_metadata_json = ?,
                products_json = ?,
                people_json = ?,
                last_summarized_at = ?,
                study_status = CASE
                    WHEN COALESCE(study_status, '') IN ('', 'Not started')
                        THEN 'Crawl summarized'
                    ELSE study_status
                END
            WHERE id = ?
            """,
            (
                enrichment["long_description"],
                enrichment["long_description"],
                enrichment["short_description"],
                enrichment["key_focus"],
                enrichment["source_headers"],
                enrichment["notes"],
                search_terms,
                metadata_json,
                products_json,
                people_json,
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
            "short_description": enrichment.get("short_description", ""),
            "long_description": enrichment.get("long_description", ""),
            "products": enrichment.get("products", []),
            "people": enrichment.get("people", []),
            "metadata": enrichment["metadata"],
        }
    finally:
        dist_conn.close()


# ---------------------------------------------------------------------------
# Resource site synthesis
# ---------------------------------------------------------------------------

def lmstudio_summarize_resource_site(
    base_url: str,
    model: str,
    resource_name: str,
    resource_url: str,
    page_payloads: list[dict[str, Any]],
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    prompt = (
        "You synthesize whole-site research for a whisky knowledge resource in a searchable database. "
        "Return strict JSON with keys: short_description, long_description, summary_markdown, focus_area, search_terms, crawl_metadata. "
        "All output text must be in English. "
        "short_description: one concise sentence for list displays. "
        "long_description: one to four factual paragraphs covering what the resource site offers and who it serves. "
        "summary_markdown: concise markdown page (200-600 words) covering topic coverage, depth, audience, standout content, and practical value for craft distillers or students. Use headings and bullet lists where helpful. "
        "focus_area: 3 to 8 compact comma-separated phrases describing the site's primary areas of focus. "
        "search_terms: 12 to 40 lower-case English topical phrases for search matching. "
        "crawl_metadata: object with keys: "
        "  distillery_names (array), people (array of objects with name, role, distillery), product_names (array), company_names (array), "
        "  flavor_profile_words (array), chemical_names (array), distillery_tool_names (array), glossary_terms (array), "
        "  topics_covered (array of lower-case phrases), "
        "  content_types (array e.g. articles, whitepapers, videos, podcasts, technical guides), "
        "  audience_signals (array e.g. craft distillers, home enthusiasts, industry professionals, regulators), "
        "  chemistry_coverage (bool), regulation_coverage (bool), production_coverage (bool), "
        "  history_coverage (bool), tasting_coverage (bool), "
        "  has_downloadable_resources (bool), has_podcast (bool), has_courses (bool), "
        "  paywalled (bool), free_access (bool)."
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
            "blog_topics": _coerce_string_list(page.get("blog_topics", []), limit=20),
            "course_topics": _coerce_string_list(page.get("course_topics", []), limit=20),
            "resource_facts": _coerce_string_list(
                (page.get("summary_json") or {}).get("resource_facts", []), limit=20
            ),
            "metadata_taxonomy": page.get("metadata_taxonomy", {}),
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
                        "resource_name": resource_name,
                        "resource_url": resource_url,
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

    raw_meta = parsed.get("crawl_metadata")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    crawl_metadata = {
        "distillery_names": _coerce_string_list(meta.get("distillery_names", []), limit=80),
        "people": _normalize_people_records(meta.get("people", [])),
        "product_names": _coerce_string_list(meta.get("product_names", []), limit=120),
        "company_names": _coerce_string_list(meta.get("company_names", []), limit=80),
        "flavor_profile_words": _coerce_string_list(meta.get("flavor_profile_words", []), limit=120),
        "chemical_names": _coerce_string_list(meta.get("chemical_names", []), limit=80),
        "distillery_tool_names": _coerce_string_list(meta.get("distillery_tool_names", []), limit=80),
        "glossary_terms": _coerce_string_list(meta.get("glossary_terms", []), limit=120),
        "topics_covered": _coerce_string_list(meta.get("topics_covered", []), limit=60),
        "content_types": _coerce_string_list(meta.get("content_types", []), limit=20),
        "audience_signals": _coerce_string_list(meta.get("audience_signals", []), limit=20),
        "chemistry_coverage": bool(meta.get("chemistry_coverage", False)),
        "regulation_coverage": bool(meta.get("regulation_coverage", False)),
        "production_coverage": bool(meta.get("production_coverage", False)),
        "history_coverage": bool(meta.get("history_coverage", False)),
        "tasting_coverage": bool(meta.get("tasting_coverage", False)),
        "has_downloadable_resources": bool(meta.get("has_downloadable_resources", False)),
        "has_podcast": bool(meta.get("has_podcast", False)),
        "has_courses": bool(meta.get("has_courses", False)),
        "paywalled": bool(meta.get("paywalled", False)),
        "free_access": bool(meta.get("free_access", True)),
    }

    search_terms = _coerce_string_list(parsed.get("search_terms", []), limit=40)
    if not search_terms:
        aggregate: list[str] = []
        for page in page_payloads:
            aggregate.extend(_coerce_string_list(page.get("keywords", []), limit=20))
        search_terms = sorted(set(aggregate))[:40]

    long_description = str(parsed.get("long_description", "")).strip()
    if not long_description:
        top_titles = [str(p.get("title", "")).strip() for p in page_payloads if str(p.get("title", "")).strip()]
        long_description = (
            f"{resource_name} — crawl synthesis from {len(page_payloads)} pages. "
            f"Primary topics: {', '.join(top_titles[:4])}."
        )

    short_description = normalize_ws(str(parsed.get("short_description", "")))
    if not short_description:
        short_description = normalize_ws(long_description)[:220]

    summary_markdown = normalize_ws(str(parsed.get("summary_markdown", "")))
    if not summary_markdown:
        summary_markdown = long_description

    focus_area = normalize_ws(str(parsed.get("focus_area", "")))
    if not focus_area:
        focus_area = ", ".join(search_terms[:6])

    return {
        "short_description": short_description,
        "long_description": long_description,
        "summary_markdown": summary_markdown,
        "focus_area": focus_area,
        "search_terms": search_terms,
        "crawl_metadata": crawl_metadata,
    }


def _ensure_resource_summary_schema(conn: sqlite3.Connection) -> None:
    cols = {
        str(row[1]).lower()
        for row in conn.execute("PRAGMA table_info(resources)").fetchall()
    }
    additions: list[tuple[str, str]] = []
    if "description" not in cols:
        additions.append(("description", "TEXT"))
    if "long_description" not in cols:
        additions.append(("long_description", "TEXT"))
    if "short_description" not in cols:
        additions.append(("short_description", "TEXT"))
    if "summary_markdown" not in cols:
        additions.append(("summary_markdown", "TEXT"))
    if "search_terms" not in cols:
        additions.append(("search_terms", "TEXT"))
    if "last_summarized_at" not in cols:
        additions.append(("last_summarized_at", "TEXT"))
    if "crawl_metadata_json" not in cols:
        additions.append(("crawl_metadata_json", "TEXT"))
    if "products_json" not in cols:
        additions.append(("products_json", "TEXT"))
    if "people_json" not in cols:
        additions.append(("people_json", "TEXT"))
    for col, typ in additions:
        conn.execute(f"ALTER TABLE resources ADD COLUMN {col} {typ}")
    if additions:
        conn.commit()


def _find_resource_row(conn: sqlite3.Connection, target: SiteTarget) -> sqlite3.Row | None:
    row = conn.execute(
        "SELECT * FROM resources WHERE lower(name) = lower(?) LIMIT 1",
        (target.name,),
    ).fetchone()
    if row is not None:
        return row

    target_norm = _normalize_site_url(target.url)
    if not target_norm:
        return None
    rows = conn.execute("SELECT * FROM resources WHERE url LIKE 'http%'").fetchall()
    for candidate in rows:
        if _normalize_site_url(str(candidate["url"] or "")) == target_norm:
            return candidate
    return None


def _sync_resource_summary_from_state(
    state_conn: sqlite3.Connection,
    resource_db_path: Path,
    site_id: int,
    target: SiteTarget,
    lmstudio_url: str,
    lmstudio_model: str,
    lmstudio_extract_timeout: int,
) -> dict[str, Any]:
    rows = state_conn.execute(
        """
        SELECT
            url, title, description, summary_markdown, summary_json,
            extracted_products_json, metadata_taxonomy_json,
            keyword_sets_json, blog_topics_json, course_topics_json, keywords_json
        FROM pages
        WHERE site_id = ? AND crawl_status LIKE 'ok:%'
        ORDER BY COALESCE(last_crawled_at, '') DESC, url ASC
        """,
        (site_id,),
    ).fetchall()

    page_payloads: list[dict[str, Any]] = []
    for row in rows:
        keywords: list[str] = []
        try:
            keywords = _coerce_string_list(json.loads(str(row["keywords_json"] or "[]")), limit=25)
        except Exception:
            pass
        page_payloads.append(
            {
                "url": str(row["url"] or ""),
                "title": str(row["title"] or ""),
                "description": str(row["description"] or ""),
                "summary_markdown": str(row["summary_markdown"] or ""),
                "summary_json": _safe_json_loads(str(row["summary_json"] or "{}"), {}),
                "products": _safe_json_loads(str(row["extracted_products_json"] or "[]"), []),
                "metadata_taxonomy": _safe_json_loads(str(row["metadata_taxonomy_json"] or "{}"), {}),
                "keyword_sets": _safe_json_loads(str(row["keyword_sets_json"] or "{}"), {}),
                "blog_topics": _safe_json_loads(str(row["blog_topics_json"] or "[]"), []),
                "course_topics": _safe_json_loads(str(row["course_topics_json"] or "[]"), []),
                "keywords": keywords,
            }
        )

    if not page_payloads:
        return {"updated": False, "reason": "no_ok_pages", "site_name": target.name, "site_id": site_id}

    enrichment = lmstudio_summarize_resource_site(
        base_url=lmstudio_url,
        model=lmstudio_model,
        resource_name=target.name,
        resource_url=target.url,
        page_payloads=page_payloads,
        timeout_seconds=lmstudio_extract_timeout,
    )

    res_conn = sqlite3.connect(resource_db_path)
    res_conn.row_factory = sqlite3.Row
    try:
        _ensure_resource_summary_schema(res_conn)
        res_row = _find_resource_row(res_conn, target)
        if res_row is None:
            return {"updated": False, "reason": "resource_not_found", "site_name": target.name, "site_id": site_id}

        now = datetime.now(timezone.utc).isoformat()
        crawl_metadata_json = json.dumps(enrichment["crawl_metadata"], ensure_ascii=True, sort_keys=True)
        products_json = json.dumps(
            sorted(
                {
                    normalize_ws(str(p.get("name", "")))
                    for page in page_payloads
                    for p in (page.get("products", []) if isinstance(page.get("products", []), list) else [])
                    if isinstance(p, dict) and normalize_ws(str(p.get("name", "")))
                }
            ),
            ensure_ascii=True,
        )
        people_json = json.dumps(enrichment["crawl_metadata"].get("people", []), ensure_ascii=True, sort_keys=True)
        search_terms = ", ".join(enrichment["search_terms"])[:2500]

        res_conn.execute(
            """
            UPDATE resources
            SET
                description = ?,
                long_description = ?,
                short_description = ?,
                summary_markdown = ?,
                focus_area = ?,
                search_terms = ?,
                crawl_metadata_json = ?,
                products_json = ?,
                people_json = ?,
                last_summarized_at = ?
            WHERE id = ?
            """,
            (
                enrichment["long_description"],
                enrichment["long_description"],
                enrichment["short_description"],
                enrichment["summary_markdown"],
                enrichment["focus_area"],
                search_terms,
                crawl_metadata_json,
                products_json,
                people_json,
                now,
                int(res_row["id"]),
            ),
        )
        res_conn.commit()
        return {
            "updated": True,
            "site_name": target.name,
            "site_id": site_id,
            "resource_id": int(res_row["id"]),
            "pages_used": len(page_payloads),
            "search_terms_count": len(enrichment["search_terms"]),
            "short_description": enrichment.get("short_description", ""),
            "long_description": enrichment.get("long_description", ""),
            "crawl_metadata": enrichment["crawl_metadata"],
        }
    finally:
        res_conn.close()


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


def export_metadata_indexes(conn: sqlite3.Connection, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT
            s.site_type,
            s.name,
            p.url,
            p.metadata_taxonomy_json,
            p.blog_topics_json
        FROM pages p
        JOIN sites s ON s.id = p.site_id
        WHERE p.crawl_status LIKE 'ok:%'
        """
    ).fetchall()

    category_map: dict[str, dict[str, list[tuple[str, str, str]]]] = {
        "distillery_names": {},
        "people": {},
        "product_names": {},
        "company_names": {},
        "flavor_profile_words": {},
        "chemical_names": {},
        "distillery_tool_names": {},
        "glossary_terms": {},
        "blog_suggestions": {},
    }

    for row in rows:
        site_type = str(row["site_type"])
        site_name = str(row["name"])
        page_url = str(row["url"])
        meta = _normalize_metadata_taxonomy(_safe_json_loads(str(row["metadata_taxonomy_json"] or "{}"), {}))
        blog_topics = _coerce_string_list(_safe_json_loads(str(row["blog_topics_json"] or "[]"), []), limit=200)

        for key in [
            "distillery_names",
            "product_names",
            "company_names",
            "flavor_profile_words",
            "chemical_names",
            "distillery_tool_names",
            "glossary_terms",
        ]:
            for token in _coerce_string_list(meta.get(key, []), limit=300):
                category_map[key].setdefault(token, []).append((site_type, site_name, page_url))

        for person in _normalize_people_records(meta.get("people", [])):
            person_key = normalize_ws(person.get("name", ""))
            if not person_key:
                continue
            role = normalize_ws(person.get("role", ""))
            distillery = normalize_ws(person.get("distillery", ""))
            decorated = person_key
            if role:
                decorated += f" | role: {role}"
            if distillery:
                decorated += f" | distillery: {distillery}"
            category_map["people"].setdefault(decorated.lower(), []).append((site_type, site_name, page_url))

        for topic in blog_topics:
            category_map["blog_suggestions"].setdefault(topic, []).append((site_type, site_name, page_url))

    headings = {
        "distillery_names": "Distillery Names Index",
        "people": "People Index",
        "product_names": "Product Names Index",
        "company_names": "Company Names Index",
        "flavor_profile_words": "Flavor Profile Words Index",
        "chemical_names": "Chemical Names Index",
        "distillery_tool_names": "Distillery Tool Names Index",
        "glossary_terms": "Glossary Terms Index",
        "blog_suggestions": "Blog Suggestions Index",
    }
    filenames = {
        "distillery_names": "metadata_distillery_names.md",
        "people": "metadata_people.md",
        "product_names": "metadata_product_names.md",
        "company_names": "metadata_company_names.md",
        "flavor_profile_words": "metadata_flavor_profile_words.md",
        "chemical_names": "metadata_chemical_names.md",
        "distillery_tool_names": "metadata_distillery_tool_names.md",
        "glossary_terms": "metadata_glossary_terms.md",
        "blog_suggestions": "metadata_blog_suggestions.md",
    }

    output_files: list[Path] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    for key, bucket in category_map.items():
        out_path = output_dir / filenames[key]
        lines = [
            f"# {headings[key]}",
            "",
            f"Generated: {timestamp}",
            "",
        ]
        for token in sorted(bucket.keys()):
            lines.append(f"## {token}")
            for site_type, site_name, page_url in bucket[token][:80]:
                lines.append(f"- [{site_type}] {site_name}: {page_url}")
            lines.append("")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        output_files.append(out_path)

    return output_files


def crawl_site(
    conn: sqlite3.Connection,
    target: SiteTarget,
    distillery_db_path: Path,
    resource_db_path: Path,
    markdown_dir: Path,
    max_pages_per_site: int,
    recrawl_days: int,
    force_rescrape: bool,
    page_timeout: int,
    lmstudio_url: str,
    lmstudio_screen_model: str,
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
    resource_sync: bool,
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

    def classify_fetch_mode(url: str, existing_row: sqlite3.Row | None) -> str:
        # PDFs must always be fetched directly — CDP (browser) renders them as an
        # opaque PDF viewer with no extractable text.
        if urlparse(url).path.lower().endswith(".pdf"):
            return "direct"
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
        if cdp_url:
            ensure_cdp_browser(cdp_url, log=log)

        while queue and processed_pages < max_pages_per_site:
            pending: list[tuple[str, int, sqlite3.Row | None, str]] = []
            while queue and len(pending) < parallel_slots and (processed_pages + len(pending)) < max_pages_per_site:
                page_url, depth = queue.pop(0)
                if page_url in seen:
                    continue
                seen.add(page_url)

                if should_skip_path(page_url, target=target):
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
                    # Re-fetch PDFs that were previously captured via CDP with no text
                    # content — the browser PDF viewer yields empty DOM text.
                    is_pdf_url = urlparse(page_url).path.lower().endswith(".pdf")
                    if is_pdf_url and not str(existing["text_content"] or "").strip():
                        log(f"  [refetch] PDF with no prior text content: {page_url}")
                    else:
                        skipped_pages += 1
                        existing_links = json.loads(existing["extracted_links_json"] or "[]")
                        for link in sort_links_for_crawl(existing_links):
                            if same_domain(target.url, link) and link not in seen:
                                queue.append((link, depth + 1))
                        sort_queue_for_crawl(queue)
                        log(f"  [skip] fresh cache {page_url}")
                        continue

                pending.append((page_url, depth, existing, classify_fetch_mode(page_url, existing)))

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
                            ensure_cdp_browser(cdp_url, log=log)
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
                            ensure_cdp_browser(cdp_url, log=log)
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
                            if should_skip_path(normalized, target=target):
                                continue
                            normalized_links.append(normalized)

                        unique_links = []
                        seen_links: set[str] = set()
                        for link in sort_links_for_crawl(normalized_links):
                            if link in seen_links:
                                continue
                            seen_links.add(link)
                            unique_links.append(link)
                            if link not in seen:
                                queue.append((link, depth + 1))
                        sort_queue_for_crawl(queue)

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

                        total_audio = len(audio_urls)
                        for audio_index, audio_url in enumerate(audio_urls, start=1):
                            if not use_python_api and not whisper_bin:
                                log("  [transcribe] No Whisper available (install openai-whisper); skipping audio transcription")
                                break
                            try:
                                log(f"  [transcribe] [{audio_index}/{total_audio}] {current_url} -> {audio_url}")
                                if use_python_api:
                                    transcript = transcribe_audio_with_python_api(
                                        audio_url=audio_url,
                                        model_name=whisper_model_name,
                                        timeout_seconds=audio_transcribe_timeout,
                                        progress_log=log,
                                    )
                                else:
                                    transcript = transcribe_audio_with_whisper(
                                        audio_url=audio_url,
                                        whisper_executable=whisper_bin,
                                        whisper_model_path=whisper_model_path,
                                        timeout_seconds=audio_transcribe_timeout,
                                        progress_log=log,
                                    )
                                log(f"  [summarize] [{audio_index}/{total_audio}] transcript summary for {audio_url}")
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
                                    _raise_if_terminal_lmstudio_error(exc)
                                    log(f"  [fail] transcript-summary {audio_url}: {type(exc).__name__}: {exc}")
                                    t_summary = "- Transcript captured; summary unavailable in this run."
                                    t_keywords = fallback_keywords(transcript)
                                transcript_keywords.extend(t_keywords)
                                transcript_blob_parts.append(f"Audio URL: {audio_url}\nTranscript: {transcript}")
                                audio_items.append({"url": audio_url, "transcript": transcript, "summary": t_summary})
                                log(f"  [transcribe] [{audio_index}/{total_audio}] completed {audio_url}")
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

            for page in prepared_pages:
                if should_preexclude_page(page.current_url, page.page_title, page.combined_text, target=target):
                    excluded_pages.add(page.current_url)
                    log(f"  [exclude:url] {page.current_url}: matched low-value pre-exclusion rules")

            # Stage 1: Screen remaining pages for whisky relevance using granite (quick)
            screening_targets = [
                page for page in prepared_pages
                if not (page.existing and page.existing["content_hash"] == page.content_hash and not force_rescrape)
                and page.current_url not in excluded_pages
            ]
            if screening_targets:
                log(f"  [batch] screening {len(screening_targets)} page(s) for relevance")
                for page in screening_targets:
                    try:
                        is_relevant = lmstudio_screen_page_relevance(
                            base_url=lmstudio_url,
                            model=lmstudio_screen_model,
                            site_name=target.name,
                            page_url=page.current_url,
                            page_title=page.page_title,
                            text=page.combined_text,
                            timeout_seconds=min(600, lmstudio_extract_timeout),
                        )
                        if not is_relevant:
                            excluded_pages.add(page.current_url)
                            log(f"  [exclude:llm] {page.current_url}: content not whisky-relevant")
                    except Exception as exc:
                        _raise_if_terminal_lmstudio_error(exc)
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
                            _raise_if_terminal_lmstudio_error(exc)
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
                            markdown_path=NULL,
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
                if page.current_url in excluded_pages:
                    # Excluded pages are already marked and cleaned up above.
                    continue

                now = datetime.now(timezone.utc).isoformat()
                summary_md = ""
                keywords: list[str] = []
                summary_json: dict[str, Any] = {}
                product_records: list[dict[str, Any]] = []
                review_records: list[dict[str, Any]] = []
                keyword_sets: dict[str, Any] = {}
                metadata_taxonomy: dict[str, Any] = {}
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
                    metadata_taxonomy = _normalize_metadata_taxonomy(
                        _safe_json_loads(str(page.existing["metadata_taxonomy_json"] or "{}"), {})
                    )
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
                    metadata_taxonomy = _normalize_metadata_taxonomy(structured.get("metadata_taxonomy", {}))
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
                    metadata_taxonomy=metadata_taxonomy,
                    blog_topics=blog_topics,
                )
                metadata_markdown_path = write_page_metadata_output(
                    markdown_dir,
                    site_slug=site_slug,
                    page_url=page.current_url,
                    metadata_taxonomy=metadata_taxonomy,
                    blog_topics=blog_topics,
                )

                conn.execute(
                    """
                    INSERT INTO pages (
                        site_id, url, title, description, text_content, content_hash,
                        extracted_links_json, summary_markdown, summary_json,
                        extracted_products_json, extracted_reviews_json, keyword_sets_json,
                        metadata_taxonomy_json, blog_topics_json, course_topics_json, db_enrichment_json,
                        llm_model, keywords_json, is_content_excluded,
                        crawl_status, last_crawled_at, crawl_count, markdown_path, html_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        metadata_taxonomy_json=excluded.metadata_taxonomy_json,
                        blog_topics_json=excluded.blog_topics_json,
                        course_topics_json=excluded.course_topics_json,
                        db_enrichment_json=excluded.db_enrichment_json,
                        llm_model=excluded.llm_model,
                        keywords_json=excluded.keywords_json,
                        is_content_excluded=excluded.is_content_excluded,
                        crawl_status=excluded.crawl_status,
                        last_crawled_at=excluded.last_crawled_at,
                        crawl_count=pages.crawl_count + 1,
                        markdown_path=excluded.markdown_path,
                        html_path=excluded.html_path
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
                        json.dumps(metadata_taxonomy, ensure_ascii=True),
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
                        str(metadata_markdown_path),
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

    distillery_sync_result: dict[str, Any] | None = None
    if distillery_sync and target.site_type == "distillery" and processed_pages > 0:
        try:
            distillery_sync_result = _sync_distillery_summary_from_state(
                state_conn=conn,
                distillery_db_path=distillery_db_path,
                site_id=site_id,
                target=target,
                lmstudio_url=lmstudio_url,
                lmstudio_model=lmstudio_model,
                lmstudio_extract_timeout=lmstudio_extract_timeout,
            )
            if verbose_crawl:
                sync_meta = distillery_sync_result or {}
                print(
                    f"  [distillery-sync] updated={sync_meta.get('updated')} "
                    f"pages={sync_meta.get('pages_used', 0)}"
                )
            if distillery_sync_result and distillery_sync_result.get("updated"):
                write_site_summary_outputs(
                    base_dir=markdown_dir,
                    site_slug=site_slug,
                    site_name=target.name,
                    site_url=target.url,
                    short_description=str(distillery_sync_result.get("short_description", "")),
                    long_description=str(distillery_sync_result.get("long_description", "")),
                    metadata=distillery_sync_result.get("metadata", {}) if isinstance(distillery_sync_result.get("metadata"), dict) else {},
                    products=distillery_sync_result.get("products", []) if isinstance(distillery_sync_result.get("products"), list) else [],
                    people=distillery_sync_result.get("people", []) if isinstance(distillery_sync_result.get("people"), list) else [],
                )
        except Exception as exc:
            _raise_if_terminal_lmstudio_error(exc)
            distillery_sync_result = {
                "updated": False,
                "reason": f"sync_error:{type(exc).__name__}:{exc}",
                "site_name": target.name,
                "site_id": site_id,
            }
            print(f"  [distillery-sync] fail {target.name}: {type(exc).__name__}: {exc}")

    resource_sync_result: dict[str, Any] | None = None
    if resource_sync and target.site_type == "resource" and processed_pages > 0:
        try:
            resource_sync_result = _sync_resource_summary_from_state(
                state_conn=conn,
                resource_db_path=resource_db_path,
                site_id=site_id,
                target=target,
                lmstudio_url=lmstudio_url,
                lmstudio_model=lmstudio_model,
                lmstudio_extract_timeout=lmstudio_extract_timeout,
            )
            if verbose_crawl:
                sync_meta = resource_sync_result or {}
                print(
                    f"  [resource-sync] updated={sync_meta.get('updated')} "
                    f"pages={sync_meta.get('pages_used', 0)}"
                )
            if resource_sync_result and resource_sync_result.get("updated"):
                write_site_summary_outputs(
                    base_dir=markdown_dir,
                    site_slug=site_slug,
                    site_name=target.name,
                    site_url=target.url,
                    short_description=str(resource_sync_result.get("short_description", "")),
                    long_description=str(resource_sync_result.get("long_description", "")),
                    metadata=resource_sync_result.get("crawl_metadata", {}) if isinstance(resource_sync_result.get("crawl_metadata"), dict) else {},
                )
        except Exception as exc:
            _raise_if_terminal_lmstudio_error(exc)
            resource_sync_result = {
                "updated": False,
                "reason": f"sync_error:{type(exc).__name__}:{exc}",
                "site_name": target.name,
                "site_id": site_id,
            }
            print(f"  [resource-sync] fail {target.name}: {type(exc).__name__}: {exc}")

    return {
        "site_id": site_id,
        "site_type": target.site_type,
        "name": target.name,
        "root_url": target.url,
        "pages_processed": processed_pages,
        "pages_skipped": skipped_pages,
        "pages_failed": failed_pages,
        "pages_summarized": newly_summarized,
        "distillery_sync": distillery_sync_result,
        "resource_sync": resource_sync_result,
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
        "--resource-prefilter-rules",
        default="data/resource_prefilter_rules.json",
        help="Path to machine-readable resource URL/title prefilter rules.",
    )
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
        "--lmstudio-screen-model",
        default="ibm/granite-4-h-tiny",
        help="LM model name to use for quick relevance screening.",
    )
    parser.add_argument(
        "--lmstudio-model",
        default="openai/gpt-oss-20b",
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
        "--no-resource-sync",
        action="store_true",
        help="Disable post-crawl resource summary/metadata sync into resources.db.",
    )
    parser.add_argument(
        "--lmstudio-extract-timeout",
        type=int,
        default=3600,
        help="Timeout in seconds for LM Studio summaries and structured extraction (default 3600 for slow local inference).",
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
    resource_prefilter_rules = Path(args.resource_prefilter_rules).resolve()
    state_db = Path(args.state_db).resolve()
    markdown_dir = Path(args.output_markdown).resolve()
    report_path = Path(args.report).resolve()
    keyword_report = Path(args.keyword_report).resolve()
    whisper_model_path = Path(args.whisper_model_path).expanduser().resolve()

    required_models = [args.lmstudio_model] if args.sync_distillery_from_state else [args.lmstudio_screen_model, args.lmstudio_model]
    ensure_lmstudio_models_available(args.lmstudio_url, required_models)

    targets: list[SiteTarget] = []
    if args.site_types in {"both", "distillery"}:
        targets.extend(load_distillery_targets(distillery_db))
    if args.site_types in {"both", "resource"}:
        targets.extend(load_resource_targets(resource_db, resource_seed, resource_prefilter_rules))

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
                _raise_if_terminal_lmstudio_error(exc)
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
                    resource_db_path=resource_db,
                    markdown_dir=markdown_dir,
                    max_pages_per_site=args.max_pages_per_site,
                    recrawl_days=args.recrawl_days,
                    force_rescrape=args.force_rescrape,
                    page_timeout=args.page_timeout,
                    lmstudio_url=args.lmstudio_url,
                    lmstudio_screen_model=args.lmstudio_screen_model,
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
                    resource_sync=not args.no_resource_sync,
                )
                per_site.append(stats)
                print(
                    f"  pages={stats['pages_processed']} skipped={stats['pages_skipped']} "
                    f"failed={stats['pages_failed']} summarized={stats['pages_summarized']}"
                )
                dist_sync_meta = stats.get("distillery_sync")
                if isinstance(dist_sync_meta, dict) and stats.get("site_type") == "distillery":
                    print(
                        f"  distillery_sync updated={dist_sync_meta.get('updated', False)} "
                        f"reason={dist_sync_meta.get('reason', '')}"
                    )
                    if dist_sync_meta.get("metadata"):
                        print(json.dumps(dist_sync_meta.get("metadata", {}), ensure_ascii=True, indent=2))
                res_sync_meta = stats.get("resource_sync")
                if isinstance(res_sync_meta, dict) and stats.get("site_type") == "resource":
                    print(
                        f"  resource_sync updated={res_sync_meta.get('updated', False)} "
                        f"reason={res_sync_meta.get('reason', '')}"
                    )
            except Exception as exc:
                _raise_if_terminal_lmstudio_error(exc)
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
