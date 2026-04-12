# JSON + PWA Migration Plan for Whisky Website

## Goal

Migrate the current SQLite-backed local website to a JSON-powered web app that supports fast client-side search, installable PWA behavior, and embedded/offline images.

This is a planning document only. No implementation changes are included here.

## Current State Snapshot

- Data source is `data/distilleries.db` (SQLite).
- Server-side routes currently render pages from Python.
- Images are stored as files under `data/images/...` and referenced by `images.local_path`.
- Search/filter logic is SQL-based and runs on the server.

## Target State

- Website runs as a static or mostly-static app using structured JSON data files.
- Search and filtering run in browser JavaScript (with optional indexed client storage).
- App is installable via manifest + service worker (PWA).
- Distillery and curriculum pages work offline after install.
- Images are available offline (cached and/or bundled strategy).

## Migration Principles

1. Keep canonical source of truth in SQLite during transition.
2. Produce deterministic JSON exports from the DB in a repeatable build step.
3. Version exported JSON schema and support backward compatibility for one version.
4. Start with read-only parity (same data shown), then add enhanced search UX.
5. Ship offline support in stages to avoid large-cache failures.

## Proposed JSON Data Model

### distilleries.json

One record per distillery with denormalized fields needed for search and detail pages.

Suggested fields:

- `id` (number)
- `name` (string)
- `slug` (string)
- `country` (string)
- `region` (string)
- `section` (string)
- `officialSite` (string)
- `websiteConfidence` (string)
- `operatingStatus` (string)
- `studyStatus` (string)
- `whyStudy` (string)
- `keyFocus` (string)
- `notes` (string)
- `styles` (string[])
- `imageCount` (number)
- `images` (array of image metadata objects)

Image metadata object:

- `path` (string, app-relative)
- `category` (string)
- `altText` (string)
- `sourceUrl` (string)
- `score` (number)

### taxonomy.json

Precomputed lookup values for filters and faceting:

- `countries` (string[])
- `regions` (string[])
- `styles` (string[])
- `operatingStatuses` (string[])
- `websiteConfidenceLevels` (string[])
- `imageCategories` (string[])

### curriculum-phase1.json (optional)

If Phase 1 markdown is later preprocessed:

- `rawMarkdown` (string) or
- `sections` array with heading hierarchy and rendered HTML fragments.

## Export Pipeline Plan (SQLite -> JSON)

1. Create a new exporter script, for example `scripts/export_json_dataset.py`.
2. Read from SQLite with explicit SQL queries for distilleries, styles, and images.
3. Build denormalized in-memory records keyed by distillery id.
4. Normalize missing/null values into consistent JSON output.
5. Write:
   - `data/web/distilleries.json`
   - `data/web/taxonomy.json`
6. Produce a small manifest file:
   - `data/web/dataset-manifest.json` with `schemaVersion`, `generatedAt`, `recordCount`, checksums.
7. Add validation step to fail build if required fields are missing.

## Search Architecture Plan

### Phase A: Direct In-Memory Search

- Load `distilleries.json` once.
- Implement filter predicates for country/region/style/status/confidence/images.
- Add text search across `name`, `whyStudy`, `keyFocus`, `notes`, `styles`.

### Phase B: Indexed Search

- Add a lightweight client index (for example MiniSearch/FlexSearch or custom token map).
- Precompute tokenized fields in build output for faster startup.
- Store parsed dataset in IndexedDB for repeat-visit performance.

### Phase C: Advanced Query UX

- Combined text + facet search.
- Sort by relevance/date/name/imageCount.
- URL-persisted query state for shareable links.

## Routing and Page Model Plan

- Keep path-based routing:
  - `/`
  - `/phase-1`
  - `/database`
  - `/distillery/:id` or `/distillery/:slug`
- Move to client-side router only after parity is confirmed.
- Keep static fallback handling for deep links in deployment target.

## PWA Packaging Plan

1. Add `manifest.webmanifest`:
   - app name, short name, theme/background colors, icons.
2. Add service worker:
   - App shell caching for HTML/CSS/JS.
   - Runtime caching for dataset JSON and image assets.
3. Define cache versioning strategy:
   - Separate `app-shell-vN`, `dataset-vN`, `images-vN` caches.
4. Add update flow:
   - detect new dataset manifest and prompt user to refresh.

## Image Embedding / Offline Strategy Plan

Use a hybrid strategy to balance install size and offline utility.

### Tier 1 (recommended baseline)

- Keep images as files in app package/static assets.
- Service worker caches image requests on first view.
- Precache key curriculum images and top-N distillery thumbnails.

### Tier 2 (optional for full offline completeness)

- Build step creates image bundles per region/category (zip chunks or grouped folders).
- App offers optional "Download full image pack" action.
- Cache usage UI shows storage consumption and allows cleanup.

### Tier 3 (not default)

- Base64 embedding in JSON for selected small assets only (icons/logos), not full photo sets.

## Performance and Size Guardrails

- Keep initial install payload under target threshold (for example 30-50 MB baseline).
- Lazy-load non-critical images and detail data.
- Consider splitting `distilleries.json` by country/region if growth continues.
- Monitor parse time, memory usage, and first interactive render on mid-range mobile.

## Data Quality and Validation Plan

- Add schema validation (JSON Schema) in export step.
- Enforce unique ids/slugs and valid image paths.
- Flag invalid URLs and missing categories in diagnostics output.
- Add regression checks comparing DB counts vs exported JSON counts.

## Rollout Phases

1. Phase 1: JSON export script + schema validation.
2. Phase 2: Website reads JSON for `/database` while keeping current server fallback.
3. Phase 3: Client-side search + route state in URL.
4. Phase 4: PWA manifest + service worker for app shell.
5. Phase 5: Offline dataset + image caching strategy.
6. Phase 6: Optional full static deployment mode.

## Risks and Mitigations

- Risk: Large image set causes install/storage issues.
  - Mitigation: tiered image caching and optional pack download.
- Risk: Search latency on low-memory devices.
  - Mitigation: precomputed index fields and chunked loading.
- Risk: Data drift between SQLite and JSON exports.
  - Mitigation: manifest checksums and CI validation.
- Risk: stale offline data.
  - Mitigation: dataset version checks and update prompt UX.

## Acceptance Criteria

- Data parity with SQLite pages for core fields.
- Database page fully searchable from JSON data.
- Deep links and direct URL navigation work.
- App is installable and functional offline for core pages.
- Key educational and distillery images are available offline according to chosen tier.
- Export pipeline is repeatable and validated.
