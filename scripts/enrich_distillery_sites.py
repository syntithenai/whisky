#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from whisky_local.database import connect
from whisky_local.enrichment import LinkAndImageCollector, candidate_pages, fetch_text


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


@dataclass
class PageSignal:
    url: str
    title: str
    history: bool
    process: bool
    core_range: bool
    technical_blog: bool


NEW_TERM_CANDIDATES = [
    "worm tub",
    "shell and tube condenser",
    "spirit still",
    "wash still",
    "new fill",
    "char level",
    "warehouse parcel",
    "str cask",
    "first fill",
    "refill",
    "single cask",
    "small batch",
    "entry proof",
    "bottle code",
    "non chill filtered",
    "natural colour",
    "warehouse microclimate",
    "spirit safe",
    "dunnage",
    "racked warehouse",
]


def norm_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_glossary_terms(readme_text: str) -> set[str]:
    terms: set[str] = set()
    in_section = False
    for line in readme_text.splitlines():
        if line.startswith("## 18. Dictionary of Important Whisky Words"):
            in_section = True
            continue
        if in_section and line.startswith("## 19."):
            break
        if not in_section:
            continue
        m = re.match(r"^-\s+([^:]+):", line.strip())
        if m:
            terms.add(m.group(1).strip().lower())
    return terms


def detect_signal(url: str, title: str, page_text: str) -> PageSignal:
    hay = " ".join([url, title, page_text]).lower()
    history = any(k in hay for k in ["history", "heritage", "our story", "founded", "since "])
    process = any(
        k in hay
        for k in [
            "process",
            "craft",
            "distillation",
            "mash",
            "fermentation",
            "still",
            "warehouse",
            "maturation",
            "cask",
            "barrel",
            "new make",
        ]
    )
    core_range = any(
        k in hay for k in ["core range", "our whisky", "our whiskey", "products", "shop", "collection", "expressions"]
    )
    technical_blog = any(k in hay for k in ["blog", "journal", "academy", "learn", "education", "news", "technical"])
    return PageSignal(url=url, title=title, history=history, process=process, core_range=core_range, technical_blog=technical_blog)


def extract_facts(text: str) -> list[str]:
    facts: list[str] = []
    checks = [
        ("stills", ["pot still", "column still", "spirit still", "wash still", "copper"]),
        ("fermentation", ["fermentation", "washback", "yeast"]),
        ("grain", ["barley", "rye", "corn", "wheat", "malted", "mash bill"]),
        ("cask", ["cask", "barrel", "sherry", "bourbon", "mizunara", "refill", "first fill"]),
        ("maturation", ["warehouse", "dunnage", "racked", "angel", "age"]),
        ("strength", ["abv", "cask strength", "proof", "non chill", "natural colour"]),
    ]
    low = text.lower()
    for label, terms in checks:
        hit = [t for t in terms if t in low]
        if hit:
            facts.append(f"{label}: " + ", ".join(sorted(set(hit))[:6]))
    return facts


def extract_mythology_cues(text: str) -> list[str]:
    low = text.lower()
    cues = []
    for token in ["legend", "myth", "ancient", "timeless", "mystic", "secret recipe", "handcrafted tradition", "heritage"]:
        if token in low:
            cues.append(token)
    return sorted(set(cues))[:8]


def normalize_site(url: str) -> str:
    p = urlparse(url)
    host = p.netloc.lower().replace("www.", "")
    return f"{p.scheme.lower()}://{host}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich distillery notes and statuses from official websites.")
    parser.add_argument("--db", default="data/distilleries.db")
    parser.add_argument("--max-pages", type=int, default=7)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    readme_text = README_PATH.read_text(encoding="utf-8")
    glossary_terms = parse_glossary_terms(readme_text)

    db_path = (PROJECT_ROOT / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db)
    conn = connect(db_path)

    rows = conn.execute(
        """
        SELECT id, name, slug, official_site, operating_status
        FROM distilleries
        WHERE official_site LIKE 'http%'
        ORDER BY country, region, name
        """
    ).fetchall()
    if args.limit > 0:
        rows = rows[: args.limit]

    total = len(rows)
    updated = 0
    failures = 0
    discovered_terms: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()

    for i, row in enumerate(rows, start=1):
        distillery_id = int(row[0])
        name = row[1]
        site = row[3]

        visited: list[tuple[str, str, str]] = []
        signals: list[PageSignal] = []
        all_text_chunks: list[str] = []
        statuses: list[str] = []

        try:
            html = fetch_text(site, timeout=20)
        except Exception as exc:
            failures += 1
            conn.execute(
                "UPDATE distilleries SET notes = ?, study_status = ? WHERE id = ?",
                (f"Site fetch failed ({now}): {type(exc).__name__}: {str(exc)[:200]}", "Not started", distillery_id),
            )
            conn.commit()
            print(f"[{i}/{total}] fail {name}: {type(exc).__name__}")
            continue

        collector = LinkAndImageCollector()
        collector.feed(html)
        extractor = TextExtractor()
        extractor.feed(html)

        home_text = norm_whitespace(extractor.text())
        home_title = norm_whitespace(collector.page_title)[:180]
        visited.append((site, home_title, home_text[:5000]))

        pages = [site]
        pages.extend(candidate_pages(site, collector.links))

        # Broaden coverage for product/technical/blog pages.
        extra = []
        for href in collector.links:
            full = href.strip()
            if not full:
                continue
            try:
                from whisky_local.enrichment import normalize_url, same_domain

                n = normalize_url(site, full)
                if not n or not same_domain(site, n):
                    continue
                low = n.lower()
                if any(k in low for k in ["about", "history", "heritage", "craft", "process", "product", "shop", "range", "blog", "journal", "academy", "news"]):
                    extra.append(n)
            except Exception:
                continue
        pages.extend(extra)

        unique_pages = []
        seen = set()
        for p in pages:
            if p not in seen:
                seen.add(p)
                unique_pages.append(p)
        unique_pages = unique_pages[: args.max_pages]

        for p in unique_pages[1:]:
            try:
                body = fetch_text(p, timeout=20)
                c = LinkAndImageCollector()
                c.feed(body)
                e = TextExtractor()
                e.feed(body)
                text = norm_whitespace(e.text())
                title = norm_whitespace(c.page_title)[:180]
                visited.append((p, title, text[:5000]))
            except Exception:
                continue

        combined_text = "\n".join(v[2] for v in visited)
        all_text_chunks.append(combined_text)

        for url, title, text in visited:
            signals.append(detect_signal(url, title, text))

        if visited:
            statuses.append("Site reviewed")
        if any(s.history for s in signals):
            statuses.append("History reviewed")
        if any(s.process for s in signals):
            statuses.append("Process reviewed")
        if any(s.core_range for s in signals):
            statuses.append("Core range mapped")
        if visited:
            statuses.append("Notes complete")

        facts = extract_facts(combined_text)
        myth = extract_mythology_cues(combined_text)

        hit_terms = []
        low_combined = combined_text.lower()
        for t in glossary_terms:
            if t and t in low_combined:
                hit_terms.append(t)

        new_hits = []
        for t in NEW_TERM_CANDIDATES:
            if t in low_combined and t not in glossary_terms:
                new_hits.append(t)
                discovered_terms[t] = discovered_terms.get(t, 0) + 1

        history_urls = [s.url for s in signals if s.history][:3]
        process_urls = [s.url for s in signals if s.process][:3]
        core_urls = [s.url for s in signals if s.core_range][:3]
        blog_urls = [s.url for s in signals if s.technical_blog][:3]

        note_lines = [
            f"Site review updated: {now}",
            f"Pages visited: {len(visited)}",
        ]
        if history_urls:
            note_lines.append("History pages: " + " | ".join(history_urls))
        if process_urls:
            note_lines.append("Process pages: " + " | ".join(process_urls))
        if core_urls:
            note_lines.append("Core range/product pages: " + " | ".join(core_urls))
        if blog_urls:
            note_lines.append("Technical/blog pages: " + " | ".join(blog_urls))
        if facts:
            note_lines.append("Production facts: " + "; ".join(facts[:6]))
        if myth:
            note_lines.append("Brand-myth cues: " + ", ".join(myth))
        if hit_terms:
            note_lines.append("Glossary terms covered: " + ", ".join(sorted(set(hit_terms))[:20]))
        if new_hits:
            note_lines.append("Potential new glossary terms: " + ", ".join(sorted(set(new_hits))))

        note_text = "\n".join(note_lines)

        short_header = (
            f"pages={len(visited)};"
            f"history={len(history_urls)};"
            f"process={len(process_urls)};"
            f"core={len(core_urls)};"
            f"blog={len(blog_urls)};"
            f"terms={len(set(hit_terms))};"
            f"new_terms={','.join(sorted(set(new_hits))[:6])}"
        )

        # Keep statuses in the suggested label vocabulary.
        status_text = ", ".join(statuses) if statuses else "Not started"

        conn.execute(
            """
            UPDATE distilleries
            SET notes = ?, source_headers = ?, study_status = ?
            WHERE id = ?
            """,
            (note_text, short_header, status_text, distillery_id),
        )

        # Save visited pages for traceability in the UI detail page.
        for url, title, _text in visited:
            conn.execute(
                """
                INSERT OR REPLACE INTO source_pages (distillery_id, url, title, fetched_at)
                VALUES (?, ?, ?, ?)
                """,
                (distillery_id, url, title[:240], now),
            )

        conn.commit()
        updated += 1
        print(f"[{i}/{total}] ok   {name}: pages={len(visited)} status={status_text}")

    # Persist discovered new-term suggestions for glossary expansion workflow.
    if discovered_terms:
        out = PROJECT_ROOT / "data" / "glossary_new_terms.txt"
        lines = ["term\thits"]
        for term, hits in sorted(discovered_terms.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"{term}\t{hits}")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    conn.close()
    print("\nSummary")
    print("updated", updated)
    print("failures", failures)
    print("new_terms_found", len(discovered_terms))


if __name__ == "__main__":
    main()
