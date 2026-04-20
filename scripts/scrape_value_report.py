#!/usr/bin/env python3
"""
Scrape Value Report
-------------------
Summarises the last N scrape runs and overall extraction quality.

Usage:
    python3 scripts/scrape_value_report.py [--runs 10] [--data-dir data]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── helpers ────────────────────────────────────────────────────────────────────

def fmt_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso


def pct(n: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{n / total * 100:.0f}%"


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def subsection(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(0, 66 - len(title)))


def truncate_text(text: str | None, max_len: int = 120) -> str:
    if not text:
        return "—"
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def latest_file(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


# ── log parsing ────────────────────────────────────────────────────────────────

_RUN_COMPLETE_RE = re.compile(
    r'"sites_processed"\s*:\s*(\d+).*?"sites_succeeded"\s*:\s*(\d+).*?'
    r'"sites_failed"\s*:\s*(\d+).*?"pages_processed"\s*:\s*(\d+).*?'
    r'"pages_skipped"\s*:\s*(\d+).*?"pages_failed"\s*:\s*(\d+).*?'
    r'"pages_summarized"\s*:\s*(\d+)',
    re.S,
)


def parse_iteration_log(log_path: Path) -> dict[str, Any] | None:
    """Extract summary stats from a crawl_iteration_N.log file."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = _RUN_COMPLETE_RE.search(text)
    if not m:
        return None

    sites, succeeded, failed, pages, skipped, pfailed, summarized = (
        int(x) for x in m.groups()
    )

    # pull target-window line
    target_line = next(
        (l for l in text.splitlines() if "[target-window]" in l), ""
    )
    target_match = re.search(r"selected=(\d+)/(\d+)", target_line)
    selected = int(target_match.group(1)) if target_match else None
    total_pool = int(target_match.group(2)) if target_match else None

    # count distinct distilleries that had pages summarized
    summarized_names = re.findall(r"\[distillery-sync\] updated=True", text)

    return {
        "sites_processed": sites,
        "sites_succeeded": succeeded,
        "sites_failed": failed,
        "pages_processed": pages,
        "pages_skipped": skipped,
        "pages_failed": pfailed,
        "pages_summarized": summarized,
        "distilleries_updated": len(summarized_names),
        "target_selected": selected,
        "target_pool": total_pool,
    }


def parse_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(manifest_path.read_text())
    except Exception:
        return {}
    return data


def parse_blog_suggestions(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "items": []}

    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current:
                items.append(current)
            current = {"title": line[3:].strip(), "source": ""}
        elif current and line.startswith("- "):
            current["source"] = line[2:].strip()
    if current:
        items.append(current)

    return {"path": str(path), "items": items}


def parse_lesson_suggestions(content_dir: Path) -> dict[str, Any]:
    candidates = [
        path for path in content_dir.glob("LESSON_CONTENT_EDITS*.md")
        if "TABLE" not in path.name
    ]
    suggestion_path = latest_file(candidates)
    if suggestion_path is None:
        return {"path": None, "items": [], "counts": {}, "generated_at": None}

    items: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    current_phase = ""
    current_item: dict[str, str] | None = None
    current_field: str | None = None
    generated_at = None

    for raw_line in suggestion_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("Generated:"):
            generated_at = stripped.split(":", 1)[1].strip()
            continue

        if stripped.startswith("## PHASE_"):
            if current_item:
                items.append(current_item)
                counts[current_phase] = counts.get(current_phase, 0) + 1
                current_item = None
            current_phase = stripped[3:].strip()
            current_field = None
            continue

        if stripped.startswith("### "):
            if current_item:
                items.append(current_item)
                counts[current_phase] = counts.get(current_phase, 0) + 1
            current_item = {
                "phase_file": current_phase,
                "id": stripped[4:].strip(),
                "target_section": "",
                "edit_action": "",
                "source_file": "",
            }
            current_field = None
            continue

        if stripped == "Target section:":
            current_field = "target_section"
            continue
        if stripped == "Edit action:":
            current_field = "edit_action"
            continue
        if stripped == "Source file:":
            current_field = "source_file"
            continue

        if current_item and current_field and stripped.startswith("- ") and not current_item[current_field]:
            value = stripped[2:].strip().strip("`")
            current_item[current_field] = value

    if current_item:
        items.append(current_item)
        counts[current_phase] = counts.get(current_phase, 0) + 1

    return {
        "path": str(suggestion_path),
        "items": items,
        "counts": counts,
        "generated_at": generated_at,
    }


def parse_quiz_suggestions(quiz_dir: Path) -> dict[str, Any]:
    latest_run_file = quiz_dir / "latest_run.txt"
    run_id = latest_run_file.read_text(encoding="utf-8", errors="replace").strip() if latest_run_file.exists() else ""
    if not run_id:
        run_dirs = sorted([path for path in quiz_dir.glob("run_*") if path.is_dir()])
        run_id = run_dirs[-1].name.removeprefix("run_") if run_dirs else ""

    if not run_id:
        return {"run_id": None, "path": None, "counts": {}, "items": [], "generated_at": None}

    run_path = quiz_dir / f"run_{run_id}"
    counts: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    generated_at = None

    for phase_file in sorted(run_path.glob("phase_*.json"), key=lambda path: int(path.stem.split("_")[1])):
        try:
            payload = json.loads(phase_file.read_text())
        except Exception:
            continue

        phase = str(payload.get("phase", phase_file.stem.split("_")[1]))
        phase_items = payload.get("items", [])
        counts[phase] = len(phase_items)
        if generated_at is None:
            generated_at = payload.get("generated_at")
        for item in phase_items:
            items.append(
                {
                    "phase": phase,
                    "id": item.get("id", ""),
                    "quiz_type": item.get("quiz_type", ""),
                    "stem": item.get("stem", ""),
                    "source": item.get("source", ""),
                    "confidence": item.get("confidence"),
                }
            )

    return {
        "run_id": run_id,
        "path": str(run_path),
        "counts": counts,
        "items": items,
        "generated_at": generated_at,
    }


# ── run summary ────────────────────────────────────────────────────────────────

def collect_run_summaries(run_manifests_dir: Path, n: int) -> list[dict]:
    """Return summary dicts for the last N pipeline runs."""
    run_dirs = sorted(
        [d for d in run_manifests_dir.iterdir() if d.is_dir()],
        reverse=True,
    )[:n]

    summaries: list[dict] = []
    for run_dir in run_dirs:
        manifest = parse_manifest(run_dir / "manifest.json")
        run_id = manifest.get("run_id", run_dir.name)
        started_at = manifest.get("started_at", "")
        ended_at = manifest.get("ended_at", "")
        status = manifest.get("status", "?")

        # aggregate across all iteration logs
        totals: dict[str, int] = {
            "sites_processed": 0,
            "sites_succeeded": 0,
            "sites_failed": 0,
            "pages_processed": 0,
            "pages_skipped": 0,
            "pages_failed": 0,
            "pages_summarized": 0,
            "distilleries_updated": 0,
        }
        iteration_logs = sorted(run_dir.glob("crawl_iteration_*.log"))
        for log_path in iteration_logs:
            parsed = parse_iteration_log(log_path)
            if parsed:
                for k in totals:
                    totals[k] += parsed.get(k, 0)

        # image labeling
        image_phases = manifest.get("phases", {})
        img_data = image_phases.get("image_labeling", {})
        images_total = img_data.get("images_total", 0)
        images_labeled = img_data.get("images_labeled", 0)
        label_counts = img_data.get("label_counts", {})
        review_bridge = image_phases.get("review_action_bridge", {})

        # review quality signal
        review_path = run_dir / "review.json"
        review_quality = None
        review_gaps: list[str] = []
        next_run_priorities: list[dict[str, Any]] = []
        next_run_actions: list[dict[str, Any]] = []
        if review_path.exists():
            try:
                rev = json.loads(review_path.read_text())
                review_quality = rev.get("summary", {}).get("overall_quality")
                review_gaps = rev.get("summary", {}).get("notable_gaps", [])
                next_run_priorities = rev.get("priorities_next_run", [])
                next_run_actions = rev.get("action_items", [])
            except Exception:
                pass

        # duration
        duration_s = None
        if started_at and ended_at:
            try:
                s = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                e = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                duration_s = int((e - s).total_seconds())
            except Exception:
                pass

        summaries.append(
            {
                "run_id": run_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "status": status,
                "duration_s": duration_s,
                "iterations": len(iteration_logs),
                **totals,
                "images_total": images_total,
                "images_labeled": images_labeled,
                "label_counts": label_counts,
                "review_quality": review_quality,
                "review_gaps": review_gaps,
                "bridge_reasons": review_bridge.get("reasons", []),
                "bridge_overrides": review_bridge.get("overrides", {}),
                "next_run_priorities": next_run_priorities,
                "next_run_actions": next_run_actions,
            }
        )

    return summaries


# ── overall DB summary ─────────────────────────────────────────────────────────

def distilleries_summary(db_path: Path) -> dict:
    if not db_path.exists():
        return {}
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            """
            SELECT
                COUNT(*) as total,
                COUNT(description) as with_desc,
                COUNT(last_summarized_at) as summarized,
                COUNT(products_json) as with_products,
                COUNT(people_json) as with_people,
                COUNT(CASE WHEN website_confidence = 'high' THEN 1 END) as high_conf,
                COUNT(CASE WHEN website_confidence = 'medium' THEN 1 END) as med_conf,
                COUNT(CASE WHEN website_confidence = 'low' THEN 1 END) as low_conf
            FROM distilleries
            """
        ).fetchone()

        pages_row = con.execute("SELECT COUNT(*) FROM source_pages").fetchone()

        diag_row = con.execute(
            """
            SELECT
                COUNT(*) as attempts,
                SUM(success) as successes,
                SUM(pages_visited) as pages_visited,
                SUM(images_downloaded) as images_downloaded,
                MAX(attempted_at) as last_crawl
            FROM crawl_diagnostics
            """
        ).fetchone()

        # top 5 distilleries by pages scraped
        top_distilleries = con.execute(
            """
            SELECT d.name, COUNT(sp.id) as page_count
            FROM distilleries d
            LEFT JOIN source_pages sp ON sp.distillery_id = d.id
            GROUP BY d.id
            ORDER BY page_count DESC
            LIMIT 5
            """
        ).fetchall()

        # products count
        product_rows = con.execute(
            "SELECT products_json FROM distilleries WHERE products_json IS NOT NULL"
        ).fetchall()
        total_products = 0
        for (pj,) in product_rows:
            try:
                total_products += len(json.loads(pj))
            except Exception:
                pass

        people_rows = con.execute(
            "SELECT people_json FROM distilleries WHERE people_json IS NOT NULL"
        ).fetchall()
        total_people = 0
        for (pj,) in people_rows:
            try:
                total_people += len(json.loads(pj))
            except Exception:
                pass

    finally:
        con.close()

    return {
        "total": row[0],
        "with_desc": row[1],
        "summarized": row[2],
        "with_products": row[3],
        "with_people": row[4],
        "high_conf": row[5],
        "med_conf": row[6],
        "low_conf": row[7],
        "total_source_pages": pages_row[0],
        "crawl_attempts": diag_row[0],
        "crawl_successes": diag_row[1] or 0,
        "pages_visited": diag_row[2] or 0,
        "images_downloaded": diag_row[3] or 0,
        "last_crawl": diag_row[4],
        "top_distilleries_by_pages": top_distilleries,
        "total_products": total_products,
        "total_people": total_people,
    }


def resources_summary(db_path: Path) -> dict:
    if not db_path.exists():
        return {}
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            """
            SELECT
                COUNT(*) as total,
                COUNT(description) as with_desc,
                COUNT(last_summarized_at) as summarized,
                COUNT(summary_markdown) as with_summary
            FROM resources
            """
        ).fetchone()

        by_category = con.execute(
            "SELECT category, COUNT(*) FROM resources GROUP BY category ORDER BY 2 DESC"
        ).fetchall()

    finally:
        con.close()

    return {
        "total": row[0],
        "with_desc": row[1],
        "summarized": row[2],
        "with_summary": row[3],
        "by_category": by_category,
    }


def metadata_summary(data_dir: Path) -> dict:
    """Count entries in each metadata index file."""
    files = {
        "distillery_names": "metadata_distillery_names.md",
        "product_names": "metadata_product_names.md",
        "people": "metadata_people.md",
        "flavor_words": "metadata_flavor_profile_words.md",
        "glossary_terms": "metadata_glossary_terms.md",
        "company_names": "metadata_company_names.md",
        "chemical_names": "metadata_chemical_names.md",
        "tool_names": "metadata_distillery_tool_names.md",
    }
    counts: dict[str, int] = {}
    for key, fname in files.items():
        path = data_dir / fname
        if path.exists():
            lines = [
                l for l in path.read_text(encoding="utf-8", errors="replace").splitlines()
                if l.strip() and not l.startswith("#") and not l.startswith("---")
            ]
            counts[key] = len(lines)
        else:
            counts[key] = 0
    return counts


def content_suggestions_summary(data_dir: Path) -> dict[str, Any]:
    return {
        "lesson": parse_lesson_suggestions(data_dir / "content_recommendations"),
        "quiz": parse_quiz_suggestions(data_dir / "quiz_suggestions"),
        "blog": parse_blog_suggestions(data_dir / "metadata_blog_suggestions.md"),
    }


# ── rendering ──────────────────────────────────────────────────────────────────

def render_run_summaries(runs: list[dict]) -> None:
    section(f"LAST {len(runs)} SCRAPE RUNS")

    for i, r in enumerate(runs, 1):
        dur = f"{r['duration_s'] // 60}m {r['duration_s'] % 60}s" if r["duration_s"] is not None else "—"
        subsection(f"Run {i}: {r['run_id']}  [{r['status']}]  ⏱ {dur}")
        print(f"  Started   : {fmt_dt(r['started_at'])}")
        print(f"  Ended     : {fmt_dt(r['ended_at'])}")
        print(f"  Iterations: {r['iterations']}")
        print()
        print(f"  Sites     : {r['sites_processed']} processed  "
              f"({r['sites_succeeded']} ok / {r['sites_failed']} failed)")
        print(f"  Pages     : {r['pages_processed']} crawled  "
              f"| {r['pages_summarized']} summarized  "
              f"| {r['pages_skipped']} skipped  "
              f"| {r['pages_failed']} failed")
        print(f"  Distill.  : {r['distilleries_updated']} updated")
        if r["images_total"]:
            label_str = "  ".join(
                f"{k}={v}" for k, v in sorted(r["label_counts"].items()) if v
            ) or "none"
            print(f"  Images    : {r['images_labeled']}/{r['images_total']} labeled  ({label_str})")
        if r["review_quality"]:
            print(f"  Quality   : {r['review_quality']}")
        if r["review_gaps"]:
            for g in r["review_gaps"]:
                print(f"    ⚠ Notable gap: {g}")
        if r["bridge_reasons"] or r["bridge_overrides"]:
            print("  Applied prior review guidance:")
            for reason in r["bridge_reasons"]:
                print(f"    - {truncate_text(reason, 110)}")
            for key, value in sorted(r["bridge_overrides"].items()):
                print(f"    - override {key}={value}")
        if r["next_run_priorities"]:
            print("  Next iteration guidance:")
            for item in r["next_run_priorities"][:3]:
                score = item.get("priority_score")
                score_text = f"{score:.2f}" if isinstance(score, (int, float)) else "?"
                print(
                    f"    - [{item.get('type', 'unknown')}, score={score_text}] "
                    f"{item.get('name', 'Unnamed')}: {truncate_text(item.get('reason', ''), 95)}"
                )
        if r["next_run_actions"]:
            print("  Suggested engine follow-ups:")
            for item in r["next_run_actions"][:2]:
                print(
                    f"    - [{item.get('severity', 'unknown')}] {item.get('title', 'Untitled')}: "
                    f"{truncate_text(item.get('suggested_fix', ''), 95)}"
                )


def render_content_suggestions(suggestions: dict[str, Any], limit: int) -> None:
    section("EXTRACTED CONTENT SUGGESTIONS")

    lesson = suggestions["lesson"]
    subsection("Lesson Plan Updates")
    print(f"  Source file           : {lesson.get('path') or '—'}")
    print(f"  Generated             : {fmt_dt(lesson.get('generated_at'))}")
    print(f"  Total lesson edits    : {len(lesson.get('items', []))}")
    if lesson.get("counts"):
        phase_counts = "  ".join(
            f"{phase.replace('PHASE_', 'P').replace('_EXPANDED.md', '')}={count}"
            for phase, count in sorted(lesson["counts"].items())
        )
        print(f"  By phase              : {phase_counts}")
    for item in lesson.get("items", [])[:limit]:
        print(
            f"    - {item.get('id', '—')} | {item.get('phase_file', '—')} | "
            f"{truncate_text(item.get('edit_action', ''), 75)} | "
            f"target {truncate_text(item.get('target_section', ''), 55)}"
        )

    quiz = suggestions["quiz"]
    subsection("Quiz Suggestions")
    print(f"  Source run            : {quiz.get('run_id') or '—'}")
    print(f"  Source dir            : {quiz.get('path') or '—'}")
    print(f"  Generated             : {fmt_dt(quiz.get('generated_at'))}")
    print(f"  Total quiz items      : {len(quiz.get('items', []))}")
    if quiz.get("counts"):
        phase_counts = "  ".join(
            f"P{phase}={count}" for phase, count in sorted(quiz["counts"].items(), key=lambda item: int(item[0]))
        )
        print(f"  By phase              : {phase_counts}")
    for item in quiz.get("items", [])[:limit]:
        confidence = item.get("confidence")
        confidence_text = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "—"
        print(
            f"    - {item.get('id', '—')} | P{item.get('phase', '—')} | {item.get('quiz_type', '—')} | "
            f"conf={confidence_text} | {truncate_text(item.get('stem', ''), 90)}"
        )

    blog = suggestions["blog"]
    subsection("Blog Suggestions")
    print(f"  Source file           : {blog.get('path') or '—'}")
    print(f"  Total blog ideas      : {len(blog.get('items', []))}")
    for item in blog.get("items", [])[:limit]:
        print(
            f"    - {truncate_text(item.get('title', ''), 70)} | "
            f"{truncate_text(item.get('source', ''), 95)}"
        )


def render_overall(dist: dict, res: dict, meta: dict) -> None:
    section("OVERALL EXTRACTION SUMMARY")

    subsection("Distilleries DB")
    total = dist.get("total", 0)
    print(f"  Total distilleries    : {total}")
    print(f"  With description      : {dist.get('with_desc', 0)}  ({pct(dist.get('with_desc', 0), total)})")
    print(f"  Summarized            : {dist.get('summarized', 0)}  ({pct(dist.get('summarized', 0), total)})")
    print(f"  With products         : {dist.get('with_products', 0)}  ({pct(dist.get('with_products', 0), total)})")
    print(f"  With people           : {dist.get('with_people', 0)}  ({pct(dist.get('with_people', 0), total)})")
    print()
    print(f"  Website confidence    : high={dist.get('high_conf',0)}  "
          f"medium={dist.get('med_conf',0)}  low={dist.get('low_conf',0)}")
    print()
    print(f"  Source pages          : {dist.get('total_source_pages', 0)}")
    print(f"  Total products        : {dist.get('total_products', 0)}")
    print(f"  Total people          : {dist.get('total_people', 0)}")
    print()
    print(f"  Crawl attempts (all)  : {dist.get('crawl_attempts', 0)}  "
          f"({dist.get('crawl_successes', 0)} succeeded)")
    print(f"  Pages visited (all)   : {dist.get('pages_visited', 0)}")
    print(f"  Images downloaded     : {dist.get('images_downloaded', 0)}")
    print(f"  Last crawl activity   : {fmt_dt(dist.get('last_crawl'))}")

    top = dist.get("top_distilleries_by_pages", [])
    if top:
        print()
        print("  Top distilleries by pages scraped:")
        for name, n in top:
            print(f"    {n:4d}  {name}")

    subsection("Resources DB")
    rtotal = res.get("total", 0)
    print(f"  Total resources       : {rtotal}")
    print(f"  With description      : {res.get('with_desc', 0)}  ({pct(res.get('with_desc', 0), rtotal)})")
    print(f"  Summarized            : {res.get('summarized', 0)}  ({pct(res.get('summarized', 0), rtotal)})")
    for cat, count in res.get("by_category", []):
        print(f"    {count:4d}  {cat or 'uncategorized'}")

    subsection("Metadata Indexes")
    for key, count in meta.items():
        label = key.replace("_", " ").title()
        print(f"  {label:<22}: {count}")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape value report")
    parser.add_argument("--runs", type=int, default=10, help="Number of recent runs to show")
    parser.add_argument(
        "--suggestion-limit",
        type=int,
        default=10,
        help="Number of lesson/quiz/blog suggestions to display per section",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Path to data directory (default: data)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    run_manifests_dir = data_dir / "run_manifests"

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║              WHISKY SCRAPE VALUE REPORT                             ║")
    print(f"║  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'):<57}║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    # ── run summaries ──────────────────────────────────────────────────────────
    if run_manifests_dir.exists():
        runs = collect_run_summaries(run_manifests_dir, args.runs)
        if runs:
            render_run_summaries(runs)
        else:
            print("\n  No run manifests found.")
    else:
        print(f"\n  Run manifests directory not found: {run_manifests_dir}")

    # ── overall summaries ──────────────────────────────────────────────────────
    dist = distilleries_summary(data_dir / "distilleries.db")
    res = resources_summary(data_dir / "resources.db")
    meta = metadata_summary(data_dir)
    suggestions = content_suggestions_summary(data_dir)
    render_content_suggestions(suggestions, args.suggestion_limit)
    render_overall(dist, res, meta)

    print()
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
