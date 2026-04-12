#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from whisky_local.database import connect
from whisky_local.enrichment import (
    LinkAndImageCollector,
    candidate_pages,
    classify_image,
    normalize_url,
    pick_extension,
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crawl_diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distillery_id INTEGER NOT NULL,
            distillery_name TEXT NOT NULL,
            site_url TEXT NOT NULL,
            method TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            success INTEGER NOT NULL,
            pages_visited INTEGER NOT NULL,
            images_downloaded INTEGER NOT NULL,
            http_status INTEGER,
            challenge_hint TEXT,
            error_type TEXT,
            error_message TEXT
        )
        """
    )
    conn.commit()


def challenge_hint_from_html(title: str, html: str) -> str:
    hay = (title + "\n" + html).lower()
    hints = []
    probes = [
        "captcha",
        "cloudflare",
        "access denied",
        "forbidden",
        "verify you are human",
        "bot",
        "ddos",
        "challenge",
    ]
    for token in probes:
        if token in hay:
            hints.append(token)
    return ", ".join(hints)


def save_image_bytes(content: bytes, source_url: str, dest_dir: Path) -> Path | None:
    if len(content) < 300:
        return None
    ext = pick_extension(content, source_url)
    safe_name = str(abs(hash(source_url)))[:18]
    path = dest_dir / f"{safe_name}{ext}"
    path.write_bytes(content)
    return path


def build_report(conn: sqlite3.Connection, report_path: Path) -> None:
    rows = conn.execute(
        """
        SELECT
            distillery_name,
            site_url,
            success,
            pages_visited,
            images_downloaded,
            http_status,
            challenge_hint,
            error_type,
            error_message,
            attempted_at
        FROM crawl_diagnostics
        WHERE method = 'cdp-recrawl'
        ORDER BY attempted_at DESC, distillery_name ASC
        """
    ).fetchall()

    success_count = sum(1 for r in rows if r[2] == 1)
    failure_count = len(rows) - success_count

    lines = [
        "# CDP Recrawl Diagnostics",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total attempts: {len(rows)}",
        f"Successful: {success_count}",
        f"Failed: {failure_count}",
        "",
        "| Distillery | Site | Success | Pages | Images | HTTP | Challenge Hint | Error Type | Error Message | Attempted At |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for r in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    (r[0] or "").replace("|", " "),
                    (r[1] or "").replace("|", " "),
                    "yes" if r[2] == 1 else "no",
                    str(r[3] or 0),
                    str(r[4] or 0),
                    str(r[5] or ""),
                    (r[6] or "").replace("|", " "),
                    (r[7] or "").replace("|", " "),
                    (r[8] or "").replace("|", " "),
                    (r[9] or "").replace("|", " "),
                ]
            )
            + " |"
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recrawl missed distillery sites using Chrome CDP and write diagnostics.")
    parser.add_argument("--db", default="data/distilleries.db", help="Path to SQLite database.")
    parser.add_argument("--image-root", default="data/images", help="Root image directory.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="CDP endpoint for running Chrome.")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages per site to inspect.")
    parser.add_argument("--max-images", type=int, default=12, help="Max images per site to save.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of missed sites (0 = all).")
    parser.add_argument("--report", default="data/crawl_diagnostics_report.md", help="Diagnostics markdown report path.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    image_root = Path(args.image_root).resolve()
    report_path = Path(args.report).resolve()

    conn = connect(db_path)
    ensure_schema(conn)

    missed = conn.execute(
        """
        SELECT d.id, d.slug, d.name, d.official_site
        FROM distilleries d
        WHERE d.official_site LIKE 'http%'
          AND NOT EXISTS (
            SELECT 1 FROM source_pages sp WHERE sp.distillery_id = d.id
          )
        ORDER BY d.country, d.region, d.name
        """
    ).fetchall()

    if args.limit and args.limit > 0:
        missed = missed[: args.limit]

    print(f"Missed distilleries queued for CDP recrawl: {len(missed)}")

    if not missed:
        build_report(conn, report_path)
        print(f"Report written to {report_path}")
        conn.close()
        return

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except Exception as exc:
        print("Playwright is required for CDP recrawl but is unavailable.")
        print(str(exc))
        conn.close()
        raise

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        for row in missed:
            distillery_id = int(row[0])
            slug = row[1]
            name = row[2]
            site = row[3]

            pages_visited = 0
            images_downloaded = 0
            last_http_status = None
            challenge_hint = ""
            error_type = ""
            error_message = ""
            success = 0

            distillery_dir = image_root / slug
            distillery_dir.mkdir(parents=True, exist_ok=True)

            try:
                resp = page.goto(site, wait_until="domcontentloaded", timeout=45000)
                last_http_status = resp.status if resp else None
                html = page.content()
                title = page.title()
                challenge_hint = challenge_hint_from_html(title, html)

                collector = LinkAndImageCollector()
                collector.feed(html)

                pages = [site]
                pages.extend(candidate_pages(site, collector.links))
                pages = pages[: args.max_pages]

                seen_images: set[str] = set()

                for page_url in pages:
                    try:
                        resp = page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                        status = resp.status if resp else None
                        last_http_status = status
                        html = page.content()
                        title = page.title()
                        pages_visited += 1

                        conn.execute(
                            """
                            INSERT OR REPLACE INTO source_pages (distillery_id, url, title, fetched_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                distillery_id,
                                page_url,
                                title.strip(),
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )

                        sub_collector = LinkAndImageCollector()
                        sub_collector.feed(html)
                        image_entries = list(sub_collector.images)
                        image_entries.extend((url, "og:image") for url in sub_collector.meta_images)

                        for raw_url, alt_text in image_entries:
                            source_url = normalize_url(page_url, raw_url)
                            if not source_url or source_url in seen_images:
                                continue
                            seen_images.add(source_url)

                            category, score = classify_image(source_url, alt_text, page_url)
                            try:
                                img_resp = context.request.get(source_url, timeout=20000)
                                if not img_resp.ok:
                                    continue
                                saved = save_image_bytes(img_resp.body(), source_url, distillery_dir)
                                if saved is None:
                                    continue
                            except Exception:
                                continue

                            local_rel = saved.relative_to(image_root.parent).as_posix()
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO images (
                                    distillery_id, source_url, page_url, local_path, category, alt_text, score
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    distillery_id,
                                    source_url,
                                    page_url,
                                    local_rel,
                                    category,
                                    alt_text[:400],
                                    score,
                                ),
                            )
                            images_downloaded += 1
                            if images_downloaded >= args.max_images:
                                break

                        if images_downloaded >= args.max_images:
                            break
                    except PlaywrightTimeoutError as exc:
                        error_type = "timeout"
                        error_message = str(exc)
                    except Exception as exc:
                        error_type = type(exc).__name__
                        error_message = str(exc)

                success = 1 if pages_visited > 0 else 0

            except PlaywrightTimeoutError as exc:
                error_type = "timeout"
                error_message = str(exc)
            except Exception as exc:
                error_type = type(exc).__name__
                error_message = str(exc)

            conn.execute(
                """
                INSERT INTO crawl_diagnostics (
                    distillery_id, distillery_name, site_url, method, attempted_at,
                    success, pages_visited, images_downloaded, http_status,
                    challenge_hint, error_type, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    distillery_id,
                    name,
                    site,
                    "cdp-recrawl",
                    datetime.now(timezone.utc).isoformat(),
                    success,
                    pages_visited,
                    images_downloaded,
                    last_http_status,
                    challenge_hint,
                    error_type,
                    error_message[:600],
                ),
            )
            conn.commit()
            print(f"[cdp] {name}: success={success} pages={pages_visited} images={images_downloaded} status={last_http_status}")

        page.close()
        browser.close()

    build_report(conn, report_path)
    print(f"Report written to {report_path}")
    conn.close()


if __name__ == "__main__":
    main()
