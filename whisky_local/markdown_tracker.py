from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


COUNTRY_MARKERS = {
    "Scotland": "Scotland",
    "Ireland": "Ireland",
    "United States": "United States",
    "Canada": "Canada",
    "Japan": "Japan",
    "Australia": "Australia",
    "India, Taiwan, and Other World Whisky Regions": "World Whisky",
}


@dataclass
class DistilleryRecord:
    name: str
    country: str
    region: str
    section: str
    why_study: str
    official_site: str
    key_focus: str
    study_status: str
    operating_status: str
    website_confidence: str
    notes: str
    source_headers: str


def parse_markdown_table_row(line: str) -> list[str]:
    trimmed = line.strip()
    if not trimmed.startswith("|"):
        return []
    parts = [cell.strip() for cell in trimmed.strip("|").split("|")]
    return parts


def is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False
    for cell in cells:
        if not re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")):
            return False
    return True


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def infer_style_tags(text: str) -> set[str]:
    lowered = text.lower()
    tags: set[str] = set()
    keyword_map = {
        "single malt": "single malt",
        "peated": "peated",
        "unpeated": "unpeated",
        "sherry": "sherry cask",
        "bourbon": "bourbon cask",
        "port": "port cask",
        "rye": "rye",
        "cask strength": "cask strength",
        "single cask": "single cask",
        "small batch": "small batch",
        "wheated": "wheated",
        "corn": "corn-forward",
        "pot still": "pot still",
        "column": "column still",
        "tourism": "visitor experience",
        "coastal": "coastal maturation",
        "warm-climate": "warm climate maturation",
        "tropical": "tropical maturation",
        "fortified": "fortified wine cask",
        "solera": "solera",
    }

    for needle, tag in keyword_map.items():
        if needle in lowered:
            tags.add(tag)

    return tags


def parse_tracker(path: Path) -> Iterable[tuple[DistilleryRecord, set[str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()

    heading_stack: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            i += 1
            continue

        if line.strip().startswith("|"):
            header_cells = parse_markdown_table_row(line)
            if not header_cells:
                i += 1
                continue

            if i + 1 >= len(lines):
                i += 1
                continue

            separator_cells = parse_markdown_table_row(lines[i + 1])
            if not is_separator_row(separator_cells):
                i += 1
                continue

            table_rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                row_cells = parse_markdown_table_row(lines[j])
                if row_cells and not is_separator_row(row_cells):
                    table_rows.append(row_cells)
                j += 1

            source_headers = ", ".join(header_cells)
            current_section = heading_stack[-1][1] if heading_stack else "Unknown"
            country = "Unknown"
            region_heading = ""

            for _, heading in heading_stack:
                for marker, canonical in COUNTRY_MARKERS.items():
                    if marker in heading:
                        country = canonical
                region_heading = heading

            header_map = {name.lower(): idx for idx, name in enumerate(header_cells)}

            def value_from_row(row: list[str], *candidates: str) -> str:
                for candidate in candidates:
                    idx = header_map.get(candidate.lower())
                    if idx is not None and idx < len(row):
                        return row[idx].strip()
                return ""

            for row in table_rows:
                if len(row) < 2:
                    continue

                name = value_from_row(row, "Distillery / Brand", "Distillery", "Brand")
                if not name:
                    continue

                region = value_from_row(row, "Region", "Likely Region") or region_heading
                why_study = value_from_row(row, "Why Study It", "Reason to Queue")
                official_site = value_from_row(
                    row,
                    "Official Site",
                    "Website",
                    "Primary Site (if verified)",
                )
                key_focus = value_from_row(
                    row,
                    "Key Production or Style Focus",
                    "Reason to Queue",
                )
                study_status = value_from_row(row, "Study Status", "Status")
                operating_status = value_from_row(row, "Operating Status")
                website_confidence = value_from_row(row, "Website Confidence")
                notes = value_from_row(row, "Notes")

                all_text = " ".join(
                    [name, region, why_study, key_focus, notes, study_status, operating_status]
                )
                style_tags = infer_style_tags(all_text)

                yield DistilleryRecord(
                    name=name,
                    country=country,
                    region=region,
                    section=current_section,
                    why_study=why_study,
                    official_site=official_site,
                    key_focus=key_focus,
                    study_status=study_status,
                    operating_status=operating_status,
                    website_confidence=website_confidence,
                    notes=notes,
                    source_headers=source_headers,
                ), style_tags

            i = j
            continue

        i += 1
