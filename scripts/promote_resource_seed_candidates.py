#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalize_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object payload in {path}")
    resources = payload.get("resources")
    if not isinstance(resources, list):
        raise ValueError(f"Expected 'resources' array in {path}")
    return payload


def validate_resource(row: Any, source: Path, index: int) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"Resource at index {index} in {source} must be an object")
    name = str(row.get("name", "")).strip()
    url = str(row.get("url", "")).strip()
    if not name or not url.startswith("http"):
        raise ValueError(f"Invalid resource at index {index} in {source}: missing name or http url")
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote curated resource seed candidates into the main seed file.")
    parser.add_argument("--seed", default="data/resource_sites_seed.json", help="Path to the main seed JSON.")
    parser.add_argument(
        "--candidates",
        default="data/resource_sites_seed_candidates.json",
        help="Path to the curated candidate JSON.",
    )
    parser.add_argument("--count", type=int, default=8, help="Maximum number of new candidates to promote.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be added without modifying files.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    args = parser.parse_args()

    seed_path = Path(args.seed).resolve()
    candidate_path = Path(args.candidates).resolve()

    seed_payload = load_payload(seed_path)
    candidate_payload = load_payload(candidate_path)

    seed_resources = [validate_resource(row, seed_path, idx) for idx, row in enumerate(seed_payload["resources"], start=1)]
    candidate_resources = [
        validate_resource(row, candidate_path, idx) for idx, row in enumerate(candidate_payload["resources"], start=1)
    ]

    existing_urls = {normalize_url(row.get("url", "")) for row in seed_resources}
    existing_names = {str(row.get("name", "")).strip().casefold() for row in seed_resources}

    additions: list[dict[str, Any]] = []
    for row in candidate_resources:
        url = normalize_url(row.get("url", ""))
        name = str(row.get("name", "")).strip()
        if not url or not name:
            continue
        if url in existing_urls or name.casefold() in existing_names:
            continue
        additions.append(row)
        existing_urls.add(url)
        existing_names.add(name.casefold())
        if len(additions) >= max(0, args.count):
            break

    if additions and not args.dry_run:
        updated_payload = dict(seed_payload)
        updated_payload["resources"] = seed_resources + additions
        seed_path.write_text(json.dumps(updated_payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    promoted_urls = {normalize_url(row.get("url", "")) for row in additions}
    remaining_candidates = 0
    for row in candidate_resources:
        url = normalize_url(row.get("url", ""))
        name = str(row.get("name", "")).strip().casefold()
        if url in promoted_urls:
            continue
        if url in {normalize_url(item.get("url", "")) for item in seed_resources}:
            continue
        if name in {str(item.get("name", "")).strip().casefold() for item in seed_resources}:
            continue
        remaining_candidates += 1

    result = {
        "added": len(additions),
        "added_names": [str(row.get("name", "")).strip() for row in additions],
        "dry_run": args.dry_run,
        "remaining_candidates": remaining_candidates,
        "seed": str(seed_path),
        "candidates": str(candidate_path),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=True))
        return

    if additions:
        mode = "Would add" if args.dry_run else "Added"
        print(f"{mode} {len(additions)} resource seed candidate(s):")
        for name in result["added_names"]:
            print(f"- {name}")
    else:
        print("No resource seed candidates available to add.")
    print(f"Remaining candidates: {remaining_candidates}")


if __name__ == "__main__":
    main()