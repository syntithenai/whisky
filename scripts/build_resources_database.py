#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from whisky_local.database import connect, slugify
from whisky_local.resources_database import init_schema, replace_tags, upsert_resource
from export_resources_json import export_dataset


def _load_seed(seed_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        resources = payload.get("resources", [])
    elif isinstance(payload, list):
        resources = payload
    else:
        raise ValueError("Seed payload must be an object or array")

    if not isinstance(resources, list):
        raise ValueError("Seed resources must be a list")

    clean_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(resources, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Resource at index {idx} must be an object")
        clean_rows.append(row)

    return clean_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build whisky resource website database from curated seed data.")
    parser.add_argument("--seed", default="data/resource_sites_seed.json", help="Path to resources seed JSON.")
    parser.add_argument("--db", default="data/resources.db", help="Path to resources SQLite DB output.")
    parser.add_argument("--export-json", action="store_true", help="Export JSON files for offline web app.")
    parser.add_argument("--json-out-dir", default="data/web", help="Output folder for exported JSON files.")
    args = parser.parse_args()

    seed_path = Path(args.seed).resolve()
    db_path = Path(args.db).resolve()

    rows = _load_seed(seed_path)

    conn = connect(db_path)
    init_schema(conn)

    processed = 0

    for row in rows:
        name = str(row.get("name", "")).strip()
        url = str(row.get("url", "")).strip()
        if not name or not url.startswith("http"):
            raise ValueError(f"Invalid seed row (name/url): {row}")

        payload = {
            "slug": str(row.get("slug") or slugify(name)),
            "name": name,
            "url": url,
            "category": str(row.get("category", "")).strip(),
            "focus_area": str(row.get("focusArea", "")).strip(),
            "audience": str(row.get("audience", "")).strip(),
            "region_scope": str(row.get("regionScope", "")).strip(),
            "cost": str(row.get("cost", "")).strip(),
            "small_distillery_relevance": str(row.get("smallDistilleryRelevance", "")).strip(),
            "source_confidence": str(row.get("sourceConfidence", "")).strip(),
            "notes": str(row.get("notes", "")).strip(),
        }

        tags = row.get("tags", [])
        tag_list = [str(tag).strip().lower() for tag in tags if str(tag).strip()] if isinstance(tags, list) else []

        resource_id = upsert_resource(conn, payload)
        replace_tags(conn, resource_id, tag_list)
        processed += 1

    conn.commit()
    conn.close()

    print(f"Built resources database at: {db_path}")
    print(f"Resources processed: {processed}")

    if args.export_json:
        export_result = export_dataset(
            db_path=db_path,
            out_dir=Path(args.json_out_dir).resolve(),
        )
        print("Resources JSON dataset exported:")
        print(export_result)


if __name__ == "__main__":
    main()
