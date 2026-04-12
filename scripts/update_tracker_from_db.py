#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def norm_site(url: str) -> str:
    if not url or not url.startswith("http"):
        return ""
    p = urlparse(url.strip())
    host = p.netloc.lower().replace("www.", "")
    return f"{p.scheme.lower()}://{host}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Update tracker status/notes columns from distilleries DB data.")
    parser.add_argument("--db", default="data/distilleries.db")
    parser.add_argument("--tracker", default="DISTILLERY_STUDY_TRACKER.md")
    args = parser.parse_args()

    db_path = (PROJECT_ROOT / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db)
    tracker_path = (PROJECT_ROOT / args.tracker).resolve() if not Path(args.tracker).is_absolute() else Path(args.tracker)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name, official_site, study_status, source_headers FROM distilleries"
    ).fetchall()
    conn.close()

    by_name = {str(r[0]).strip().lower(): (r[2] or "Not started", r[3] or "") for r in rows}
    by_site = {norm_site(r[1] or ""): (r[2] or "Not started", r[3] or "") for r in rows if r[1]}

    lines = tracker_path.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []

    header_cols: list[str] = []
    status_idx = -1
    notes_idx = -1
    site_idx = -1

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if all(c.startswith("---") for c in cols):
                out_lines.append(line)
                continue

            lower_cols = [c.lower() for c in cols]
            is_header = any(c in {"status", "study status"} for c in lower_cols)
            if is_header:
                header_cols = cols
                lower_headers = lower_cols
                status_idx = -1
                notes_idx = -1
                site_idx = -1
                for i, h in enumerate(lower_headers):
                    if h in {"status", "study status"}:
                        status_idx = i
                    if h == "notes":
                        notes_idx = i
                    if h in {"official site", "website"}:
                        site_idx = i
                out_lines.append(line)
                continue

            # Data row for the current table header.
            if header_cols and len(cols) >= len(header_cols) and status_idx >= 0 and notes_idx >= 0:
                cols = cols[: len(header_cols)]
                name = cols[0].strip().lower()
                site = cols[site_idx].strip() if 0 <= site_idx < len(cols) else ""
                status_note = by_name.get(name)
                if not status_note and site:
                    status_note = by_site.get(norm_site(site))
                if status_note:
                    status, source_header = status_note
                    cols[status_idx] = status or "Not started"
                    if source_header and not source_header.startswith("Distillery / Brand"):
                        cols[notes_idx] = source_header
                    elif cols[notes_idx].startswith("Distillery / Brand"):
                        cols[notes_idx] = ""
                out_lines.append("| " + " | ".join(cols) + " |")
            else:
                out_lines.append(line)
            continue

        out_lines.append(line)

    tracker_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Updated tracker: {tracker_path}")


if __name__ == "__main__":
    main()
