# Gemma Review and Image Label Specification

## Scope

This specification defines implementation details for:

1. T000 model routing baseline.
2. T105 end-of-run image labeling.
3. T106 run review phase.

Target model policy:

- Summarization model: google/gemma-3-27b
- Review model: google/gemma-3-27b
- Image labeling model: google/gemma-3-27b

All requests must use local LM Studio OpenAI-compatible endpoints.

## Runtime Configuration

## File

- config/model_policy.json

## JSON contract

{
  "version": 1,
  "lmstudio": {
    "base_url": "http://127.0.0.1:1234/v1",
    "request_timeout_seconds": 3600,
    "healthcheck_models_endpoint": "/models"
  },
  "models": {
    "summarization": "google/gemma-3-27b",
    "review": "google/gemma-3-27b",
    "image_labeling": "google/gemma-3-27b",
    "relevance_screening": "ibm/granite-4-h-tiny"
  },
  "policy": {
    "fail_if_required_model_missing": true,
    "allow_cli_override": true,
    "record_model_in_manifest": true
  }
}

## CLI Surface

Add or standardize these flags on the top-level orchestration path.

1. --model-policy
- Default: config/model_policy.json
- Purpose: load model routing and policy.

2. --lmstudio-url
- Default: from model policy, fallback http://127.0.0.1:1234/v1

3. --lmstudio-review-model
- Default: from model policy review key.
- Allowed override only if allow_cli_override true.

4. --lmstudio-image-label-model
- Default: from model policy image_labeling key.

5. --enable-run-review
- Default: true
- Controls T106 execution.

6. --enable-image-labeling
- Default: true
- Controls T105 execution.

7. --image-label-batch-size
- Default: 64
- Number of images processed per labeling batch.

8. --image-label-max-workers
- Default: 4
- Parallel workers for image labeling calls.

9. --review-max-pages
- Default: 200
- Cap on pages sent to run review aggregation.

## Model Selection Rules

Priority order for each phase:

1. Explicit CLI override.
2. model_policy.json phase mapping.
3. Hard default google/gemma-3-27b for summarization, review, and image labeling.

If fail_if_required_model_missing is true and model is unavailable in LM Studio /models response, stop run with non-zero exit.

## Run Manifest Schema Additions

## File path pattern

- data/run_manifests/<run_id>/manifest.json

## Required fields

{
  "run_id": "20260417-120501-abc123",
  "started_at": "2026-04-17T12:05:01Z",
  "ended_at": "2026-04-17T13:41:22Z",
  "status": "completed",
  "model_policy": {
    "path": "config/model_policy.json",
    "version": 1,
    "resolved": {
      "summarization": "google/gemma-3-27b",
      "review": "google/gemma-3-27b",
      "image_labeling": "google/gemma-3-27b",
      "relevance_screening": "ibm/granite-4-h-tiny"
    }
  },
  "phases": {
    "crawl": {
      "status": "completed",
      "pages_processed": 1234
    },
    "review": {
      "enabled": true,
      "status": "completed",
      "model": "google/gemma-3-27b",
      "prompt_version": "review-v1",
      "output_file": "data/run_manifests/<run_id>/review.json"
    },
    "image_labeling": {
      "enabled": true,
      "status": "completed",
      "model": "google/gemma-3-27b",
      "prompt_version": "image-label-v1",
      "images_total": 520,
      "images_labeled": 520,
      "label_counts": {
        "bottle": 110,
        "logo": 74,
        "award": 18,
        "lifestyle": 126,
        "equipment": 92,
        "junk": 100
      },
      "output_file": "data/run_manifests/<run_id>/image_labels.json"
    }
  }
}

## Image Labeling Data Contract

## Output file

- data/run_manifests/<run_id>/image_labels.json

## Record schema

{
  "run_id": "20260417-120501-abc123",
  "generated_at": "2026-04-17T13:40:55Z",
  "model": "google/gemma-3-27b",
  "prompt_version": "image-label-v1",
  "allowed_labels": ["bottle", "logo", "award", "lifestyle", "equipment", "junk"],
  "records": [
    {
      "image_id": "sha256:...",
      "source_url": "https://example.com/image.jpg",
      "local_path": "data/images/.../abc123.jpg",
      "page_url": "https://example.com/products/x",
      "label": "bottle",
      "confidence": 0.92,
      "reason": "Single centered spirits bottle product shot with neutral backdrop.",
      "reviewed_at": "2026-04-17T13:40:03Z"
    }
  ]
}

## DB integration (recommended)

Add columns to images table in crawl state and/or distillery DB mirror:

1. ai_label TEXT
2. ai_label_confidence REAL
3. ai_label_reason TEXT
4. ai_labeled_at TEXT
5. ai_label_model TEXT
6. ai_label_prompt_version TEXT

## Validation rules

1. label must be one of bottle, logo, award, lifestyle, equipment, junk.
2. confidence must be between 0 and 1.
3. reason length between 8 and 280 chars.
4. no unlabeled new images if image labeling phase enabled.

## Review Phase Data Contract

## Output file

- data/run_manifests/<run_id>/review.json

## JSON schema

{
  "run_id": "20260417-120501-abc123",
  "generated_at": "2026-04-17T13:41:10Z",
  "model": "google/gemma-3-27b",
  "prompt_version": "review-v1",
  "summary": {
    "overall_quality": "high",
    "coverage_assessment": "good",
    "notable_gaps": ["limited regulatory depth for AU excise updates"]
  },
  "priorities_next_run": [
    {
      "type": "site",
      "name": "Example Site",
      "reason": "High technical yield in recent crawl",
      "priority_score": 0.93
    }
  ],
  "action_items": [
    {
      "id": "R1",
      "severity": "high",
      "category": "reliability",
      "title": "Retry blocked pages with CDP-first policy",
      "details": "23 pages classified blocked_suspected",
      "owner": "scrape",
      "suggested_fix": "increase cooldown and route domain to CDP-first"
    }
  ]
}

## Prompt Templates

## Prompt file locations

1. prompts/review/review-v1.md
2. prompts/image_label/image-label-v1.md

## review-v1.md template

System prompt:

You are reviewing a whisky knowledge crawl run. Use only the supplied run data. Return strict JSON with keys: summary, priorities_next_run, action_items. Keep recommendations specific and actionable.

User payload keys:

- run_summary
- per_site_stats
- failure_stats
- relevance_distribution
- triage_snapshot
- extraction_completeness
- image_label_distribution

Output constraints:

1. summary.overall_quality one of high, medium, low.
2. priority_score range 0..1.
3. action_items severity one of high, medium, low.
4. No markdown, JSON only.

## image-label-v1.md template

System prompt:

Classify each image into exactly one label from bottle, logo, award, lifestyle, equipment, junk. Return strict JSON array. Do not invent labels. Keep reason concise and visual.

User payload keys per image:

- image_id
- source_url
- page_url
- local_path
- alt_text
- context_excerpt

Output item constraints:

1. label must be from allowed set.
2. confidence numeric 0..1.
3. reason max 280 chars.

## Processing Order

At end of each completed run:

1. Finalize crawl metrics and persist base manifest.
2. Execute review phase with gemma and write review.json.
3. Execute image labeling phase with gemma and write image_labels.json.
4. Update manifest phase statuses and counts.
5. Run post-label cleanup policy in dry-run or active mode as configured.

## Failure Handling

1. If review phase fails:
- Mark phases.review.status as failed.
- Continue run completion with non-fatal warning unless strict mode enabled.

2. If image labeling fails and enable-image-labeling true:
- Mark phases.image_labeling.status as failed.
- If strict labeling mode enabled, fail run.
- If strict labeling mode disabled, keep run complete but block cleanup that depends on labels.

Suggested strict flags:

1. --strict-review-phase default false
2. --strict-image-labeling default true

## Acceptance Test Cases

1. Model routing compliance
- Given model policy file and no overrides, summarization, review, and image labeling resolve to google/gemma-3-27b.

2. Manifest completeness
- Completed run manifest contains model policy block and both phase outputs.

3. Image label vocabulary enforcement
- Any label outside allowed set causes validation failure.

4. End-of-run coverage
- images_labeled equals images_total for new run images when strict labeling true.

5. Review output validity
- review.json parses and includes summary, priorities_next_run, action_items.

6. Cleanup safeguard integration
- If image_labels missing, cleanup that uses junk labels does not delete files and reports blocked state.
