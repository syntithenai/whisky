from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import hashlib
import imghdr
import re
import time


USER_AGENT = "WhiskyStudyBot/1.0 (+local research crawler)"


@dataclass
class ImageCandidate:
    source_url: str
    page_url: str
    alt_text: str
    category: str
    score: int


class LinkAndImageCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.meta_images: list[str] = []
        self.page_title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}

        if tag == "a":
            href = attr_map.get("href", "").strip()
            if href:
                self.links.append(href)

        if tag == "img":
            src = attr_map.get("src", "").strip()
            if not src:
                # Many ecommerce/gallery pages lazy-load product images into data-* attrs.
                src = (
                    attr_map.get("data-src", "").strip()
                    or attr_map.get("data-lazy-src", "").strip()
                    or attr_map.get("data-original", "").strip()
                )
            alt = attr_map.get("alt", "").strip()
            if not alt:
                alt = attr_map.get("aria-label", "").strip() or attr_map.get("title", "").strip()
            srcset = attr_map.get("srcset", "").strip()
            if not src and srcset:
                src = srcset.split(",")[0].strip().split(" ")[0]
            if src:
                self.images.append((src, alt))

        data_image_url = attr_map.get("data-image-url", "").strip()
        if data_image_url:
            descriptor = (
                attr_map.get("aria-label", "").strip()
                or attr_map.get("alt", "").strip()
                or attr_map.get("title", "").strip()
            )
            self.images.append((data_image_url, descriptor))

        if tag == "meta":
            prop = attr_map.get("property", "") or attr_map.get("name", "")
            if prop.lower() in {"og:image", "twitter:image", "twitter:image:src"}:
                content = attr_map.get("content", "").strip()
                if content:
                    self.meta_images.append(content)

        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page_title += data


def fetch_text(url: str, timeout: int = 15) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_bytes(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def classify_image(source_url: str, alt_text: str, page_url: str) -> tuple[str, int]:
    source_alt = " ".join([source_url, alt_text]).lower()
    page = page_url.lower()

    if any(word in source_alt for word in ["logo", "wordmark", "brandmark", "favicon"]):
        return "logo", 100

    awards_keywords = [
        "award",
        "awards",
        "medal",
        "winner",
        "trophy",
        "best in class",
        "double gold",
        "gold medal",
        "silver medal",
        "bronze medal",
    ]
    if any(word in source_alt for word in awards_keywords):
        return "awards", 90

    bottle_keywords = [
        "bottle",
        "label",
        "product",
        "single-malt",
        "single_malt",
        "single malt",
        "whisky",
        "whiskey",
        "gin",
        "vodka",
        "rum",
        "liqueur",
        "brandy",
        "absinthe",
        "shop",
        "store",
    ]
    if any(word in source_alt for word in bottle_keywords):
        return "bottle", 85

    # Product gallery/store pages frequently host bottle photos with generic filenames.
    if "/store/" in page or "product" in page or "shop" in page:
        return "bottle", 75

    process_keywords = [
        "still",
        "mash",
        "washback",
        "ferment",
        "cask",
        "barrel",
        "warehouse",
        "distillation",
        "process",
    ]
    if any(word in source_alt for word in process_keywords):
        return "process", 70

    return "general", 30


def normalize_url(base_url: str, maybe_relative: str) -> str:
    if maybe_relative.startswith("data:"):
        return ""
    full = urljoin(base_url, maybe_relative)
    parsed = urlparse(full)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return full


def same_domain(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()


def candidate_pages(start_url: str, links: list[str]) -> list[str]:
    preferred_tokens = [
        "about",
        "history",
        "our-story",
        "craft",
        "process",
        "production",
        "distillery",
        "whisky",
        "whiskey",
        "story",
    ]

    resolved: list[str] = []
    for href in links:
        normalized = normalize_url(start_url, href)
        if not normalized:
            continue
        if not same_domain(start_url, normalized):
            continue
        lowered = normalized.lower()
        if any(token in lowered for token in preferred_tokens):
            resolved.append(normalized)

    unique: list[str] = []
    seen: set[str] = set()
    for url in resolved:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def pick_extension(content: bytes, source_url: str) -> str:
    guessed = imghdr.what(None, h=content)
    if guessed:
        return "." + guessed.replace("jpeg", "jpg")

    lower = source_url.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"]:
        if ext in lower:
            return ".jpg" if ext == ".jpeg" else ext

    return ".img"


def download_image_to_file(image_url: str, dest_dir: Path) -> Path | None:
    try:
        content = fetch_bytes(image_url)
    except (URLError, HTTPError, TimeoutError, ValueError, UnicodeError):
        return None

    if len(content) < 300:
        return None

    ext = pick_extension(content, image_url)
    digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:18]
    file_path = dest_dir / f"{digest}{ext}"
    file_path.write_bytes(content)
    return file_path


def crawl_distillery_images(
    conn,
    distillery_id: int,
    slug: str,
    official_site: str,
    image_root: Path,
    max_pages: int = 4,
    max_images: int = 24,
    throttle_seconds: float = 0.4,
) -> dict[str, int]:
    if not official_site.startswith("http"):
        return {"pages": 0, "images": 0}

    distillery_dir = image_root / slug
    distillery_dir.mkdir(parents=True, exist_ok=True)

    try:
        homepage_html = fetch_text(official_site)
    except (URLError, HTTPError, TimeoutError, ValueError, UnicodeError):
        return {"pages": 0, "images": 0}

    homepage_collector = LinkAndImageCollector()
    homepage_collector.feed(homepage_html)

    pages_to_visit = [official_site]
    pages_to_visit.extend(candidate_pages(official_site, homepage_collector.links))
    pages_to_visit = pages_to_visit[:max_pages]

    visited: set[str] = set()
    seen_image_urls: set[str] = set()
    image_count = 0

    for page_url in pages_to_visit:
        if page_url in visited:
            continue
        visited.add(page_url)

        try:
            html = fetch_text(page_url)
        except (URLError, HTTPError, TimeoutError, ValueError, UnicodeError):
            continue

        collector = LinkAndImageCollector()
        collector.feed(html)

        conn.execute(
            """
            INSERT OR REPLACE INTO source_pages (distillery_id, url, title, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                distillery_id,
                page_url,
                collector.page_title.strip(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        image_entries = list(collector.images)
        image_entries.extend((url, "og:image") for url in collector.meta_images)

        for raw_url, alt_text in image_entries:
            source_url = normalize_url(page_url, raw_url)
            if not source_url:
                continue
            if source_url in seen_image_urls:
                continue
            seen_image_urls.add(source_url)

            category, score = classify_image(source_url, alt_text, page_url)
            saved_path = download_image_to_file(source_url, distillery_dir)
            if saved_path is None:
                continue

            local_rel = saved_path.relative_to(image_root.parent).as_posix()

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

            image_count += 1
            if image_count >= max_images:
                break

        conn.commit()
        if image_count >= max_images:
            break

        time.sleep(throttle_seconds)

    return {"pages": len(visited), "images": image_count}
