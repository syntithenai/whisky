#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _json_checksum(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_records(records: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    seen_ids: set[int] = set()
    seen_slugs: set[str] = set()

    for record in records:
        rid = record.get("id")
        if not isinstance(rid, int):
            issues.append("resource.id must be int")
            continue
        if rid in seen_ids:
            issues.append(f"duplicate resource id: {rid}")
        seen_ids.add(rid)

        slug = record.get("slug")
        if not isinstance(slug, str) or not slug:
            issues.append(f"invalid slug for id={rid}")
        elif slug in seen_slugs:
            issues.append(f"duplicate slug: {slug}")
        else:
            seen_slugs.add(slug)

        for key in [
            "name",
            "url",
            "category",
            "focusArea",
            "audience",
            "regionScope",
            "cost",
            "smallDistilleryRelevance",
            "sourceConfidence",
            "notes",
        ]:
            if not isinstance(record.get(key), str):
                issues.append(f"id={rid} field {key} must be string")

        tags = record.get("tags")
        if not isinstance(tags, list) or not all(isinstance(v, str) for v in tags):
            issues.append(f"id={rid} tags must be string[]")

    return issues


def export_dataset(db_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        resource_rows = conn.execute(
            """
            SELECT
                id,
                slug,
                COALESCE(name, '') AS name,
                COALESCE(url, '') AS url,
                COALESCE(category, '') AS category,
                COALESCE(focus_area, '') AS focus_area,
                COALESCE(audience, '') AS audience,
                COALESCE(region_scope, '') AS region_scope,
                COALESCE(cost, '') AS cost,
                COALESCE(small_distillery_relevance, '') AS small_distillery_relevance,
                COALESCE(source_confidence, '') AS source_confidence,
                COALESCE(notes, '') AS notes
            FROM resources
            ORDER BY category, name
            """
        ).fetchall()

        tag_rows = conn.execute(
            """
            SELECT resource_id, tag
            FROM resource_tags
            ORDER BY resource_id, tag
            """
        ).fetchall()

    tags_by_resource: dict[int, list[str]] = {}
    for row in tag_rows:
        tags_by_resource.setdefault(int(row["resource_id"]), []).append(str(row["tag"]))

    resources: list[dict[str, Any]] = []
    for row in resource_rows:
        rid = int(row["id"])
        resources.append(
            {
                "id": rid,
                "slug": str(row["slug"]),
                "name": str(row["name"]),
                "url": str(row["url"]),
                "category": str(row["category"]),
                "focusArea": str(row["focus_area"]),
                "audience": str(row["audience"]),
                "regionScope": str(row["region_scope"]),
                "cost": str(row["cost"]),
                "smallDistilleryRelevance": str(row["small_distillery_relevance"]),
                "sourceConfidence": str(row["source_confidence"]),
                "notes": str(row["notes"]),
                "tags": tags_by_resource.get(rid, []),
            }
        )

    taxonomy = {
        "categories": sorted({item["category"] for item in resources if item["category"]}),
        "focusAreas": sorted({item["focusArea"] for item in resources if item["focusArea"]}),
        "audiences": sorted({item["audience"] for item in resources if item["audience"]}),
        "regionScopes": sorted({item["regionScope"] for item in resources if item["regionScope"]}),
        "costs": sorted({item["cost"] for item in resources if item["cost"]}),
        "relevanceLevels": sorted(
            {item["smallDistilleryRelevance"] for item in resources if item["smallDistilleryRelevance"]}
        ),
        "sourceConfidenceLevels": sorted({item["sourceConfidence"] for item in resources if item["sourceConfidence"]}),
        "tags": sorted({tag for item in resources for tag in item["tags"]}),
    }

    resources_payload = {
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "recordCount": len(resources),
        "resources": resources,
    }

    taxonomy_payload = {
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        **taxonomy,
    }

    issues = _validate_records(resources)
    if issues:
        raise ValueError("Resource JSON validation failed:\n- " + "\n- ".join(issues))

    resources_path = out_dir / "resources.json"
    taxonomy_path = out_dir / "resources-taxonomy.json"

    resources_path.write_text(json.dumps(resources_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    taxonomy_path.write_text(json.dumps(taxonomy_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    manifest_payload = {
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "recordCount": len(resources),
        "checksums": {
            "resources.json": _json_checksum(resources_payload),
            "resources-taxonomy.json": _json_checksum(taxonomy_payload),
        },
    }
    manifest_path = out_dir / "resources-manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    return {
        "resourcesPath": str(resources_path),
        "taxonomyPath": str(taxonomy_path),
        "manifestPath": str(manifest_path),
        "recordCount": len(resources),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export resources SQLite data to JSON files for offline web use.")
    parser.add_argument("--db", default="data/resources.db", help="Path to resources SQLite database.")
    parser.add_argument("--out-dir", default="data/web", help="Output directory for web JSON files.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    out_dir = Path(args.out_dir).resolve()

    result = export_dataset(db_path=db_path, out_dir=out_dir)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
