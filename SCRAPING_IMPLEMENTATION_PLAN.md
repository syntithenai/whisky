# Whisky Scraping Implementation Plan

## Document Objective

Provide an implementation-ready plan that:

1. Preserves current working features.
2. Closes known capability gaps from the target system definition.
3. Reduces maintenance risk as the feature set expands.

This plan is based on direct review of current scripts and runtime behavior.

## Deep Review Baseline (Current Code)

### Primary entry points and orchestrators

- Main crawler: scripts/crawl_whisky_sites.py
- Resource orchestrator: scripts/scrape_resources.sh
- Distillery orchestrator: scripts/scrape_distilleries.sh
- CDP focused recrawl diagnostics: scripts/cdp_recrawl_missed.py

### What is already implemented and must be preserved

1. Crawl state and resumability
- SQLite state model for sites/pages and crawl metadata.
- Page-level status updates and incremental commits.
- Recrawl freshness gate with recrawl-days and force-rescrape override.

2. Fetch strategy capabilities
- Direct HTTP fetch with SSL fallback handling.
- CDP fetch via Playwright and optional CDP browser auto-start.
- Existing logic that upgrades some pages to CDP after direct failure/signals.

3. Multimodal extraction
- PDF extraction with parser fallback chain.
- Audio discovery from page links and RSS feed mapping.
- Whisper transcription with service, Python API, and CLI options.

4. Summarization and metadata extraction
- LLM screening for page relevance.
- Structured extraction for product/review/people/taxonomy/topic candidates.
- Fallback metadata extraction when model output is missing.

5. Site-level synthesis and DB sync
- Distillery site summary synthesis and sync into distilleries DB.
- Resource site summary synthesis and sync into resources DB.
- Site-level markdown outputs.

6. Cleanup and prefilter support
- Machine-readable prefilter rules file with global/domain/site overrides.
- Cleanup script for outdated or noise pages.

7. Reporting and audit outputs
- Run report, keyword index, metadata indexes, quality audit CSV.
- Resource and distillery post-run reports in orchestrator scripts.

### Verified gaps vs requested target system

1. Missing unified orchestrator
- No scripts/scrape.sh that performs chunked iterative loops and final generation semantics.

2. Missing dedicated content-generation entry point
- No scripts/generate_content.sh for independent generation runs with filter controls.

3. Missing triage and implementation scripts from requested plan
- scripts/triage_resources.py not present.
- scripts/build_products_from_triage.py not present.
- No phase insertion queue generator under data/phase_insertion_queue.

4. Product visibility and linkage rules are incomplete
- Current products page uses product markdown availability/archive logic.
- Distillery detail page currently does not render associated products list from distillery-product relationships.
- Existing behavior does not enforce dedicated products page gating rule of requiring name + distillery + image + purchase link.

5. Age-gate handling can be strengthened
- Current handling is broad but generic and not site-rule driven.
- No explicit per-site age-gate selector/policy registry.

6. Retry memory and failure taxonomy can be improved
- State retains error text and status, but no robust structured failure taxonomy/backoff policies by error class.

7. Headed reliability preference not yet reflected in orchestrators
- Current wrappers invoke crawler with headless mode by default.

8. Prompt/editability maintainability gap
- Prompt and extraction schema behavior is mostly embedded in crawler logic rather than centralized editable registry files.

9. Model policy alignment gap
- Summarization and review phases are not yet explicitly pinned to google/gemma-3-27b via local LM Studio policy.

10. End-of-run image labeling gap
- No mandatory post-run LM labeling pass that categorizes each image as bottle, logo, award, lifestyle, equipment, or junk.

## Feature Preservation Contract (Do Not Regress)

All implementation work must preserve these existing behaviors:

1. Resume from existing state DB without data-loss.
2. Existing direct + CDP + whisper fallback paths.
3. Existing distillery/resource DB sync flow.
4. Existing markdown outputs and report artifacts.
5. Existing cleanup script and prefilter rule compatibility.
6. Existing CLI parameters should remain available or be migration-aliased.
7. Existing image assets referenced by lessons and quizzes must remain protected during cleanup.

## Target Architecture (Incremental, Not Rewrite-First)

### Layer 1: Orchestration

- Add scripts/scrape.sh as the single external entry point.
- Keep crawl_whisky_sites.py as crawl engine initially.
- Introduce iterative batching, continuation controls, and iteration review loop.

### Layer 2: Crawl engine policy

- Add policy/config layer for strategy decisions (direct/CDP-first, retry budgets, cooldown).
- Keep existing fetch/transcribe/summarize functions but route through policy decisions.

### Layer 3: Extraction schema and prompts

- Move extraction prompts and output schema constraints into editable prompt registry.
- Add explicit schema version field in outputs and run manifests.
- Add explicit model routing policy so summarization and review phases use google/gemma-3-27b through local LM Studio.

### Layer 4: Post-crawl generation

- Add scripts/generate_content.sh for on-demand content generation.
- Implement triage, product hardening, and lesson suggestion queue generation as separate scripts.

### Layer 5: Quality and governance

- Add run manifest and failure taxonomy outputs.
- Add acceptance checks for feature completeness and regressions.
- Add end-of-run image labeling pass and quality checks for category consistency.

## Implementation Workstreams

## Workstream A: Unified Entry Point and Iterative Lifecycle

### Deliverables

1. scripts/scrape.sh
- Parameters:
  - chunk-size (default 15)
  - continue (boolean or integer loops)
  - continue-count (0 means forever)
  - filters for distillery/resource/date/name
  - browser-mode (headed default, headless override)

2. Iteration behavior
- Per iteration:
  - select targets
  - run scrape
  - write iteration review summary
  - update priority queue
- Content generation deferred until terminal iteration of the run.

### Acceptance criteria

1. One command runs the full scrape lifecycle.
2. Looping mode works for finite and infinite runs.
3. Content generation is skipped during intermediate iterations.

## Workstream B: Strategy Hardening (Direct/CDP, Retry, Recovery)

### Deliverables

1. Structured failure taxonomy
- Standardize status classes: transient_timeout, blocked_suspected, parse_failure, extraction_failure, fatal_fetch.

2. Retry policy registry
- Policy by failure class with retry budget and cooldown.

3. CDP-first site memory
- Persist per-site strategy preference and rationale.

4. Resume safety improvements
- Preserve current page-level commit behavior.
- Add run-level manifest with iteration checkpoints.

### Acceptance criteria

1. Failed-target retries are deterministic and explainable.
2. CDP-first promotions are visible in state.
3. Interrupted runs resume without duplicate heavy work.

## Workstream C: Multimodal Fidelity and Asset Hygiene

### Deliverables

1. Completeness tracking per page
- Flags for html/pdf/audio/transcript/images/metadata/summary completeness.

2. Image hygiene policy updates
- Preserve broad capture but suppress obvious ads/tracking/junk.

3. PDF/audio recovery hooks
- Identify and re-queue pages with extraction-incomplete outcomes.

4. End-of-run image categorization
- Add mandatory LM Studio image review step at run end.
- Use google/gemma-3-27b and emit one label per image from: bottle, logo, award, lifestyle, equipment, junk.
- Persist label confidence and rationale snippet for audit and cleanup decisions.

### Acceptance criteria

1. Full-text preservation for HTML, PDF, transcript is measurable.
2. Extraction-incomplete pages can be targeted in recovery mode.
3. Every newly captured image has a post-run category label from the six-category taxonomy.

## Workstream D: Triage and Prioritization

### Deliverables

1. scripts/triage_resources.py
- Parse metadata taxonomy counts from crawl markdown.
- Compute bucket and quality score.
- Write data/resource_triage.json and CSV.

2. Rule-aware ranking updates
- Rank next targets by relevance, density, and extraction value.
- Feed updates into iterative chunk selection.

3. Prefilter rule enhancement workflow
- Maintain data/resource_prefilter_rules.json with allow_path_prefixes and block_path_prefixes additions.

### Acceptance criteria

1. Triage output is reproducible for fixed inputs.
2. Next-run ordering reflects triage scores.

## Workstream E: Product Pipeline Hardening

### Deliverables

1. scripts/build_products_from_triage.py
- Read product_catalog pages from triage output.
- Parse product tuples from main markdown.
- Apply confidence gates and dedupe safeguards.

2. Product linkage policy
- Upsert product markdown and relation mapping to distillery records.
- Ensure distillery detail views can list all known products.
- Keep dedicated products listing restricted to complete products (name + distillery + image + purchase link).

### Acceptance criteria

1. Duplicate products are not reintroduced.
2. Distillery-to-product links are present and queryable.
3. Dedicated products page filters to complete products only.

## Workstream F: Lesson Suggestion Queues and Content Generation

### Deliverables

1. Dense-topic index pass
- Build source-density and topic-richness index before suggestion generation.

2. Suggestion generation pipeline
- Source-backed, concrete edits by phase file.
- Explicit evidence snippets and insertion rationale.

3. Queue output
- Write companion queue files under data/phase_insertion_queue/.

4. scripts/generate_content.sh
- Default to latest 100 updated files.
- Support filters by site, distillery, date, and source category.

### Acceptance criteria

1. Suggestion queue is actionable and traceable to sources.
2. Suggestions rely on full source text, not summary-only pages (except transcript-origin constraints).

## Workstream G: Maintainability Refactor

### Deliverables

1. Prompt registry
- Move extraction prompts to editable files with version tags.

1a. Model policy registry
- Add centralized model policy configuration for summarization and review.
- Pin both phases to google/gemma-3-27b in LM Studio local routing.

2. Schema registry
- Typed metadata schema contracts with migration notes.

3. Module boundary extraction
- Split crawler concerns into modules without changing external behavior.

4. Test harness
- Unit tests for parsing/dedupe/scoring.
- Integration tests for fetch/summarize/sync pipeline.
- Recovery tests for interrupted runs.

### Acceptance criteria

1. Prompt and schema edits can be made without touching crawler internals.
2. Core pipeline behavior passes regression suite.
3. Summarization and review model routing is controlled by configuration and defaults to google/gemma-3-27b.

## Phased Timeline

## Phase 1 (Foundation)

- Add scripts/scrape.sh, run manifests, and strategy policy config.
- Keep existing crawler as backend.

## Phase 2 (Data quality and prioritization)

- Implement triage script and quality-based queue ordering.
- Add completeness tracking and stronger failure taxonomy.

## Phase 3 (Generation pipelines)

- Implement product hardening script.
- Add generate_content.sh and phase queue generation.

## Phase 4 (Maintainability)

- Prompt/schema registry.
- Module decomposition and test coverage expansion.

## Risks and Mitigations

1. Monolithic crawler complexity
- Mitigation: wrapper-first incremental changes, then modular extraction.

2. Behavior regressions during refactor
- Mitigation: feature preservation checklist and fixture-based regression tests.

3. LLM variability in extraction
- Mitigation: schema validation, fallback extraction, confidence tagging, and audit reports.

5. Image label drift across runs
- Mitigation: stable prompt template, confidence thresholds, and periodic spot-check set for the six-category taxonomy.

4. Growth in crawl artifacts
- Mitigation: cleanup policy reports and quarantine/deletion controls.

## Definition of Done

1. Single command lifecycle with chunked iteration and continuation.
2. Reliable fallback strategy with persistent failure memory.
3. Full-text retention and metadata/summaries for multimodal inputs.
4. Deterministic triage and improved target prioritization.
5. End-of-run image labeling is enforced with categories: bottle, logo, award, lifestyle, equipment, junk.
6. Distillery/resource/product updates and lesson suggestion queues generated with provenance.
7. No regression of current reporting/sync/resume capabilities.
