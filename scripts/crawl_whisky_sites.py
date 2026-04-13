#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
from typing import Any
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class SiteTarget:
    site_type: str
    name: str
    url: str


class ContentCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
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
            targets.extend([SiteTarget(site_type="resource", name=str(r["name"]), url=str(r["url"])) for r in rows])
        finally:
            conn.close()

    if not targets and seed_path.exists():
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        for entry in payload.get("resources", []):
            url = str(entry.get("url", "")).strip()
            name = str(entry.get("name", "")).strip()
            if url.startswith("http") and name:
                targets.append(SiteTarget(site_type="resource", name=name, url=url))

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
        "summary_markdown should be concise markdown with sections: Key Facts, Production Signals, Commercial Signals, Risks/Unknowns. "
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
        for k in parsed.get("keywords", [])
        if isinstance(k, str) and normalize_ws(k)
    ]
    if not summary_md:
        raise ValueError("LM Studio response missing summary_markdown")
    if not keywords:
        keywords = fallback_keywords(text)
    return summary_md, sorted(set(keywords))


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
        f"## Key Facts\n"
        f"- Source: {name}\n"
        f"- Page: {page_title or 'Untitled'}\n\n"
        f"## Production Signals\n"
        f"- Auto-summary fallback used because LM Studio output was unavailable.\n\n"
        f"## Commercial Signals\n"
        f"- Candidate keywords: {', '.join(keywords[:10]) if keywords else 'none'}\n\n"
        f"## Risks/Unknowns\n"
        f"- Verify details directly from source page.\n"
        f"- Raw extract snippet: {snippet}"
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


def same_domain(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()


def should_skip_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip", ".mp4", ".mp3"]):
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
    driver,
    target: SiteTarget,
    markdown_dir: Path,
    max_pages_per_site: int,
    recrawl_days: int,
    force_rescrape: bool,
    page_timeout: int,
    age_gate_wait: int,
    lmstudio_url: str,
    lmstudio_model: str,
    throttle_seconds: float,
) -> dict[str, Any]:
    site_row = get_or_create_site(conn, target)
    site_id = int(site_row["id"])
    site_slug = slugify(f"{target.site_type}-{target.name}")

    queue: list[tuple[str, int]] = [(canonicalize_site_root(target.url), 0)]
    seen: set[str] = set()

    processed_pages = 0
    skipped_pages = 0
    failed_pages = 0
    newly_summarized = 0

    while queue and processed_pages < max_pages_per_site:
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
            skipped_pages += 1
            existing_links = json.loads(existing["extracted_links_json"] or "[]")
            for link in existing_links:
                if same_domain(target.url, link) and link not in seen:
                    queue.append((link, depth + 1))
            continue

        now = datetime.now(timezone.utc).isoformat()
        try:
            html, browser_title, current_url = fetch_with_selenium(
                driver,
                page_url,
                page_timeout=page_timeout,
                age_gate_wait=age_gate_wait,
            )
            collector = ContentCollector()
            collector.feed(html)
            page_title = collector.title or browser_title
            text_content = collector.visible_text
            description = collector.description

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
            seen_links = set()
            for link in normalized_links:
                if link in seen_links:
                    continue
                seen_links.add(link)
                unique_links.append(link)
                if link not in seen:
                    queue.append((link, depth + 1))

            content_hash = hashlib.sha256(text_content.encode("utf-8", errors="ignore")).hexdigest()

            summary_md = ""
            keywords: list[str] = []
            if existing and existing["content_hash"] == content_hash and not force_rescrape:
                summary_md = str(existing["summary_markdown"] or "")
                keywords = json.loads(existing["keywords_json"] or "[]")
            else:
                try:
                    summary_md, keywords = lmstudio_summarize(
                        base_url=lmstudio_url,
                        model=lmstudio_model,
                        name=target.name,
                        url=target.url,
                        page_title=page_title,
                        text=text_content,
                    )
                except Exception:
                    keywords = fallback_keywords(text_content)
                    summary_md = fallback_summary(target.name, page_title, text_content, keywords)
                newly_summarized += 1

            markdown_path = write_markdown_output(
                markdown_dir,
                site_slug=site_slug,
                page_url=current_url,
                title=page_title,
                summary_markdown=summary_md,
                keywords=keywords,
            )

            conn.execute(
                """
                INSERT INTO pages (
                    site_id, url, title, description, text_content, content_hash,
                    extracted_links_json, summary_markdown, llm_model, keywords_json,
                    crawl_status, last_crawled_at, crawl_count, markdown_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(site_id, url) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    text_content=excluded.text_content,
                    content_hash=excluded.content_hash,
                    extracted_links_json=excluded.extracted_links_json,
                    summary_markdown=excluded.summary_markdown,
                    llm_model=excluded.llm_model,
                    keywords_json=excluded.keywords_json,
                    crawl_status=excluded.crawl_status,
                    last_crawled_at=excluded.last_crawled_at,
                    crawl_count=pages.crawl_count + 1,
                    markdown_path=excluded.markdown_path
                """,
                (
                    site_id,
                    current_url,
                    page_title,
                    description,
                    text_content,
                    content_hash,
                    json.dumps(unique_links, ensure_ascii=True),
                    summary_md,
                    lmstudio_model,
                    json.dumps(sorted(set(keywords)), ensure_ascii=True),
                    "ok",
                    now,
                    str(markdown_path),
                ),
            )

            update_keyword_index(conn, site_id=site_id, page_url=current_url, keywords=keywords)
            processed_pages += 1
            time.sleep(max(0.0, throttle_seconds))
        except Exception as exc:
            failed_pages += 1
            conn.execute(
                """
                INSERT INTO pages (site_id, url, crawl_status, last_crawled_at, crawl_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(site_id, url) DO UPDATE SET
                    crawl_status=excluded.crawl_status,
                    last_crawled_at=excluded.last_crawled_at,
                    crawl_count=pages.crawl_count + 1
                """,
                (site_id, page_url, f"error:{type(exc).__name__}", now),
            )

        conn.commit()

    conn.execute(
        "UPDATE sites SET last_crawled_at = ?, last_status = ? WHERE id = ?",
        (
            datetime.now(timezone.utc).isoformat(),
            f"ok pages={processed_pages} skipped={skipped_pages} failed={failed_pages}",
            site_id,
        ),
    )
    conn.commit()

    return {
        "site_id": site_id,
        "site_type": target.site_type,
        "name": target.name,
        "root_url": target.url,
        "pages_processed": processed_pages,
        "pages_skipped": skipped_pages,
        "pages_failed": failed_pages,
        "pages_summarized": newly_summarized,
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
    parser.add_argument("--max-pages-per-site", type=int, default=30, help="Maximum pages to crawl per site.")
    parser.add_argument("--recrawl-days", type=int, default=14, help="Skip recrawl if page was fetched within this many days.")
    parser.add_argument("--force-rescrape", action="store_true", help="Re-fetch and re-summarize even when cache is fresh.")
    parser.add_argument("--state-db", default="data/site_crawl_state.db", help="SQLite DB for crawler state.")
    parser.add_argument("--output-markdown", default="data/crawl_markdown", help="Directory for per-page markdown output.")
    parser.add_argument("--report", default="data/crawl_report.md", help="Markdown report output path.")
    parser.add_argument("--keyword-report", default="data/keyword_index.md", help="Keyword index markdown report.")
    parser.add_argument("--page-timeout", type=int, default=60, help="Selenium page-load timeout in seconds.")
    parser.add_argument("--age-gate-wait", type=int, default=10, help="Seconds to search/click age-gate controls.")
    parser.add_argument("--throttle-seconds", type=float, default=0.8, help="Delay between page fetches.")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    parser.add_argument("--lmstudio-url", default="http://127.0.0.1:1234/v1", help="LM Studio OpenAI-compatible base URL.")
    parser.add_argument(
        "--lmstudio-model",
        default="qwen3.5-27b-claude-4.6-opus-reasoning-distilled-v2",
        help="LM model name to use for summaries.",
    )
    args = parser.parse_args()

    distillery_db = Path(args.distillery_db).resolve()
    resource_db = Path(args.resource_db).resolve()
    resource_seed = Path(args.resource_seed).resolve()
    state_db = Path(args.state_db).resolve()
    markdown_dir = Path(args.output_markdown).resolve()
    report_path = Path(args.report).resolve()
    keyword_report = Path(args.keyword_report).resolve()

    targets: list[SiteTarget] = []
    if args.site_types in {"both", "distillery"}:
        targets.extend(load_distillery_targets(distillery_db))
    if args.site_types in {"both", "resource"}:
        targets.extend(load_resource_targets(resource_db, resource_seed))

    targets = dedupe_targets(targets)
    targets = targets[: max(0, args.max_sites)] if args.max_sites > 0 else targets

    if not targets:
        print("No crawl targets found. Check DB paths and seed data.")
        return

    conn = connect_state_db(state_db)
    driver = open_selenium_driver(headless=args.headless)

    per_site: list[dict[str, Any]] = []
    try:
        for idx, target in enumerate(targets, start=1):
            print(f"[{idx}/{len(targets)}] Crawling {target.site_type}: {target.name} ({target.url})")
            try:
                stats = crawl_site(
                    conn=conn,
                    driver=driver,
                    target=target,
                    markdown_dir=markdown_dir,
                    max_pages_per_site=args.max_pages_per_site,
                    recrawl_days=args.recrawl_days,
                    force_rescrape=args.force_rescrape,
                    page_timeout=args.page_timeout,
                    age_gate_wait=args.age_gate_wait,
                    lmstudio_url=args.lmstudio_url,
                    lmstudio_model=args.lmstudio_model,
                    throttle_seconds=args.throttle_seconds,
                )
                per_site.append(stats)
                print(
                    f"  pages={stats['pages_processed']} skipped={stats['pages_skipped']} "
                    f"failed={stats['pages_failed']} summarized={stats['pages_summarized']}"
                )
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
        driver.quit()
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
