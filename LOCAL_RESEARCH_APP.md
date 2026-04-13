# Local Distillery and Resource Research Databases and Website

This project now includes two local pipelines:

1. Distillery pipeline: turns `DISTILLERY_STUDY_TRACKER.md` into a searchable SQLite database.
2. Resource pipeline: turns curated whisky resource links into a searchable SQLite database focused on making, history, culture, and practical small-distillery operations.

## What It Does

1. Parses all markdown tracker tables into normalized records.
2. Derives whisky-style tags from the text (for style-based search).
3. Optionally crawls official distillery websites and saves images with emphasis on:
   - logos
   - bottle/product imagery
   - distilling/process imagery
4. Serves a local website where you can search by:
   - name
   - country
   - region
   - style tags
   - operating status
   - website confidence
   - whether images are available
5. Builds and serves an offline-ready whisky resources index with filters for:
   - category
   - focus area (making, history, culture, operations, regulation)
   - audience (including small distillery focus)
   - region scope
   - cost and relevance
   - tags and notes

## Files Added

- `scripts/build_database.py`: build and enrich the SQLite database.
- `scripts/build_resources_database.py`: build the resources SQLite database from curated seed JSON.
- `scripts/export_resources_json.py`: export resources DB to JSON for offline web use.
- `scripts/serve_site.py`: local web server for search and distillery pages.
- `whisky_local/markdown_tracker.py`: markdown parser + style inference.
- `whisky_local/database.py`: schema + persistence helpers.
- `whisky_local/resources_database.py`: resources schema + persistence helpers.
- `whisky_local/enrichment.py`: site crawl + image capture/classification.
- `data/resource_sites_seed.json`: curated resource website seed data.

## Quick Start

From the repository root:

```bash
python3 scripts/build_database.py --tracker DISTILLERY_STUDY_TRACKER.md --db data/distilleries.db
python3 scripts/build_resources_database.py --db data/resources.db --export-json
./scripts/start_site.sh
```

Open `http://127.0.0.1:8080`.

Use `http://127.0.0.1:8080/database` for distilleries and `http://127.0.0.1:8080/resources` for resource websites.

The start script always replaces any existing process already bound to the selected port before launching the new server instance.

Optional overrides:

```bash
PORT=8090 HOST=0.0.0.0 ./scripts/start_site.sh
DB_PATH=/custom/distilleries.db WEB_DATA_PATH=/custom/web ./scripts/start_site.sh
./scripts/start_site.sh --static-mode
```

## Run Full Image Enrichment

```bash
python3 scripts/build_database.py \
  --tracker DISTILLERY_STUDY_TRACKER.md \
  --db data/distilleries.db \
  --crawl-images \
  --max-pages 4 \
  --max-images 24
```

Images are saved under `data/images/<distillery-slug>/` and shown in each distillery detail page.

## Rebuild Resource Library

```bash
python3 scripts/build_resources_database.py \
   --seed data/resource_sites_seed.json \
   --db data/resources.db \
   --export-json \
   --json-out-dir data/web
```

This updates:

- `data/resources.db`
- `data/web/resources.json`
- `data/web/resources-taxonomy.json`
- `data/web/resources-manifest.json`

## Practical Notes

- Crawling all distilleries can take a while and some sites block bots.
- Re-run periodically to refresh records and collect newly published images.
- If a site has no usable official URL in the tracker, image capture is skipped for that entry.
- Resource links are curated and should be periodically reviewed for quality and relevance.
