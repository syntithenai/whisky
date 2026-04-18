#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


def run_step(cmd: list[str]) -> str:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stdout}")
    return result.stdout.strip()


def load_progress_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_progress_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _safe_read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _source_label(path_str: str) -> str:
    stem = Path(path_str).stem
    return stem.replace("-", " ").replace("_", " ").strip() or "source"


def _extract_provenance_excerpt(path_str: str, rationale: str) -> str:
    text = _safe_read_text(Path(path_str))
    lines = [line.strip() for line in text.splitlines()[:80] if line.strip()]
    heading = ""
    url = ""
    for line in lines:
        if not heading and line.startswith("#"):
            heading = re.sub(r"^#+\s*", "", line).strip()
        if not url:
            m = re.search(r"-\s*URL:\s*(https?://\S+)", line)
            if m:
                url = m.group(1)
        if heading and url:
            break

    parts = [rationale.strip()]
    if heading:
        parts.append(f"Heading: {heading}")
    if url:
        parts.append(f"URL: {url}")
    excerpt = " | ".join(p for p in parts if p)
    return excerpt[:600]


def _phase_quiz_type(phase: int) -> str:
    if phase in {3, 6, 11}:
        return "applied_reasoning"
    if phase in {9, 10}:
        return "fact_recall"
    return "compare_contrast"


def _phase_target_tags(phase: int) -> list[str]:
    if phase == 2:
        return ["history", "compliance"]
    if phase == 3:
        return ["process"]
    if phase == 4:
        return ["region", "culture"]
    if phase == 5:
        return ["culture", "region"]
    if phase == 6:
        return ["compliance", "process"]
    if phase == 9:
        return ["chemistry", "process"]
    if phase == 10:
        return ["chemistry", "process"]
    if phase == 11:
        return ["process", "compliance"]
    return []


def _phase_default_target_section(phase: int) -> str:
    if phase in {2, 4, 5}:
        return "case_examples"
    if phase in {3, 6, 11}:
        return "operational_framework"
    if phase in {9, 10}:
        return "mechanism_explainer"
    return "general"


def _phase_default_insertion_type(phase: int) -> str:
    if phase in {2, 4, 5}:
        return "mini_case"
    if phase in {3, 6, 11}:
        return "checklist"
    if phase in {9, 10}:
        return "mechanism_note"
    return "note"


def _phase_fit_score(phase: int, row: dict[str, Any], score: float) -> float:
    tags = {str(t) for t in row.get("phase_fit_tags", []) if isinstance(t, str)}
    wanted = set(_phase_target_tags(phase))
    overlap = len(tags & wanted)
    bump = 6.0 * overlap
    return round(min(100.0, score + bump), 2)


def _quiz_seed_for_item(phase: int, item: dict[str, Any], idx: int) -> dict[str, Any]:
    source = str(item.get("source") or "")
    bucket = str(item.get("bucket") or "")
    score = float(item.get("score") or 0)
    rationale = str(item.get("rationale") or "")
    label = _source_label(source)
    quiz_type = _phase_quiz_type(phase)
    confidence = max(0.35, min(0.95, round(score / 100.0, 2)))

    if quiz_type == "applied_reasoning":
        stem = f"For phase {phase}, what is the strongest reason to use the source '{label}' in an operations/process lesson update?"
        options = [
            {"id": "A", "text": "It mostly improves brand storytelling but not technical execution."},
            {"id": "B", "text": "It is primarily useful for unrelated cocktail pairing examples."},
            {"id": "C", "text": "It can provide process or compliance evidence that improves operational decision quality."},
            {"id": "D", "text": "It should only be used to replace all existing lesson citations."},
        ]
        correct = "C"
        explanation = "Process and operations phases require actionable evidence linked to production or compliance choices."
    elif quiz_type == "fact_recall":
        stem = f"In phase {phase}, why is '{label}' a suitable chemistry/biochemistry insertion candidate?"
        options = [
            {"id": "A", "text": "Because any product page is chemistry-relevant regardless of evidence."},
            {"id": "B", "text": "Because it is selected using technical/flavor density rather than pure marketing signals."},
            {"id": "C", "text": "Because noisy sources are preferred to increase variety."},
            {"id": "D", "text": "Because chemistry phases no longer use scored filtering."},
        ]
        correct = "B"
        explanation = "Chemistry phases prioritize technical and flavor-density signals and exclude noisy sources by default."
    else:
        stem = f"For phase {phase}, what is the best use of the source '{label}' in content updates?"
        options = [
            {"id": "A", "text": "Treat it as a primary legal standard regardless of source type."},
            {"id": "B", "text": "Use it as a contextual case example aligned with phase theme and score."},
            {"id": "C", "text": "Ignore phase fit and apply it to every phase uniformly."},
            {"id": "D", "text": "Use it only for image extraction, not learning content."},
        ]
        correct = "B"
        explanation = "History/regional/cultural phases use source-backed case examples when they fit phase intent and quality thresholds."

    return {
        "id": f"p{phase}-q{idx+1}",
        "phase": phase,
        "source": source,
        "source_bucket": bucket,
        "source_score": score,
        "quiz_type": quiz_type,
        "stem": stem,
        "options": options,
        "correct_option": correct,
        "explanation": explanation,
        "confidence": confidence,
        "provenance_excerpt": _extract_provenance_excerpt(source, rationale),
    }


def _timestamp_for_filename(value: datetime) -> str:
    return value.strftime("%Y%m%d-%H%M%S")


def build_phase_quiz_seed_queues(
    phase_queue_dir: Path,
    out_dir: Path,
    suggestions_dir: Path | None = None,
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc)
    generated_iso = generated_at.isoformat()
    run_stamp = _timestamp_for_filename(generated_at)
    counts: dict[str, int] = {}

    run_dir: Path | None = None
    latest_dir: Path | None = None
    if suggestions_dir is not None:
        run_dir = suggestions_dir / f"run_{run_stamp}"
        latest_dir = suggestions_dir / "latest"
        run_dir.mkdir(parents=True, exist_ok=True)
        latest_dir.mkdir(parents=True, exist_ok=True)

    for phase in [2, 3, 4, 5, 6, 9, 10, 11]:
        in_path = phase_queue_dir / f"phase_{phase}.json"
        payload = json.loads(in_path.read_text(encoding="utf-8")) if in_path.exists() else {}
        items = payload.get("items", []) if isinstance(payload, dict) else []

        seeds: list[dict[str, Any]] = []
        for idx, item in enumerate(items[:120]):
            if not isinstance(item, dict):
                continue
            seed = _quiz_seed_for_item(phase, item, idx)
            # P1 quality gates before seed export.
            if str(seed.get("source_bucket") or "") == "noisy":
                continue
            if float(seed.get("confidence") or 0) < 0.6:
                continue
            if len(str(seed.get("provenance_excerpt") or "")) < 80:
                continue
            seeds.append(seed)
            if len(seeds) >= 60:
                break
        out = {
            "generated_at": generated_iso,
            "phase": phase,
            "items": seeds,
        }
        out_path = out_dir / f"phase_{phase}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

        if run_dir is not None and latest_dir is not None:
            archived_phase_path = run_dir / f"phase_{phase}.json"
            archived_phase_path.write_text(json.dumps(out, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
            latest_phase_path = latest_dir / f"phase_{phase}.json"
            latest_phase_path.write_text(json.dumps(out, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

        counts[str(phase)] = len(seeds)

    if suggestions_dir is not None and run_dir is not None and latest_dir is not None:
        run_summary = {
            "generated_at": generated_iso,
            "run_id": run_stamp,
            "phase_counts": counts,
            "phase_files": [f"phase_{phase}.json" for phase in [2, 3, 4, 5, 6, 9, 10, 11]],
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(run_summary, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (latest_dir / "manifest.json").write_text(
            json.dumps(run_summary, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (suggestions_dir / "latest_run.txt").write_text(run_stamp + "\n", encoding="utf-8")

    return counts


def _infer_entity_type(main_path: str, bucket: str) -> str:
    low = main_path.lower()
    if bucket == "product_catalog":
        return "product"
    if any(token in low for token in ["/products", "-product", "/shop", "collections", "release", "bottle", "whisky-"]):
        return "product"
    if "/distillery-" in low:
        return "distillery"
    if "/resource-" in low:
        return "resource"
    return "resource"


def _phase_targets_by_source(phase_queue_dir: Path) -> dict[str, list[int]]:
    targets: dict[str, set[int]] = {}
    for phase in [2, 3, 4, 5, 6, 9, 10, 11]:
        in_path = phase_queue_dir / f"phase_{phase}.json"
        payload = json.loads(in_path.read_text(encoding="utf-8")) if in_path.exists() else {}
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            src = str(item.get("source") or "").strip()
            if not src:
                continue
            targets.setdefault(src, set()).add(phase)
    return {k: sorted(v) for k, v in targets.items()}


def build_db_patch_queue(
    triage_json: Path,
    phase_queue_dir: Path,
    out_path: Path,
    *,
    allowed_sources: set[str] | None = None,
) -> dict[str, int]:
    payload = json.loads(triage_json.read_text(encoding="utf-8")) if triage_json.exists() else {}
    records = payload.get("records", []) if isinstance(payload, dict) else []
    phase_targets = _phase_targets_by_source(phase_queue_dir)

    candidates: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        source = str(row.get("main_path") or "").strip()
        if not source:
            continue
        if allowed_sources is not None and source not in allowed_sources:
            continue
        if source not in phase_targets:
            continue

        bucket = str(row.get("bucket") or "")
        score = float(row.get("score") or 0)
        if bucket == "noisy" or score < 45:
            continue

        entity_type = _infer_entity_type(source, bucket)
        parent_slug = Path(source).parent.name
        match_key = f"{parent_slug}:{Path(source).stem}"
        confidence = max(0.4, min(0.96, round(score / 100.0, 2)))

        candidates.append(
            {
                "entity_type": entity_type,
                "match_key": match_key,
                "proposed_fields": {
                    "source_main_path": source,
                    "source_signature": str(row.get("source_signature") or ""),
                    "triage_bucket": bucket,
                    "triage_score": score,
                    "phase_targets": phase_targets.get(source, []),
                    "extraction_counts": {
                        "product_names": int(row.get("product_names") or 0),
                        "chemical_names": int(row.get("chemical_names") or 0),
                        "glossary_terms": int(row.get("glossary_terms") or 0),
                        "distillery_tool_names": int(row.get("distillery_tool_names") or 0),
                        "flavor_profile_words": int(row.get("flavor_profile_words") or 0),
                    },
                    "quality_flags": {
                        "abv_mentioned": bool(row.get("abv_mentioned")),
                        "price_mentioned": bool(row.get("price_mentioned")),
                        "regulatory_overlap": bool(row.get("regulatory_overlap")),
                    },
                },
                "confidence": confidence,
                "source": source,
                "source_signature": str(row.get("source_signature") or ""),
                "review_status": "pending",
            }
        )

    # Prioritize higher confidence patches while keeping output bounded.
    candidates = sorted(candidates, key=lambda x: float(x.get("confidence") or 0), reverse=True)[:300]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": candidates,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    return {
        "total": len(candidates),
        "product": sum(1 for c in candidates if c.get("entity_type") == "product"),
        "distillery": sum(1 for c in candidates if c.get("entity_type") == "distillery"),
        "resource": sum(1 for c in candidates if c.get("entity_type") == "resource"),
    }


def build_phase_queues(
    triage_json: Path,
    out_dir: Path,
    *,
    allowed_sources: set[str] | None = None,
    used_phase_sources: dict[str, set[str]] | None = None,
) -> tuple[dict[str, int], dict[str, list[str]]]:
    payload = json.loads(triage_json.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []

    out_dir.mkdir(parents=True, exist_ok=True)

    phase_map: dict[int, list[dict[str, Any]]] = {2: [], 3: [], 4: [], 5: [], 6: [], 9: [], 10: [], 11: []}
    consumed_by_phase: dict[str, list[str]] = {str(p): [] for p in phase_map.keys()}

    def has_any_token(path_lower: str, tokens: tuple[str, ...]) -> bool:
        return any(token in path_lower for token in tokens)

    def is_nav_or_generic(path_lower: str) -> bool:
        return path_lower.endswith("/home.md") or path_lower.endswith("/site.md") or "/author-" in path_lower or "all-press" in path_lower

    def is_news_or_cocktail_noise(path_lower: str) -> bool:
        return "/cocktails" in path_lower or "cocktails-" in path_lower or "blogs-news-glen-scotia-blog" in path_lower

    def include_for_phase(phase: int, row: dict[str, Any], path_lower: str) -> tuple[bool, str]:
        bucket = str(row.get("bucket") or "")
        score = float(row.get("score") or 0)
        flavor_count = int(row.get("flavor_profile_words") or 0)
        chemical_count = int(row.get("chemical_names") or 0)
        glossary_count = int(row.get("glossary_terms") or 0)
        tool_count = int(row.get("distillery_tool_names") or 0)
        regulatory_overlap = bool(row.get("regulatory_overlap"))

        history_policy_tokens = ("history", "excise", "duty", "tariff", "export", "policy", "regulation", "standard", "label")
        region_identity_tokens = ("campbeltown", "islay", "speyside", "highland", "japan", "irish", "bourbon", "scotch", "single-malt")
        culture_tokens = ("visitor", "tour", "festival", "event", "partnership", "collaboration", "community", "heritage")
        process_tokens = ("process", "distillation", "ferment", "mash", "cask", "barrel", "production", "whisky-school")
        compliance_tokens = ("legal", "label", "excise", "duty", "standard", "permit", "audit", "compliance", "safety")
        equipment_tokens = ("equipment", "cip", "clean", "building", "permit", "utility", "utilities", "planning", "retrofit")
        chemistry_tokens = ("chem", "ester", "phenol", "sulfur", "analysis", "flavor", "flavour", "quality")
        biochem_tokens = ("yeast", "ferment", "nutrient", "attenuation", "lactic", "biochem", "metabolism")

        if phase == 2:
            if bucket == "regulatory" or regulatory_overlap:
                if score >= 25:
                    return True, "regulatory/policy source for history-tax continuity"
            if bucket == "product_catalog" and score >= 72 and has_any_token(path_lower, history_policy_tokens):
                return True, "product-linked source with history/policy cues"
            return False, ""

        if phase == 4:
            if bucket == "product_catalog" and score >= 62 and not is_news_or_cocktail_noise(path_lower):
                if has_any_token(path_lower, region_identity_tokens) or flavor_count >= 4:
                    return True, "regional identity candidate with product signals"
            return False, ""

        if phase == 5:
            if bucket == "product_catalog" and score >= 58 and not is_news_or_cocktail_noise(path_lower):
                if has_any_token(path_lower, culture_tokens) or "blogs-news" in path_lower:
                    return True, "culture/tourism/story candidate"
            return False, ""

        if phase == 3:
            if bucket == "technical_process" and not is_nav_or_generic(path_lower):
                if has_any_token(path_lower, process_tokens) or chemical_count >= 2 or tool_count >= 2 or glossary_count >= 8:
                    return True, "process-focused technical source"
            return False, ""

        if phase == 6:
            if bucket == "regulatory" and score >= 25:
                return True, "regulatory source for operations compliance"
            if bucket == "technical_process" and not is_nav_or_generic(path_lower):
                if has_any_token(path_lower, compliance_tokens) or regulatory_overlap:
                    return True, "technical/compliance operations source"
            return False, ""

        if phase == 11:
            if bucket == "technical_process" and not is_nav_or_generic(path_lower):
                if has_any_token(path_lower, equipment_tokens) or tool_count >= 2:
                    return True, "equipment and infrastructure planning source"
            return False, ""

        if phase == 9:
            if bucket == "noisy":
                return False, ""
            if is_news_or_cocktail_noise(path_lower):
                return False, ""
            if bucket in {"product_catalog", "technical_process"} and score >= 45:
                if chemical_count >= 1 or flavor_count >= 3 or glossary_count >= 6 or has_any_token(path_lower, chemistry_tokens):
                    return True, "chemistry/flavor candidate with technical density"
            return False, ""

        if phase == 10:
            if bucket == "noisy":
                return False, ""
            if is_news_or_cocktail_noise(path_lower):
                return False, ""
            if bucket in {"product_catalog", "technical_process"} and score >= 45:
                if chemical_count >= 2 or glossary_count >= 8 or has_any_token(path_lower, biochem_tokens):
                    return True, "biochemistry candidate with process linkage"
            return False, ""

        return False, ""

    for row in records:
        if not isinstance(row, dict):
            continue
        bucket = str(row.get("bucket") or "")
        main_path = str(row.get("main_path") or "")
        path_lower = main_path.lower()
        if allowed_sources is not None and main_path not in allowed_sources:
            continue
        score = float(row.get("score") or 0)

        entry = {
            "source": main_path,
            "main_path": main_path,
            "metadata_path": str(row.get("metadata_path") or ""),
            "source_signature": str(row.get("source_signature") or ""),
            "bucket": bucket,
            "score": score,
            "extraction_counts": {
                "product_names": int(row.get("product_names") or 0),
                "chemical_names": int(row.get("chemical_names") or 0),
                "glossary_terms": int(row.get("glossary_terms") or 0),
                "distillery_tool_names": int(row.get("distillery_tool_names") or 0),
                "flavor_profile_words": int(row.get("flavor_profile_words") or 0),
            },
            "rationale": "",
        }

        for p in [2, 3, 4, 5, 6, 9, 10, 11]:
            if used_phase_sources and main_path in used_phase_sources.get(str(p), set()):
                continue
            include, rationale = include_for_phase(p, row, path_lower)
            if not include:
                continue
            e = dict(entry)
            e["rationale"] = rationale
            e["phase_fit_score"] = _phase_fit_score(p, row, score)
            e["target_tags"] = _phase_target_tags(p)
            e["target_section"] = _phase_default_target_section(p)
            e["insertion_type"] = _phase_default_insertion_type(p)
            e["evidence_excerpt"] = _extract_provenance_excerpt(main_path, rationale)
            e["action_candidates"] = {
                "content_patch": True,
                "quiz_seed": True,
                "db_patch": True,
            }
            e["quiz_seed"] = {
                "phase": p,
                "quiz_type": _phase_quiz_type(p),
            }
            e["db_patch_hints"] = {
                "entity_type": _infer_entity_type(main_path, bucket),
                "match_key": f"{Path(main_path).parent.name}:{Path(main_path).stem}",
            }
            phase_map[p].append(e)
            consumed_by_phase[str(p)].append(main_path)

    counts: dict[str, int] = {}
    for phase, items in phase_map.items():
        items_sorted = sorted(items, key=lambda x: float(x.get("score") or 0), reverse=True)
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "items": items_sorted[:200],
        }
        out_path = out_dir / f"phase_{phase}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        counts[str(phase)] = len(out["items"])

    for phase in consumed_by_phase:
        consumed_by_phase[phase] = sorted(set(consumed_by_phase[phase]))

    return counts, consumed_by_phase


def compute_observability_metrics(
    phase_queue_dir: Path,
    phase_quiz_seed_counts: dict[str, int],
    db_patch_queue_counts: dict[str, int],
) -> dict[str, Any]:
    phases = [2, 3, 4, 5, 6, 9, 10, 11]
    per_phase_total: dict[str, int] = {}
    per_phase_unique: dict[str, int] = {}
    all_sources: list[str] = []
    duplicate_within_phase = 0
    noisy_chem = 0
    total_chem = 0

    for phase in phases:
        in_path = phase_queue_dir / f"phase_{phase}.json"
        payload = json.loads(in_path.read_text(encoding="utf-8")) if in_path.exists() else {}
        items = payload.get("items", []) if isinstance(payload, dict) else []
        srcs = [str(i.get("source") or "") for i in items if isinstance(i, dict) and str(i.get("source") or "")]
        per_phase_total[str(phase)] = len(srcs)
        per_phase_unique[str(phase)] = len(set(srcs))
        duplicate_within_phase += max(0, len(srcs) - len(set(srcs)))
        all_sources.extend(srcs)
        if phase in {9, 10}:
            total_chem += len(items)
            noisy_chem += sum(1 for i in items if isinstance(i, dict) and str(i.get("bucket") or "") == "noisy")

    total = len(all_sources)
    unique_total = len(set(all_sources))
    duplicate_ratio = (duplicate_within_phase / total) if total else 0.0
    noisy_ratio = (noisy_chem / total_chem) if total_chem else 0.0

    return {
        "queue_items_total": total,
        "queue_items_unique": unique_total,
        "queue_items_unique_by_phase": per_phase_unique,
        "queue_items_total_by_phase": per_phase_total,
        "duplicate_ratio": round(duplicate_ratio, 4),
        "noisy_ratio": round(noisy_ratio, 4),
        "quiz_seed_count": int(sum(phase_quiz_seed_counts.values())),
        "db_patch_candidate_count": int(db_patch_queue_counts.get("total") or 0),
    }


def validate_observability_thresholds(metrics: dict[str, Any], min_unique_per_phase: int = 15) -> list[str]:
    violations: list[str] = []
    duplicate_ratio = float(metrics.get("duplicate_ratio") or 0.0)
    noisy_ratio = float(metrics.get("noisy_ratio") or 0.0)
    unique_by_phase = metrics.get("queue_items_unique_by_phase", {})

    if duplicate_ratio > 0.25:
        violations.append(f"duplicate_ratio {duplicate_ratio:.4f} > 0.25")
    if noisy_ratio > 0.20:
        violations.append(f"noisy_ratio {noisy_ratio:.4f} > 0.20 for phases 9/10")
    if min_unique_per_phase > 0 and isinstance(unique_by_phase, dict):
        for phase, count in unique_by_phase.items():
            try:
                if int(count) < min_unique_per_phase:
                    violations.append(f"queue_items_unique for phase {phase} is {count} < {min_unique_per_phase}")
            except Exception:
                continue

    return violations


def select_incremental_records(
    triage_payload: dict[str, Any],
    previous_signatures: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, int]]:
    records = triage_payload.get("records", []) if isinstance(triage_payload, dict) else []
    incremental: list[dict[str, Any]] = []
    current_signatures: dict[str, str] = {}
    unchanged = 0

    for row in records:
        if not isinstance(row, dict):
            continue
        main_path = str(row.get("main_path") or "").strip()
        signature = str(row.get("source_signature") or "").strip()
        if not main_path:
            continue
        if not signature:
            # Fallback for older triage rows without explicit signatures.
            signature = json.dumps(
                {
                    "main_path": main_path,
                    "bucket": row.get("bucket"),
                    "score": row.get("score"),
                    "product_names": row.get("product_names"),
                    "distillery_tool_names": row.get("distillery_tool_names"),
                    "chemical_names": row.get("chemical_names"),
                    "flavor_profile_words": row.get("flavor_profile_words"),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        current_signatures[main_path] = signature
        if previous_signatures.get(main_path) == signature:
            unchanged += 1
            continue
        incremental.append(row)

    stats = {
        "triage_total_records": len([r for r in records if isinstance(r, dict)]),
        "triage_incremental_records": len(incremental),
        "triage_unchanged_records": unchanged,
    }
    return incremental, current_signatures, stats


_PHASE_LABELS: dict[int, str] = {
    2: "PHASE_2_HISTORY_EXPANDED.md",
    3: "PHASE_3_PROCESS_EXPANDED.md",
    4: "PHASE_4_REGIONAL_IDENTITY_EXPANDED.md",
    5: "PHASE_5_CULTURAL_SOCIAL_EXPANDED.md",
    6: "PHASE_6_OPERATIONS_EXECUTION_EXPANDED.md",
    9: "PHASE_9_CHEMISTRY_OF_WHISKY_EXPANDED.md",
    10: "PHASE_10_BIOCHEMISTRY_OF_WHISKY_EXPANDED.md",
    11: "PHASE_11_DISTILLERY_EQUIPMENT_EXPANDED.md",
}

# Per phase: map (bucket, first matching tag) -> list of plausible target sections in that lesson file.
# Only first matching tag in item["target_tags"] is used.
_PHASE_SECTION_MAP: dict[int, dict[str, list[str]]] = {
    2: {
        "history":    ["## 9. Industrialization: The Coffey Still and the Rise of Blending",
                       "## 19. The Modern Revival: Craft, Premiumization, and Global Curiosity"],
        "compliance": ["## 3. Scotland: Highlands, Illicit Stills, and the Excise Wars",
                       "## 12. Empire, Trade, and the Global Rise of Scotch"],
        "default":    ["## 19. The Modern Revival: Craft, Premiumization, and Global Curiosity"],
    },
    3: {
        "process":    ["## 8. Fermentation: Where Spirit Personality Starts",
                       "## 9. Distillation: Selection, Not Simple Purification",
                       "## 11. Column Stills: Continuous Production and Style Control"],
        "chemistry":  ["## 16. Maturation: Extraction, Subtraction, and Transformation"],
        "default":    ["## 9. Distillation: Selection, Not Simple Purification"],
    },
    4: {
        "regional":   ["## 6. Japan: Precision Blending and Controlled Diversity",
                       "## 8. Australia: The Deepest Regional Grid in Your Database"],
        "compliance": ["## 14. Legal and Category Mapping by Region"],
        "default":    ["## 9. Regional Style vs Brand Identity: A Practical Matrix"],
    },
    5: {
        "culture":    ["## 9. Place-Making and Distillery Tourism",
                       "## 7. Global Modern Culture: From Dram to Asset"],
        "default":    ["## 9. Place-Making and Distillery Tourism"],
    },
    6: {
        "compliance": ["## 7. Label and Regulatory Execution",
                       "## 11. Australia Operational Compliance Map (Expanded Use)"],
        "process":    ["## 4. Process Control: Parameters That Actually Matter",
                       "## 9. Risk Register: Practical Failure Modes"],
        "default":    ["## 7. Label and Regulatory Execution"],
    },
    9: {
        "chemistry":  ["## 7. Ester Chemistry in Fermentation: Fruit Engine and Risk Surface",
                       "## 26. Phenol Chemistry: Smoke, Medicinal Notes, and Complexity"],
        "process":    ["## 14. Distillation Chemistry: Separation by Volatility and Affinity"],
        "default":    ["## 21. Flavor Chemistry Framework: Families of Compounds in Whisky"],
    },
    10: {
        "biochemistry": ["## 2. Fermentation Chemistry: The Foundation of New Make Character"],
        "process":      ["## 12. Fermentation Failure Modes and Their Chemical Signatures"],
        "default":      ["## 2. Fermentation Chemistry: The Foundation of New Make Character"],
    },
    11: {
        "process":    ["## 3. Still and Condensation Systems",
                       "## 5. Cask and Maturation Infrastructure"],
        "compliance": ["## 8. Permitting and Regulatory Infrastructure"],
        "default":    ["## 3. Still and Condensation Systems"],
    },
}

# Quality gates: minimum content word count for a source excerpt to be considered useful.
_MIN_CONTENT_WORDS = 40
# Score thresholds by bucket.
_SCORE_THRESHOLD: dict[str, float] = {
    "technical_process": 50.0,
    "regulatory": 50.0,
    "product_catalog": 90.0,  # much stricter — product pages are rarely useful for lesson prose
}
# Max edits per phase.
_MAX_EDITS_PER_PHASE = 5
# Min edits per phase before we bother writing that section.
_MIN_EDITS_PER_PHASE = 2

# Nav/boilerplate fragment detection: skip source excerpts dominated by these.
_NAV_SIGNALS = {"shop", "cart", "cookie", "javascript", "add to", "subscribe", "sign in",
                "log in", "menu", "footer", "header", "skip to content"}


def _source_excerpt(source_path: str) -> tuple[str, str, int]:
    """
    Read up to 1200 chars of a source markdown file.
    Returns (page_heading, first_paragraph_snippet, substantive_word_count).
    heading and snippet are empty strings if the file cannot be read or fails quality.
    """
    try:
        text = Path(source_path).read_text(encoding="utf-8", errors="replace")[:1800]
    except OSError:
        return "", "", 0

    heading = ""
    paragraphs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and not heading:
            heading = stripped.lstrip("#").strip()
        elif not stripped.startswith("#") and not stripped.startswith("http") and len(stripped) > 30:
            paragraphs.append(stripped)

    snippet = " ".join(paragraphs[:3])[:400]
    # Reject if nav-heavy
    lower = snippet.lower()
    nav_hits = sum(1 for sig in _NAV_SIGNALS if sig in lower)
    if nav_hits >= 3:
        return heading, "", 0

    word_count = len(snippet.split())
    return heading, snippet, word_count


def _section_for_item(phase: int, item: dict) -> str:
    """Pick the most relevant lesson section heading for this queue item."""
    phase_map = _PHASE_SECTION_MAP.get(phase, {})
    tags = [str(t).lower() for t in (item.get("target_tags") or [])]
    for tag in tags:
        if tag in phase_map:
            return phase_map[tag][0]
    return phase_map.get("default", ["[locate best-fit section]"])[0]


def _insertion_action(insertion_type: str, bucket: str, phase: int) -> str:
    """Convert queue insertion_type + bucket into a human-readable edit action verb."""
    if insertion_type == "mini_case":
        return "Add a mini-case sidebar drawing on the product/brand narrative in this source."
    if insertion_type == "checklist":
        if bucket == "regulatory":
            return "Add or extend a compliance checklist drawing on the regulatory language in this source."
        return "Add or extend an operational checklist drawing on the process guidance in this source."
    if insertion_type == "mechanism_note":
        return "Add a mechanism note or callout box drawing on the technical explanation in this source."
    return "Review source and insert a relevant callout, table row, or example to strengthen this section."


def render_lesson_edit_suggestions(
    phase_queue_dir: Path,
    recommendations_dir: Path,
    generated_at: str,
) -> Path | None:
    """
    Generate a dated STEP4-style lesson content edit recommendations file.
    Writes to recommendations_dir/LESSON_CONTENT_EDITS_YYYY-MM-DD.md.
    Returns the output path, or None if no qualifying edits were found.
    """
    date_tag = generated_at[:10]  # YYYY-MM-DD
    out_path = recommendations_dir / f"LESSON_CONTENT_EDITS_{date_tag}.md"

    # If a file for today already exists, use a counter suffix to avoid clobbering.
    counter = 1
    while out_path.exists():
        out_path = recommendations_dir / f"LESSON_CONTENT_EDITS_{date_tag}_{counter:02d}.md"
        counter += 1

    section_blocks: list[str] = []
    total_edits = 0

    for phase in [2, 3, 4, 5, 6, 9, 10, 11]:
        in_path = phase_queue_dir / f"phase_{phase}.json"
        payload = json.loads(in_path.read_text(encoding="utf-8")) if in_path.exists() else {}
        items = [i for i in (payload.get("items", []) if isinstance(payload, dict) else []) if isinstance(i, dict)]

        # Sort: non-product-catalog first by score, then product_catalog by score.
        priority = sorted(
            [i for i in items if i.get("bucket") != "product_catalog"],
            key=lambda x: float(x.get("score", 0)),
            reverse=True,
        )
        supplemental = sorted(
            [i for i in items if i.get("bucket") == "product_catalog"],
            key=lambda x: float(x.get("score", 0)),
            reverse=True,
        )
        candidates = priority + supplemental

        edits: list[str] = []
        edit_num = 1

        for item in candidates:
            if len(edits) >= _MAX_EDITS_PER_PHASE:
                break
            bucket = str(item.get("bucket") or "")
            score = float(item.get("score") or 0)
            threshold = _SCORE_THRESHOLD.get(bucket, 70.0)
            if score < threshold:
                continue

            source = str(item.get("source") or "").strip()
            page_heading, snippet, word_count = _source_excerpt(source)
            if word_count < _MIN_CONTENT_WORDS:
                continue  # not enough real content found in this file

            # Build edit entry.
            edit_id = f"P{phase}-{edit_num:02d}"
            target_section = _section_for_item(phase, item)
            insertion_type = str(item.get("insertion_type") or "")
            action = _insertion_action(insertion_type, bucket, phase)
            tags = ", ".join(str(t) for t in (item.get("target_tags") or []))
            confidence = "A" if bucket != "product_catalog" and score >= 65 else "B"

            excerpt_display = snippet[:280].rstrip() + ("…" if len(snippet) > 280 else "")

            block = "\n".join([
                f"### {edit_id}",
                f"Target section:",
                f"- `{target_section}`",
                "",
                f"Edit action:",
                f"- {action}",
                "",
                f"Source file:",
                f"- `{source}`",
                f"- Page heading: **{page_heading or '(see file)'}**",
                "",
                f"Excerpt hint:",
                f"> {excerpt_display}",
                "",
                f"Tags: {tags}  |  Bucket: {bucket}  |  Score: {score}",
                "",
                f"Confidence: {confidence}",
            ])
            edits.append(block)
            edit_num += 1

        if len(edits) < _MIN_EDITS_PER_PHASE:
            continue  # not enough signal for this phase; skip rather than pad

        lesson_file = _PHASE_LABELS.get(phase, f"Phase {phase}")
        section_blocks.append(f"\n## {lesson_file}\n")
        section_blocks.extend(e + "\n\n---" for e in edits)
        total_edits += len(edits)

    if total_edits == 0:
        return None  # nothing useful to write

    corpus_info = "\n".join([
        "## Corpus Summary",
        "",
        f"Queue source: `{phase_queue_dir}`",
        f"Quality gate: non-product-catalog score ≥ {_SCORE_THRESHOLD['technical_process']}, "
        f"product-catalog score ≥ {_SCORE_THRESHOLD['product_catalog']}, "
        f"min excerpt words ≥ {_MIN_CONTENT_WORDS}",
        f"Total edits emitted: {total_edits} (max {_MAX_EDITS_PER_PHASE} per phase, "
        f"phase skipped if fewer than {_MIN_EDITS_PER_PHASE} pass gate)",
        "",
        "---",
    ])

    header = "\n".join([
        "# Lesson Content Edit Recommendations",
        "",
        f"Date: {date_tag}",
        f"Generated: {generated_at}",
        "",
        "Auto-generated by `scripts/generate_content.py` from the current phase insertion queues.",
        "Review each suggestion and apply manually to the target lesson file.",
        "Only sources with sufficient substantive content pass the quality gate — if a phase",
        "has fewer than two qualifying sources it is omitted rather than padded with weak material.",
        "",
        "---",
        "",
        corpus_info,
    ])

    recommendations_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n" + "\n".join(section_blocks) + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate post-scrape content artifacts.")
    parser.add_argument("--triage-json", default="data/resource_triage.json")
    parser.add_argument("--triage-csv", default="data/resource_triage.csv")
    parser.add_argument("--phase-queue-dir", default="data/phase_insertion_queue")
    parser.add_argument("--phase-quiz-seed-dir", default="data/phase_quiz_seed_queue")
    parser.add_argument(
        "--quiz-suggestions-dir",
        default="data/quiz_suggestions",
        help="Directory where timestamped per-run quiz suggestion files are archived.",
    )
    parser.add_argument("--db-patch-queue", default="data/db_patch_queue.json")
    parser.add_argument("--products-dir", default="data/products")
    parser.add_argument("--product-limit", type=int, default=0)
    parser.add_argument(
        "--progress-state",
        default="data/content_progress_state.json",
        help="Progress state to track consumed sources and signatures for incremental digestion.",
    )
    parser.add_argument(
        "--full-redigest",
        action="store_true",
        help="Ignore progress state and process all triage records again.",
    )
    parser.add_argument(
        "--min-unique-per-phase",
        type=int,
        default=15,
        help="Minimum unique queue items required per phase (0 disables the check).",
    )
    args = parser.parse_args()

    py = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
    py_cmd = str(py) if py.exists() else "python3"

    run_step([py_cmd, "scripts/triage_resources.py", "--json-out", args.triage_json, "--csv-out", args.triage_csv])

    triage_payload = json.loads(Path(args.triage_json).read_text(encoding="utf-8"))
    progress_path = Path(args.progress_state)
    progress = {} if args.full_redigest else load_progress_state(progress_path)

    prev_signatures_raw = progress.get("triage_signatures", {}) if isinstance(progress, dict) else {}
    prev_signatures = {
        str(k): str(v)
        for k, v in prev_signatures_raw.items()
        if isinstance(k, str) and isinstance(v, str)
    }

    incremental_records, current_signatures, inc_stats = select_incremental_records(triage_payload, prev_signatures)
    incremental_sources = sorted(
        {
            str(row.get("main_path") or "").strip()
            for row in incremental_records
            if isinstance(row, dict) and str(row.get("main_path") or "").strip()
        }
    )

    with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp_sources:
        tmp_sources.write(json.dumps(incremental_sources, ensure_ascii=True, indent=2) + "\n")
        sources_file = tmp_sources.name

    product_cmd = [
        py_cmd,
        "scripts/build_products_from_triage.py",
        "--triage-json",
        args.triage_json,
        "--products-dir",
        args.products_dir,
        "--limit",
        str(args.product_limit),
        "--only-sources-json",
        sources_file,
        "--progress-state",
        args.progress_state,
    ]
    if args.full_redigest:
        product_cmd.append("--ignore-used-sources")

    product_stdout = run_step(product_cmd)

    try:
        product_result = json.loads(product_stdout) if product_stdout else {}
    except Exception:
        product_result = {"raw": product_stdout}
    Path(sources_file).unlink(missing_ok=True)

    used_phase_sources_raw = progress.get("used_phase_sources", {}) if isinstance(progress, dict) else {}
    used_phase_sources: dict[str, set[str]] = {}
    for phase in ["2", "3", "4", "5", "6", "9", "10", "11"]:
        vals = used_phase_sources_raw.get(phase, []) if isinstance(used_phase_sources_raw, dict) else []
        used_phase_sources[phase] = {str(x) for x in vals if isinstance(x, str) and x.strip()}

    queue_counts, consumed_phase_sources = build_phase_queues(
        Path(args.triage_json),
        Path(args.phase_queue_dir),
        allowed_sources=set(incremental_sources),
        used_phase_sources=used_phase_sources,
    )

    quiz_seed_counts = build_phase_quiz_seed_queues(
        Path(args.phase_queue_dir),
        Path(args.phase_quiz_seed_dir),
        Path(args.quiz_suggestions_dir),
    )

    db_patch_counts = build_db_patch_queue(
        Path(args.triage_json),
        Path(args.phase_queue_dir),
        Path(args.db_patch_queue),
        allowed_sources=set(incremental_sources),
    )

    # Persist updated progress state.
    state_to_write = load_progress_state(progress_path)
    state_to_write["triage_signatures"] = current_signatures
    merged_phase_sources: dict[str, list[str]] = {}
    for phase in ["2", "3", "4", "5", "6", "9", "10", "11"]:
        merged = set(used_phase_sources.get(phase, set()))
        merged.update(consumed_phase_sources.get(phase, []))
        merged_phase_sources[phase] = sorted(merged)
    state_to_write["used_phase_sources"] = merged_phase_sources
    state_to_write["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_progress_state(progress_path, state_to_write)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "triage_json": args.triage_json,
        "triage_csv": args.triage_csv,
        "progress_state": str(progress_path),
        "incremental": {
            **inc_stats,
            "incremental_sources": len(incremental_sources),
            "full_redigest": bool(args.full_redigest),
        },
        "products": product_result,
        "phase_queue_counts": queue_counts,
        "phase_quiz_seed_counts": quiz_seed_counts,
        "quiz_suggestions_dir": args.quiz_suggestions_dir,
        "db_patch_queue_counts": db_patch_counts,
        "phase_sources_consumed": {
            k: len(v)
            for k, v in consumed_phase_sources.items()
        },
    }
    observability_metrics = compute_observability_metrics(
        Path(args.phase_queue_dir),
        quiz_seed_counts,
        db_patch_counts,
    )
    threshold_violations = validate_observability_thresholds(observability_metrics, min_unique_per_phase=args.min_unique_per_phase)
    report["observability_metrics"] = observability_metrics
    report["threshold_violations"] = threshold_violations

    if threshold_violations:
        out_report = Path("data/content_generation_report.json")
        out_report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError("Quality thresholds failed: " + "; ".join(threshold_violations))

    out_report = Path("data/content_generation_report.json")
    out_report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    render_lesson_edit_suggestions(
        phase_queue_dir=Path(args.phase_queue_dir),
        recommendations_dir=Path("data/content_recommendations"),
        generated_at=report["generated_at"],
    )

    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
