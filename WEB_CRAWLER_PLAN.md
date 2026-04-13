# Whisky Site Crawler Plan

## Goal

Create a resumable crawler for distillery and resource websites that:

- handles age-gate UI reliably (distillery websites)
- crawls site-internal pages and captures useful content
- summarizes pages into structured markdown using local LM Studio
- stores persistent crawl state to avoid unnecessary re-scraping
- builds and maintains a keyword index across captured pages
- runs in bounded batches (N sites per execution) and reports progress

## Implemented Script

- [scripts/crawl_whisky_sites.py](scripts/crawl_whisky_sites.py)

This script is designed for long-running local use and can be re-run safely.

## Architecture

1. Site Target Discovery
- Distillery targets from [data/distilleries.db](data/distilleries.db), table `distilleries.official_site`
- Resource targets from [data/resources.db](data/resources.db), table `resources.url`
- Fallback resource targets from [data/resource_sites_seed.json](data/resource_sites_seed.json)

2. Browser Fetch Layer
- Selenium (Chrome) loads each page
- Generic age-gate clicker attempts common legal-age confirmation buttons
- Captures fully-rendered HTML and visible text

3. Crawl and Discovery
- Same-domain BFS crawl queue
- Per-site `--max-pages-per-site` guard
- Link normalization, de-duplication, and binary-asset path exclusion

4. LLM Summarization
- Calls LM Studio OpenAI-compatible endpoint
- Default model setting: `qwen3.5-27b-claude-4.6-opus-reasoning-distilled-v2`
- Outputs markdown summary + topical keywords for each page
- Fallback summary/keywords when LM output fails

5. Persistent State and Resume
- State DB: [data/site_crawl_state.db](data/site_crawl_state.db)
- Tracks sites, pages, content hash, links, summary markdown, keywords, crawl status/timestamps
- Skips fresh pages based on `--recrawl-days` unless `--force-rescrape`

6. Output Artifacts
- Per-page markdown files: [data/crawl_markdown](data/crawl_markdown)
- Run report: [data/crawl_report.md](data/crawl_report.md)
- Keyword index markdown: [data/keyword_index.md](data/keyword_index.md)

## Data Model (State DB)

1. `sites`
- one row per root website
- last crawl timestamp and status

2. `pages`
- one row per crawled URL per site
- text content, extracted links, content hash, summary markdown, keywords, status

3. `keyword_index`
- inverted index of keyword -> site/page URL

## Rescrape Rules

Default behavior:

- If page was crawled within `--recrawl-days`, skip fetch and reuse cached links.
- If fetched page hash is unchanged, reuse prior summary/keywords.
- If changed, re-summarize and update index.

Force refresh behavior:

- `--force-rescrape` bypasses freshness and hash reuse.

## Batch Execution Pattern

Recommended first run:

```bash
python3 scripts/crawl_whisky_sites.py \
  --site-types both \
  --max-sites 10 \
  --max-pages-per-site 25 \
  --recrawl-days 14 \
  --headless \
  --lmstudio-url http://127.0.0.1:1234/v1 \
  --lmstudio-model qwen3.5-27b-claude-4.6-opus-reasoning-distilled-v2
```

Distillery-only run (age-gate-heavy set):

```bash
python3 scripts/crawl_whisky_sites.py \
  --site-types distillery \
  --max-sites 8 \
  --max-pages-per-site 30 \
  --headless
```

Resource-only run:

```bash
python3 scripts/crawl_whisky_sites.py \
  --site-types resource \
  --max-sites 20 \
  --max-pages-per-site 20 \
  --headless
```

## Operational Guidance

1. Keep batches small at first (5-10 sites) to validate anti-bot behavior.
2. Increase `--age-gate-wait` for difficult distillery sites.
3. Use `--force-rescrape` only when you intentionally want a full refresh.
4. Re-run nightly or weekly with moderate `--max-sites` to progressively complete coverage.

## Dependencies

Python requirements:

- selenium
- google-chrome and matching chromedriver on PATH (or local fallback at `tools/chromedriver`)

Install example:

```bash
python3 -m pip install selenium
```

## Future Improvements

1. Per-site custom age-gate selectors for known difficult brands.
2. Optional robots.txt policy modes.
3. Incremental sitemap ingestion before BFS.
4. Optional JSON export of summaries for UI integration.
5. Retry queues and backoff profiles by site.
