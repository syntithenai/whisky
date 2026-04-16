# Resource Scrape Post-Run Report

Generated: 2026-04-16T13:29:10.938581+00:00
Attempted: 37
Succeeded: 20
Failed: 0
Timed out: 9
Unknown: 4
Blocked suspected: 0
Remaining queued after run: 8
Retry failed enabled: True
Per-site timeout: 1200s
Max pages per site: 20
Site workers: 2
Retry rounds: 1
Domain cooldown: 900s
LM Studio model: openai/gpt-oss-20b
Quiet crawl: False
Skip podcasts: False

## Timed Out Sites

- The Distiller (Moonshine University)
- Whisky Notes
- TTB Distilled Spirits
- The Whisky Club Australia
- StillDragon Learn
- Bourbon Pursuit
- National Research Institute of Brewing (NRIB)
- Distiller Magazine
- Nip of Courage

## Unknown Status Sites

- Distiller Magazine
- Nip of Courage
- StillDragon Learn
- The Whisky Club Australia

## Remaining Queue

- Bourbon Pursuit
- Whisky Notes
- Nip of Courage
- The Whisky Club Australia
- Distiller Magazine
- StillDragon Learn
- National Research Institute of Brewing (NRIB)
- The Distiller (Moonshine University)

## Review Addendum (2026-04-17)

### What The Scraped Resource Set Can Improve

1. Course content expansion opportunities
- Product-rich resource pages are available at scale (357 resource pages with extracted product names > 0).
- High-value inputs for structured teaching examples are concentrated in:
	- Dekanta collections and product pages (Japanese whisky retail positioning, age/price/availability snapshots).
	- Distiller spirit pages (type, ABV, tasting notes, community ratings).
	- Whisky Notes / Whisky Magazine roundup pages (release timelines and comparative product mentions).
- These pages can be used to expand:
	- Regional identity comparisons (Japan/Scotland/Ireland product line positioning).
	- Product lifecycle lessons (new release, limited release, sold out, travel retail).
	- Sensory language modules (tasting descriptors mapped to style and maturation cues).

2. Quiz expansion opportunities
- Build quiz banks from extracted product metadata fields:
	- Product-to-distillery matching.
	- ABV identification by expression.
	- Category/type classification (single malt, blend, rye, bourbon, etc.).
	- Region and regulation context (Japanese standards, Scotch rules, labeling conventions).
- Use confidence-gated generation:
	- Auto-generate quiz items only when at least 2 of 3 are present: product name, distillery, ABV/type.
	- Flag low-confidence items for manual review.

3. Database expansion opportunities
- Resource database:
	- Add per-page quality flags (product_dense, regulation_dense, process_dense, noisy_page).
	- Store extracted product tuples with confidence and source traceability.
- Distillery database:
	- Backfill product roster tables from bottle-image metadata (name, distillery, image, source URL).
	- Add optional fields for status (active, archive, unknown) and confidence tier.

### Product Records Added In This Review

The following new product markdown files were added using high-confidence scraped bottle assets and source mappings (name, image, distillery, source link):

- data/products/glenfiddich-12-year-old-single-malt.md
- data/products/glenfiddich-15-year-old-single-malt.md
- data/products/glenfiddich-16-single-malt.md
- data/products/glenfiddich-18-year-old-single-malt.md
- data/products/glenfiddich-21-year-old-gran-reserva.md
- data/products/glenfiddich-23-year-old-grand-cru.md
- data/products/bushmills-10-year.md
- data/products/bushmills-12-year.md
- data/products/bushmills-21-year.md
- data/products/bushmills-black-bush.md
- data/products/yamazaki-12.md
- data/products/hakushu-12.md
- data/products/hibiki-japanese-harmony.md

Each record includes:
- title and slug
- distillery
- local image path
- source_image URL
- source_url (purchase link fallback to top-level official source when direct purchase link unavailable)

### Practical Execution Plan

1. Resource triage and scoring (immediate)
- Rank scraped resource pages by useful extraction density:
	- Product names count
	- Distillery names count
	- Presence of ABV/price/type terms
- Route pages into buckets:
	- Product catalog pages (for product DB)
	- Technical/process pages (for course content)
	- Regulatory pages (for compliance content and quiz banks)
	- Noisy/off-topic pages (for deny rules refinement)

2. Product pipeline hardening (short term)
- Expand product record generation to require:
	- name + distillery + image at minimum
	- plus ABV/price/type when available
- Add dedupe rule across:
	- slug
	- source_image hash
	- normalized product title + distillery

3. Course content enrichment (short term)
- Create per-phase insertion queues:
	- Phase 2/4/5: historical and regional release examples
	- Phase 3/6/11: production/process evidence from technical resources
	- Phase 9/10: chemistry/sensory descriptor examples linked to product records
- Add citation blocks in lesson text from high-confidence pages only.

4. Quiz system enrichment (short term)
- Generate question candidates from structured tuples:
	- (product, distillery, type, ABV, region)
- Add distractor generation by same-region or same-category products.
- Store provenance for each quiz item so low-quality questions can be traced and pruned.

5. Crawl quality refinement (medium term)
- Tighten prefilter rules for resource sites that produced high noise.
- Add site-specific allowlist paths for known product/catalog areas.
- Re-run targeted recrawls on timed-out resource sites with page caps and category constraints.

### Suggested Next Target Recrawls For Product Yield

1. Dekanta collections and product pages (highest immediate product DB value).
2. Distiller spirit pages (strong ABV/type/tasting structure).
3. Whisky Club and Whisky Notes product/release pages (timeline and comparison content).

