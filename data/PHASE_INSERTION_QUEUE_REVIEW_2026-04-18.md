# Phase Insertion Queue Review -> Concrete Update Suggestions

Date: 2026-04-18
Inputs reviewed:
- data/phase_insertion_queue/phase_2.json
- data/phase_insertion_queue/phase_3.json
- data/phase_insertion_queue/phase_4.json
- data/phase_insertion_queue/phase_5.json
- data/phase_insertion_queue/phase_6.json
- data/phase_insertion_queue/phase_9.json
- data/phase_insertion_queue/phase_10.json
- data/phase_insertion_queue/phase_11.json
- scripts/generate_content.py
- scripts/triage_resources.py

## Implementation Status (2026-04-18)

Implemented:
1. P0 queue-gating changes in scripts/generate_content.py (phase-fit filters, regulatory routing, noisy exclusion for phases 9/10).
2. Regenerated triage outputs and phase queue files directly via triage_resources + build_phase_queues.
3. Added triage-level phase-fit tags and nav/news/cocktail penalties in scripts/triage_resources.py.
4. Expanded phase queue item schema with execution fields (target_section, insertion_type, evidence_excerpt, action_candidates, quiz_seed, db_patch_hints, extraction counts, signatures).
5. Added quiz quality gates (min provenance length, confidence threshold, noisy exclusion) in quiz seed generation.
6. Added observability metrics and threshold enforcement in scripts/generate_content.py (duplicate_ratio, noisy_ratio, queue unique counts, quiz/db counts).

Validation outcomes:
1. No exact duplicate phase groups remain across 2/4/5, 3/6/11, 9/10.
2. No noisy leakage in phase 9 and phase 10 queues (noisy=0 for both).
3. Regulatory sources now flow into phase 2 and phase 6 queues.
4. Full run passes threshold gates with no violations.

Execution note:
1. The filename-too-long product generation blocker has been fixed in scripts/build_products_from_triage.py by bounded slug generation.
2. Full pipeline run now succeeds via scripts/generate_content.py --full-redigest.
3. Latest successful run summary:
  - generated_at: 2026-04-18T02:35:44.082426+00:00
  - products.written: 0
  - phase_queue_counts: {"2": 200, "3": 92, "4": 200, "5": 66, "6": 139, "9": 200, "10": 128, "11": 43}
  - phase_quiz_seed_counts: {"2": 60, "3": 8, "4": 60, "5": 60, "6": 2, "9": 60, "10": 60, "11": 4}
  - db_patch_queue_counts: {"total": 300, "product": 298, "distillery": 2, "resource": 0}
  - observability_metrics: {"duplicate_ratio": 0.0, "noisy_ratio": 0.0}
  - threshold_violations: []
4. Post-run validation still passes:
  - no high-overlap duplicate phase groups (Jaccard >= 0.90 none)
  - noisy leakage for phases 9/10 remains zero

## 1) Critical Findings (What is blocking quality right now)

1. Queue outputs are duplicated by phase groups, not phase-specific:
- Exact duplicate group A: phases 2, 4, 5 (99 items each; all product_catalog)
- Exact duplicate group B: phases 3, 6, 11 (18 items each; all technical_process)
- Exact duplicate group C: phases 9, 10 (70 items each; mixed product_catalog/technical_process/noisy)

2. High-noise records are entering chemistry/biochemistry phases:
- phases 9 and 10 include noisy cocktail/news pages because flavor_count >= 2 is the only gate.

3. Regulatory-rich records are not routed into any phase queue:
- triage has a regulatory bucket, but build_phase_queues does not map it to any phase.

4. Queue records are too thin for direct implementation:
- Current fields: source, bucket, score, rationale
- Missing fields needed for execution: target_section, insertion_type, evidence_excerpt, quiz_seed, db_patch_hints

## 2) Concrete Content Update Suggestions

## Priority P0: phase-specific filtering before any new lesson edits

1. For phases 2/4/5, do not use one shared queue.
- Split product_catalog sources into sub-intents:
  - phase 2: history/policy continuity examples only
  - phase 4: region identity and terroir/process-linked positioning
  - phase 5: culture, tourism, brand narrative, social signals

2. For phases 3/6/11, down-rank generic site pages.
- Penalize source paths ending in site.md, home.md, author-*.md, all-press.md.
- Keep technical pages containing process tokens (distillation, mash, ferment, cask, equipment, CIP, safety).

3. For phases 9/10, exclude noisy bucket by default.
- Keep only product_catalog + technical_process for chemistry phases.
- If noisy is allowed, require score >= 35 and explicit chemistry term overlap.

## Priority P1: immediate insertion targets from current queues

1. Use these as case-example candidates (content sidebars, not core claims):
- data/crawl_markdown/distillery-springbank/whisky-springbank-range.md
- data/crawl_markdown/distillery-wild-turkey/en-us-latest-news-bourbon-tasting-tips.md
- data/crawl_markdown/distillery-glen-scotia/home.md

2. Exclude these from lesson prose candidates immediately:
- data/crawl_markdown/distillery-wild-turkey/cocktails.md
- data/crawl_markdown/distillery-wild-turkey/cocktails-manhattan.md
- data/crawl_markdown/distillery-glen-scotia/blogs-news-glen-scotia-blog.md

3. For technical phases, keep only records with at least one of:
- chemical_names >= 2
- distillery_tool_names >= 2
- glossary_terms >= 8

## 3) Concrete Quiz Update Suggestions

## Priority P0: generate quiz-ready seeds from queue records

1. Add a quiz seed generation pass that emits one file per phase:
- data/phase_quiz_seed_queue/phase_<N>.json

2. Quiz seed schema (minimum):
- phase
- source
- source_bucket
- source_score
- quiz_type (fact_recall | applied_reasoning | compare_contrast)
- stem
- options (A-D)
- correct_option
- explanation
- confidence
- provenance_excerpt

3. Question templates by phase family:
- phases 2/4/5: context and interpretation questions (history/region/culture claims)
- phases 3/6/11: process decision and compliance operation questions
- phases 9/10: chemistry mechanism and flavor-cause linkage questions

## Priority P1: quality controls before importing into lesson markdown quizzes

1. Reject quiz seeds if:
- provenance_excerpt length < 80 chars
- source bucket is noisy (unless manual override)
- confidence < 0.6

2. Enforce distractor quality:
- each distractor must be plausible and same semantic class as correct answer
- no "all of the above/none of the above"

## 4) Concrete Database Update Suggestions

## Priority P0: enrich queue item structure for downstream DB actions

1. Extend phase queue item object with:
- main_path
- metadata_path
- source_signature
- extraction_counts: {product_names, chemical_names, glossary_terms, distillery_tool_names, flavor_profile_words}
- phase_fit_score
- target_tags (history, region, culture, process, chemistry, compliance)
- action_candidates: {content_patch, quiz_seed, db_patch}

2. Emit a dedicated db patch queue file:
- data/db_patch_queue.json

3. db_patch candidate object:
- entity_type (product | distillery | resource)
- match_key (slug/url/title)
- proposed_fields (key/value map)
- confidence
- source
- source_signature
- review_status (pending/approved/rejected)

## Priority P1: add phase-level observability metrics

1. Write per-run metrics to report JSON:
- queue_items_total
- queue_items_unique
- duplicate_ratio
- noisy_ratio
- quiz_seed_count
- db_patch_candidate_count

2. Add acceptance thresholds (fail run if exceeded):
- duplicate_ratio > 0.25
- noisy_ratio > 0.20 for phases 9/10
- queue_items_unique < 15 for any targeted phase

## 5) Suggested Code-Level Changes (where to implement)

1. scripts/generate_content.py
- In build_phase_queues:
  - stop assigning identical bucket groups to multiple phases without phase-fit gating
  - add per-phase filtering function using path tokens + extraction counts + bucket constraints
  - for phases 9/10, default-exclude noisy bucket
  - map regulatory bucket to phases 2 and 6 with lower base score

2. scripts/triage_resources.py
- Add penalties for nav/news/cocktail path patterns under technical/chemistry routing.
- Add explicit phase-fit signals to output records (phase_fit tags).

3. Add new generation function(s):
- build_phase_quiz_seed_queues(...)
- build_db_patch_queue(...)

## 6) Immediate Execution Plan (smallest useful next step)

1. Implement queue dedupe + phase-fit gates in scripts/generate_content.py.
2. Regenerate phase queues and confirm:
- no exact phase-group duplicates
- noisy excluded from phases 9/10 by default
3. Generate first quiz seed queue for phases 2 and 3 only (pilot).
4. Generate first db_patch_queue.json from same pilot run.
5. Review and merge into lesson edit workflow.

## 7) Definition of Done for this queue system

1. Each phase queue is materially different and phase-relevant.
2. Every queued item is executable for at least one target:
- content insertion,
- quiz seed,
- or db patch.
3. Provenance and confidence are present for all actionable items.
4. Noise and duplication thresholds stay within limits for two consecutive runs.
