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


def _normalize_path(path_value: str) -> str:
    path = (path_value or "").replace("\\", "/").strip()
    if not path:
        return ""
    if path.startswith("data/"):
        return path
    return f"data/{path.lstrip('/')}"


def _validate_records(records: list[dict[str, Any]], project_root: Path) -> list[str]:
    issues: list[str] = []
    seen_ids: set[int] = set()
    seen_slugs: set[str] = set()

    required_string_fields = [
        "name",
        "slug",
        "country",
        "region",
        "section",
        "officialSite",
        "websiteConfidence",
        "operatingStatus",
        "studyStatus",
        "whyStudy",
        "keyFocus",
        "notes",
    ]

    for record in records:
        rid = record.get("id")
        if not isinstance(rid, int):
            issues.append(f"distillery.id must be int: {record.get('slug', '<unknown>')}")
            continue
        if rid in seen_ids:
            issues.append(f"duplicate distillery id: {rid}")
        seen_ids.add(rid)

        slug = record.get("slug")
        if not isinstance(slug, str) or not slug:
            issues.append(f"invalid slug for id={rid}")
        elif slug in seen_slugs:
            issues.append(f"duplicate slug: {slug}")
        else:
            seen_slugs.add(slug)

        for field in required_string_fields:
            value = record.get(field)
            if not isinstance(value, str):
                issues.append(f"id={rid} field '{field}' must be string")

        styles = record.get("styles")
        if not isinstance(styles, list) or not all(isinstance(v, str) for v in styles):
            issues.append(f"id={rid} styles must be string[]")

        image_count = record.get("imageCount")
        if not isinstance(image_count, int) or image_count < 0:
            issues.append(f"id={rid} imageCount must be non-negative int")

        images = record.get("images")
        if not isinstance(images, list):
            issues.append(f"id={rid} images must be array")
            continue

        for image in images:
            if not isinstance(image, dict):
                issues.append(f"id={rid} image entry must be object")
                continue
            for key in ["path", "category", "altText", "sourceUrl"]:
                if not isinstance(image.get(key), str):
                    issues.append(f"id={rid} image.{key} must be string")
            score = image.get("score")
            if not isinstance(score, int):
                issues.append(f"id={rid} image.score must be int")

            image_path = image.get("path", "")
            if image_path:
                full_path = project_root / image_path
                if not full_path.exists():
                    issues.append(f"id={rid} missing image file: {image_path}")

    return issues


def export_dataset(db_path: Path, out_dir: Path, project_root: Path, phase1_markdown_path: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        distillery_rows = conn.execute(
            """
            SELECT
                d.id,
                d.name,
                d.slug,
                COALESCE(d.country, '') AS country,
                COALESCE(d.region, '') AS region,
                COALESCE(d.section, '') AS section,
                COALESCE(d.official_site, '') AS official_site,
                COALESCE(d.website_confidence, '') AS website_confidence,
                COALESCE(d.operating_status, '') AS operating_status,
                COALESCE(d.study_status, '') AS study_status,
                COALESCE(d.why_study, '') AS why_study,
                COALESCE(d.description, '') AS description,
                COALESCE(d.key_focus, '') AS key_focus,
                COALESCE(d.notes, '') AS notes,
                COALESCE(d.search_terms, '') AS search_terms,
                COALESCE(d.search_metadata_json, '') AS search_metadata_json
            FROM distilleries d
            ORDER BY d.id
            """
        ).fetchall()

        style_rows = conn.execute(
            """
            SELECT ds.distillery_id, s.name
            FROM distillery_styles ds
            JOIN styles s ON s.id = ds.style_id
            ORDER BY ds.distillery_id, s.name
            """
        ).fetchall()

        image_rows = conn.execute(
            """
            SELECT
                i.distillery_id,
                COALESCE(i.local_path, '') AS local_path,
                COALESCE(i.category, '') AS category,
                COALESCE(i.alt_text, '') AS alt_text,
                COALESCE(i.source_url, '') AS source_url,
                COALESCE(i.score, 0) AS score
            FROM images i
            ORDER BY i.distillery_id, i.score DESC, i.id ASC
            """
        ).fetchall()

        db_distillery_count = conn.execute("SELECT COUNT(*) AS c FROM distilleries").fetchone()["c"]

    styles_by_distillery: dict[int, list[str]] = {}
    for row in style_rows:
        styles_by_distillery.setdefault(int(row["distillery_id"]), []).append(row["name"])

    images_by_distillery: dict[int, list[dict[str, Any]]] = {}
    for row in image_rows:
        did = int(row["distillery_id"])
        images_by_distillery.setdefault(did, []).append(
            {
                "path": _normalize_path(row["local_path"]),
                "category": row["category"],
                "altText": row["alt_text"],
                "sourceUrl": row["source_url"],
                "score": int(row["score"]),
            }
        )

    distilleries: list[dict[str, Any]] = []
    for row in distillery_rows:
        did = int(row["id"])
        images = images_by_distillery.get(did, [])
        distilleries.append(
            {
                "id": did,
                "name": row["name"],
                "slug": row["slug"],
                "country": row["country"],
                "region": row["region"],
                "section": row["section"],
                "officialSite": row["official_site"],
                "websiteConfidence": row["website_confidence"],
                "operatingStatus": row["operating_status"],
                "studyStatus": row["study_status"],
                "whyStudy": row["why_study"],
                "description": row["description"],
                "keyFocus": row["key_focus"],
                "notes": row["notes"],
                "searchTerms": row["search_terms"],
                "searchMetadata": row["search_metadata_json"],
                "styles": styles_by_distillery.get(did, []),
                "imageCount": len(images),
                "images": images,
            }
        )

    taxonomy = {
        "countries": sorted({item["country"] for item in distilleries if item["country"]}),
        "regions": sorted({item["region"] for item in distilleries if item["region"]}),
        "styles": sorted({style for item in distilleries for style in item["styles"]}),
        "operatingStatuses": sorted({item["operatingStatus"] for item in distilleries if item["operatingStatus"]}),
        "websiteConfidenceLevels": sorted(
            {item["websiteConfidence"] for item in distilleries if item["websiteConfidence"]}
        ),
        "imageCategories": sorted(
            {
                image["category"]
                for item in distilleries
                for image in item["images"]
                if image["category"]
            }
        ),
    }

    curriculum_phase1 = {
        "source": phase1_markdown_path.name,
        "rawMarkdown": phase1_markdown_path.read_text(encoding="utf-8") if phase1_markdown_path.exists() else "",
    }

    issues = _validate_records(distilleries, project_root)
    if len(distilleries) != db_distillery_count:
        issues.append(
            f"distillery count mismatch: exported={len(distilleries)} db={db_distillery_count}"
        )

    if issues:
        issue_text = "\n".join(f"- {issue}" for issue in issues)
        raise ValueError(f"Dataset validation failed:\n{issue_text}")

    generated_at = datetime.now(timezone.utc).isoformat()
    schema_version = "1.0.0"

    distilleries_payload = {"schemaVersion": schema_version, "generatedAt": generated_at, "distilleries": distilleries}
    taxonomy_payload = {"schemaVersion": schema_version, "generatedAt": generated_at, **taxonomy}
    curriculum_payload = {"schemaVersion": schema_version, "generatedAt": generated_at, **curriculum_phase1}

    distilleries_path = out_dir / "distilleries.json"
    taxonomy_path = out_dir / "taxonomy.json"
    curriculum_path = out_dir / "curriculum-phase1.json"
    manifest_path = out_dir / "dataset-manifest.json"

    distilleries_path.write_text(json.dumps(distilleries_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    taxonomy_path.write_text(json.dumps(taxonomy_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    curriculum_path.write_text(json.dumps(curriculum_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schemaVersion": schema_version,
        "generatedAt": generated_at,
        "recordCount": len(distilleries),
        "checksums": {
            "distilleries.json": _json_checksum(distilleries_payload),
            "taxonomy.json": _json_checksum(taxonomy_payload),
            "curriculum-phase1.json": _json_checksum(curriculum_payload),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    return {
        "outDir": str(out_dir),
        "recordCount": len(distilleries),
        "schemaVersion": schema_version,
        "generatedAt": generated_at,
        "files": [
            str(distilleries_path),
            str(taxonomy_path),
            str(curriculum_path),
            str(manifest_path),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SQLite distillery data to JSON for web/PWA use.")
    parser.add_argument("--db", default="data/distilleries.db", help="Path to source SQLite database.")
    parser.add_argument("--out-dir", default="data/web", help="Output directory for JSON dataset files.")
    parser.add_argument(
        "--phase1-markdown",
        default="PHASE_1_ORIENTATION_FOUNDATIONS_EXPANDED.md",
        help="Optional Phase 1 markdown file to export as curriculum-phase1.json.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    db_path = (project_root / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db)
    out_dir = (project_root / args.out_dir).resolve() if not Path(args.out_dir).is_absolute() else Path(args.out_dir)
    phase1_markdown_path = (
        (project_root / args.phase1_markdown).resolve()
        if not Path(args.phase1_markdown).is_absolute()
        else Path(args.phase1_markdown)
    )

    result = export_dataset(db_path, out_dir, project_root, phase1_markdown_path)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
