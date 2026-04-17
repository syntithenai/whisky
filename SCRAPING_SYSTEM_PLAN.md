# Whisky Scraping System Plan

## Purpose

Define a resilient scraping and content-generation system that:

- Scrapes distillery and resource websites with high reliability.
- Handles direct web pages, PDF documents, and audio/podcast content.
- Generates both full-fidelity source artifacts and structured metadata.
- Produces downstream updates for distillery/resource databases, product records, and lesson-content suggestion queues.
- Recovers cleanly from interruptions and uses previous run knowledge to improve future runs.

## Core Product Goals

1. Reliability first
- Crawl almost all reachable sites with layered fetch strategies.
- Handle common age-verification patterns.
- Track and retry transient failures.

2. Source fidelity
- Preserve full text for HTML, PDF, and transcripts.
- Persist extracted metadata separately from summaries.
- Require full source consultation for lesson-content suggestions.

3. Intelligent prioritization
- Prioritize high-value sources and content types.
- Use run outcomes to improve next-batch ordering.
- Apply domain/site prefilter rules to reduce noise.

4. Safe automation
- Update distillery/resource/product outputs with confidence and provenance.
- Keep manual review where editorial judgment is required.
- Avoid silent data loss through explicit status and completeness tracking.
- Don't throw away any images that are used in lesson content or quizzes.

5. Maintainable evolution
- Separate orchestration, extraction, scoring, and update concerns.
- Move prompts and extraction schemas into editable/versioned configuration.
- Add acceptance tests around feature preservation and regression prevention.

## End-to-End Lifecycle

1. Target preparation
- Load targets from distilleries DB and resources DB/seed.
- Merge with crawl-state memory.
- Select a configurable chunk size (default 15) for iteration.

2. Strategy assignment per URL/site
- Default to direct fetch.
- Use CDP fallback when direct fails or quality is poor.
- Promote repeated problem sites to CDP-first mode.

3. Crawl and extraction
- Capture page HTML text and links.
- Extract PDF text through parser fallback chain.
- Detect and transcribe audio from page and RSS-derived sources.
- Collect images with lightweight junk filtering.

4. In-run analysis
- Screen relevance.
- Extract structured metadata.
- Generate page summaries and keyword sets.
- Persist per-page state including status, reasons, and quality signals.

5. Site-level synthesis
- Build distillery/resource site summaries from page-level outputs.
- Sync enriched summaries and metadata into corresponding databases.
- Write site-level markdown outputs for traceability.

6. Run-level reporting
- Produce crawl report, keyword index, metadata indexes, and quality audit CSV.
- Record success/failure counts and remaining queue.

7. End-of-run image review and labeling
- Use LM Studio with google/gemma-3-27b to label each collected image.
- Apply one category label per image: bottle, logo, award, lifestyle, equipment, or junk.
- Persist labels and confidence so cleanup, product pipelines, and lesson/quiz safeguards can use them.

8. Post-run prioritization and planning
- Score source value by metadata richness, relevance, and factual density.
- Update rules and next-run target priority.
- Queue editorial suggestions and data update opportunities.

## Required Functional Capabilities

### Scraping and Fetching

- Dual fetch path: direct + CDP fallback.
- Optional CDP-first for known-problem sites.
- Age-gate handling for simple legal-age screens.
- Retry rounds with domain cooldown.
- Batch and concurrency controls for pages and sites.

### Multimodal Content

- HTML full-text capture.
- PDF full-text capture and markdown conversion.
- Audio discovery from page and RSS metadata.
- Whisper transcription (service/API/CLI fallback).
- Image collection with junk suppression.

### Metadata and Summary

- Summarization model policy: use LM Studio locally with google/gemma-3-27b for summarization requests.
- Review phase model policy: use LM Studio locally with google/gemma-3-27b for the post-run review phase.

- Extract metadata taxonomy:
  - Distillery names and contact details.
  - Products and purchase references.
  - People, roles, and associations.
  - Flavor terms, glossary terms, equipment terms.
  - Chemical names and company/resource entities.
  - Blog and course/topic suggestions.
- Produce summary text preserving key details and context.

### Data Updates and Outputs

- Distillery DB upsert/sync behavior for discovered updates.
- Resource DB summary and taxonomy sync.
- Product markdown generation and image linkage.
- Distillery page product association behavior and dedicated products-page gating rules.
- Lesson-content suggestion queue files with source-backed recommendations.

### Recovery and Governance

- Resume from state DB after crash/interrupt.
- Track failed pages/sites and retry intelligently.
- Preserve failure diagnostics for later recrawl.
- Cleanup outdated/irrelevant crawl artifacts safely.
- Ensure image labels are available before cleanup so junk can be removed while lesson/quiz-referenced assets are preserved.

## Operational Modes

1. Single run mode
- Execute one batch pass and finish.

2. Iterative mode
- Process sites in chunks.
- Review results after each iteration.
- Continue for N iterations or continuously (0 = forever).

3. Content generation mode
- Generate updates from latest changed sources by default.
- Support filters by site, distillery, date, and category.
- Can be run independently of crawling.

## Data and State Model

1. Crawl state DB
- Site-level status and timestamps.
- Page-level status, relevance, quarantine, and extracted fields.
- Retry history and failure signals.

2. Crawl markdown outputs
- Page summaries.
- Metadata-only companion markdown files.
- Site summary and metadata files.

3. Structured index/report outputs
- Keyword index and metadata index files.
- Crawl quality audit CSV.
- Post-run status reports for distillery/resource orchestrators.

4. Domain/site rule config
- Prefilter rules with global, domain, and site overrides.
- Allow/deny path and query controls.

## Reliability and Recovery Strategy

1. Failure classification
- Distinguish transient timeout/blocking from hard parse/fetch failures.
- Persist clear status signatures.

2. Recovery checkpoints
- Commit page-level outcomes immediately.
- Rebuild queue from persisted crawl state after interruptions.

3. Smart retries
- Retry transient failures with bounded rounds.
- Apply cooldown by domain.
- Defer persistent hard-fail targets for focused recrawl.

4. CDP escalation policy
- Escalate sites with direct-fetch failures or low extraction quality.
- Optionally pre-mark historically problematic domains as CDP-first.

## Cleanup and Storage Hygiene

1. Keep what is useful
- Preserve high-value full text and associated metadata.

2. Remove known noise safely
- Enforce deny patterns and query exclusions.
- Support dry-run cleanup and explicit delete mode.

3. Prevent clutter growth
- Maintain cleanup reports and reason codes.
- Periodically re-evaluate old pages against updated rules.

## Non-Functional Requirements

1. Observability
- Heartbeats and per-site run summaries.
- Explicit status codes in state DB.
- Capture model metadata and prompt version for each summarization, review, and image-label decision.

2. Explainability
- Preserve source URL provenance in summaries/metadata.
- Keep recommendation outputs evidence-backed.

3. Configurability
- Key policies exposed as CLI/config values.

4. Maintainability
- Modular code boundaries and testable components.
- Prompt and schema registries that can evolve without broad rewrites.

## Success Criteria

1. Crawl completion and resume reliability improve across repeated runs.
2. More sites end in successful status with fewer unknown failures.
3. PDF/audio extraction coverage improves measurably.
4. Metadata quality and relevance scoring guide better target selection.
5. End-of-run image labeling quality is stable for the six target categories.
6. Database updates and lesson suggestion queues are consistent, source-backed, and reviewable.
