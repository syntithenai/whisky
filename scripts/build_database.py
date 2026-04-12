#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from whisky_local.database import connect, init_schema, replace_styles, slugify, upsert_distillery
from whisky_local.enrichment import crawl_distillery_images
from whisky_local.markdown_tracker import parse_tracker


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and enrich the local distillery study SQLite database from tracker markdown."
    )
    parser.add_argument(
        "--tracker",
        default="DISTILLERY_STUDY_TRACKER.md",
        help="Path to the markdown tracker file.",
    )
    parser.add_argument(
        "--db",
        default="data/distilleries.db",
        help="Path to SQLite database output.",
    )
    parser.add_argument(
        "--image-root",
        default="data/images",
        help="Root folder for downloaded image assets.",
    )
    parser.add_argument(
        "--crawl-images",
        action="store_true",
        help="Visit distillery sites and download image assets (logo, bottle, process, general).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=4,
        help="Maximum pages to scan per distillery when crawling images.",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=24,
        help="Maximum images to download per distillery.",
    )
    parser.add_argument(
        "--max-distilleries",
        type=int,
        default=0,
        help="Optional cap on number of distilleries processed (0 = all).",
    )
    args = parser.parse_args()

    tracker_path = Path(args.tracker).resolve()
    db_path = Path(args.db).resolve()
    image_root = Path(args.image_root).resolve()

    conn = connect(db_path)
    init_schema(conn)

    processed = 0
    crawled = 0
    downloaded = 0

    for record, styles in parse_tracker(tracker_path):
        if args.max_distilleries and processed >= args.max_distilleries:
            break

        payload = {
            "slug": slugify(f"{record.country}-{record.section}-{record.region}-{record.name}"),
            "name": record.name,
            "country": record.country,
            "region": record.region,
            "section": record.section,
            "why_study": record.why_study,
            "official_site": record.official_site,
            "key_focus": record.key_focus,
            "study_status": record.study_status,
            "operating_status": record.operating_status,
            "website_confidence": record.website_confidence,
            "notes": record.notes,
            "source_headers": record.source_headers,
        }

        distillery_id = upsert_distillery(conn, payload)
        replace_styles(conn, distillery_id, styles)
        processed += 1

        if args.crawl_images and record.official_site.startswith("http"):
            stats = crawl_distillery_images(
                conn,
                distillery_id=distillery_id,
                slug=payload["slug"],
                official_site=record.official_site,
                image_root=image_root,
                max_pages=args.max_pages,
                max_images=args.max_images,
            )
            crawled += 1
            downloaded += stats["images"]
            print(
                f"[crawl] {record.name}: pages={stats['pages']} images={stats['images']}"
            )

    conn.commit()
    conn.close()

    print(f"Built database at: {db_path}")
    print(f"Distilleries processed: {processed}")
    if args.crawl_images:
        print(f"Distilleries crawled: {crawled}")
        print(f"Images downloaded: {downloaded}")


if __name__ == "__main__":
    main()
