# Whisky Scraping Execution Backlog

## Purpose

Translate the agreed plans into implementable tickets with:

1. Clear scope.
2. Dependency ordering.
3. Acceptance tests.
4. Rollout and regression guardrails.

## Delivery Principles

1. Preserve working behavior first.
2. Add new entry points and policies without breaking existing scripts.
3. Keep outputs auditable and source-traceable.
4. Ship in small slices with measurable outcomes.

## Milestone Plan

1. M1 Foundation orchestration and manifests.
2. M2 Strategy hardening and failure taxonomy.
3. M3 Triage and prioritization loop.
4. M4 Product hardening and linkage.
5. M5 Lesson suggestion queues and generation mode.
6. M6 Maintainability refactor and test expansion.

## Ticket Backlog

## M1 Foundation Orchestration and Manifests

### T000 Add model routing baseline for LM Studio

- Priority: P0
- Type: Configuration
- Depends on: none
- Output:
  - config/model_policy.json
- Scope:
  - Define local LM Studio model policy for pipeline phases.
  - Pin summarization phase to google/gemma-3-27b.
  - Pin review phase to google/gemma-3-27b.
- Acceptance tests:
  - Runtime resolves summarization model from configuration as google/gemma-3-27b.
  - Runtime resolves review model from configuration as google/gemma-3-27b.
  - Manifest records model IDs used per phase.

### T001 Create unified scrape entrypoint

- Priority: P0
- Type: Feature
- Depends on: T000
- Output:
  - scripts/scrape.sh
- Scope:
  - Add single command wrapper for distillery and resource scraping.
  - Support chunk-size and continuation controls.
  - Delegate crawl execution to existing scripts/crawl_whisky_sites.py.
- Acceptance tests:
  - Running scripts/scrape.sh with default args executes one batch and exits cleanly.
  - Running scripts/scrape.sh with continue count > 1 executes multiple iterations.
  - Running scripts/scrape.sh with continue count = 0 loops until interrupted.

### T002 Add iteration manifest output

- Priority: P0
- Type: Feature
- Depends on: T001
- Output:
  - data/run_manifests/<timestamp>/manifest.json
- Scope:
  - Persist iteration metadata, parameters, counts, and status.
  - Include model names, strategy mode, and batch composition.
- Acceptance tests:
  - Every run creates a manifest.
  - Manifest includes per-iteration status and totals.
  - Interrupted runs retain last completed iteration marker.

### T003 Defer content generation until terminal iteration

- Priority: P0
- Type: Behavior
- Depends on: T001
- Scope:
  - Ensure iterative scrape mode performs review each iteration.
  - Ensure content generation only executes after final iteration.
- Acceptance tests:
  - Intermediate iterations do not emit content-update files.
  - Final iteration emits content-update outputs as configured.

### T004 Browser mode policy for reliability visibility

- Priority: P1
- Type: Behavior
- Depends on: T001
- Scope:
  - Add browser-mode argument with headed default and headless override.
  - Preserve compatibility with existing headless behavior when explicitly requested.
- Acceptance tests:
  - Default mode launches visible browser path when CDP/browser fetch is used.
  - headless override still works and passes existing crawl paths.

## M2 Strategy Hardening and Failure Taxonomy

### T101 Structured failure classification

- Priority: P0
- Type: Reliability
- Depends on: T002
- Scope:
  - Define standard failure classes and map current error strings to classes.
  - Persist failure_class and retry_eligible fields in crawl state artifacts.
- Acceptance tests:
  - Failed pages receive non-empty class labels.
  - Timeouts, blocks, and parse failures map to distinct classes.

### T102 Retry policy registry

- Priority: P0
- Type: Reliability
- Depends on: T101
- Output:
  - config/retry_policy.json
- Scope:
  - Configure retry counts and cooldown by failure class.
  - Keep compatibility with current retry rounds in orchestrator scripts.
- Acceptance tests:
  - Policy changes alter retry behavior without code changes.
  - Non-retryable classes are skipped in retry rounds.

### T103 CDP-first memory for problematic sites

- Priority: P1
- Type: Feature
- Depends on: T101
- Scope:
  - Persist per-site preferred strategy based on historical failure profile.
  - Route known-problem sites to CDP first.
- Acceptance tests:
  - Repeated direct failures on a site trigger CDP-first in subsequent run.
  - Successful direct recovery can clear or downgrade CDP-first preference.

### T104 Extraction completeness flags

- Priority: P1
- Type: Observability
- Depends on: T002
- Scope:
  - Store completeness flags for html, pdf, audio, transcript, images, metadata, summary.
- Acceptance tests:
  - Each processed page has completeness status fields.
  - Recovery mode can filter for incomplete pages.

### T105 End-of-run image labeling with Gemma

- Priority: P0
- Type: Feature
- Depends on: T002
- Scope:
  - Add mandatory post-run image labeling pass using local LM Studio and google/gemma-3-27b.
  - Assign exactly one label per image from: bottle, logo, award, lifestyle, equipment, junk.
  - Persist label, confidence, and reviewed_at metadata.
- Acceptance tests:
  - Every newly collected image is labeled at run end.
  - Labels are restricted to the six-category vocabulary.
  - Missing labels fail run validation checks.

### T106 Implement review phase with Gemma

- Priority: P0
- Type: Feature
- Depends on: T003
- Scope:
  - Implement structured post-run review phase in LM Studio.
  - Use google/gemma-3-27b for review analysis and recommendations.
  - Persist review summary and action recommendations in run manifest outputs.
- Acceptance tests:
  - Each run includes review output when run completes.
  - Review output contains quality findings and prioritization recommendations.
  - Review phase model ID is recorded as google/gemma-3-27b.

## M3 Triage and Prioritization Loop

### T201 Implement resource triage script

- Priority: P0
- Type: Feature
- Depends on: T104
- Output:
  - scripts/triage_resources.py
  - data/resource_triage.json
  - data/resource_triage.csv
- Scope:
  - Parse metadata taxonomy counts from crawl markdown metadata files.
  - Apply bucket rules for product_catalog, regulatory, technical_process, noisy.
- Acceptance tests:
  - Script runs against existing crawl data without errors.
  - Output rows include bucket, score, and source path.

### T202 Integrate triage output into next-batch selection

- Priority: P1
- Type: Feature
- Depends on: T201
- Scope:
  - Use triage score and relevance signals to prioritize upcoming scrape chunks.
- Acceptance tests:
  - Selection order changes when triage scores are updated.
  - High-value sources appear earlier in queue than noisy sources.

### T203 Prefilter evolution pipeline

- Priority: P1
- Type: Feature
- Depends on: T201, T105
- Scope:
  - Add operational process for allow_path_prefixes and block_path_prefixes updates.
  - Keep compatibility with current JSON schema keys and cleanup logic.
  - Use image labels to reinforce junk filtering decisions while preserving lesson and quiz assets.
- Acceptance tests:
  - Updated prefilter rules are honored by crawler and cleanup passes.
  - Rule updates produce measurable reduction in noisy page capture.

## M4 Product Hardening and Linkage

### T301 Implement build_products_from_triage

- Priority: P0
- Type: Feature
- Depends on: T201
- Output:
  - scripts/build_products_from_triage.py
- Scope:
  - Read product_catalog pages from triage output.
  - Extract product tuples from main markdown files.
  - Apply confidence gate and dedupe checks.
- Acceptance tests:
  - New product records are generated for valid candidates.
  - Duplicate records by slug/name-distillery/image hash are blocked.

### T302 Distillery-to-product relationship index

- Priority: P0
- Type: Data model
- Depends on: T301
- Scope:
  - Persist associations so each distillery can list known products.
  - Backfill existing product files into association index.
- Acceptance tests:
  - Distillery association query returns expected products.
  - Relationship remains stable across reruns.

### T303 Render associated products on distillery pages

- Priority: P1
- Type: Feature
- Depends on: T302
- Scope:
  - Update scripts/serve_site.py distillery view rendering to include associated products.
  - Keep current image and research section behavior unchanged.
- Acceptance tests:
  - Distillery detail pages show associated products list.
  - Existing distillery page sections still render correctly.

### T304 Enforce products listing completeness gate

- Priority: P1
- Type: Behavior
- Depends on: T301
- Scope:
  - Restrict dedicated products page to products with name + distillery + image + purchase link.
  - Keep distillery pages showing all associated products.
- Acceptance tests:
  - Incomplete products are excluded from products index.
  - Incomplete products remain visible in distillery-specific associated list.

## M5 Lesson Suggestion Queues and Generation Mode

### T401 Create generate_content entrypoint

- Priority: P0
- Type: Feature
- Output:
  - scripts/generate_content.sh
- Depends on: T201
- Scope:
  - Run content generation independently from scraping.
  - Default to latest 100 updated scraped files.
  - Support filters by resource, distillery, date, and bucket/category.
- Acceptance tests:
  - Script runs with defaults and generates output files.
  - Filter combinations reduce source set deterministically.

### T402 Build dense-topic index stage

- Priority: P0
- Type: Feature
- Depends on: T401
- Output:
  - data/topic_density_index_latest.json
- Scope:
  - Identify high-density technical and pedagogical source clusters.
  - Use full source content, not summary-only proxies.
- Acceptance tests:
  - Index includes ranked source clusters with evidence fields.
  - Results are stable for fixed inputs.

### T403 Generate phase insertion queues

- Priority: P0
- Type: Feature
- Depends on: T402
- Output:
  - data/phase_insertion_queue/phase_<N>.json
- Scope:
  - Generate source-backed suggestions mapped to phase themes.
  - Keep this as queue output only, no auto-edit of phase markdown.
- Acceptance tests:
  - Queue files are generated for targeted phases.
  - Suggestions include source paths, rationale, and proposed insertion blocks.

### T404 Add transparency report for suggestion provenance

- Priority: P1
- Type: Observability
- Depends on: T403
- Scope:
  - Produce human-readable rationale file alongside queue output.
  - Explain extraction signals and why each suggestion matters.
- Acceptance tests:
  - Each suggestion has linked provenance in report output.

## M6 Maintainability Refactor and Tests

### T501 Prompt registry extraction

- Priority: P1
- Type: Refactor
- Depends on: T101
- Output:
  - prompts/extraction/*.md
  - prompts/summarization/*.md
- Scope:
  - Move embedded prompt content from crawler into versioned prompt files.
- Acceptance tests:
  - Prompt updates can be made without editing crawler logic.

### T502 Metadata schema contract files

- Priority: P1
- Type: Refactor
- Depends on: T501
- Output:
  - schemas/metadata_taxonomy.schema.json
  - schemas/page_summary.schema.json
  - schemas/site_summary.schema.json
- Scope:
  - Define expected JSON structure and required fields.
- Acceptance tests:
  - Generated outputs validate against schemas.

### T503 Regression test suite bootstrap

- Priority: P0
- Type: Test
- Depends on: T002, T105, T106
- Scope:
  - Add smoke tests for crawl invocation, resume, reports, and sync outputs.
  - Add fixture tests for triage and product generation scripts.
  - Add fixture tests for model routing and six-class image labeling validity.
- Acceptance tests:
  - CI/local test run catches breaking changes in core pipeline behavior.

### T504 Cleanup safety policy for lesson/quiz assets

- Priority: P0
- Type: Reliability
- Depends on: T203
- Scope:
  - Ensure cleanup flow does not delete images referenced in lesson content or quizzes.
- Acceptance tests:
  - Dry-run cleanup flags protected assets as retained.
  - Delete mode keeps protected assets intact.

## Rollout Sequence

1. Execute M1 then M2 first.
2. Ship M3 before M4 to provide triage input for product hardening.
3. Ship M5 after triage and product foundations are in place.
4. Run M6 refactors only after behavior is locked by tests.

## Verification Matrix

1. Crawl reliability
- Success rate across recent target set.
- Timeout and blocked rates by domain.

2. Data fidelity
- Percent of pages with full text retained.
- PDF/transcript completeness rates.

3. Metadata quality
- Non-empty taxonomy rates by category.
- Confidence distribution and fallback usage.

3a. Model policy compliance
- Summarization and review phase model IDs match google/gemma-3-27b.
- Run manifests show model usage for each phase.

4. Product and DB updates
- New product precision and duplicate rate.
- Distillery-resource sync success counts.

4a. Image labeling quality
- Coverage: percent of images labeled at run end.
- Category distribution across bottle, logo, award, lifestyle, equipment, junk.
- Manual spot-check precision for each category.

5. Editorial output quality
- Number of actionable queue items.
- Source provenance coverage ratio.

## Definition of Ready for Implementation Start

1. T001 through T004 scoped and estimated.
2. Acceptance test templates prepared for M1 and M2.
3. Rollback plan documented for orchestration changes.
4. T000, T105, and T106 scoped with model availability checks.

## Definition of Done for Backlog Completion

1. Single entrypoint handles iterative scrape lifecycle with safe recovery.
2. Triaged prioritization and product hardening pipelines are operational.
3. Content generation and phase suggestion queues are reproducible and source-backed.
4. Cleanup policy preserves lesson and quiz assets.
5. Regression suite protects existing crawler capabilities.
6. Summarization and review phases run through LM Studio using google/gemma-3-27b.
7. End-of-run image labeling is present for all new images using the six-category taxonomy.
