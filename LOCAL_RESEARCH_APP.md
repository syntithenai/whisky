# Local Distillery Research Database and Website

This project now includes a local pipeline that turns `DISTILLERY_STUDY_TRACKER.md` into a searchable SQLite database and a simple website.

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

## Files Added

- `scripts/build_database.py`: build and enrich the SQLite database.
- `scripts/serve_site.py`: local web server for search and distillery pages.
- `whisky_local/markdown_tracker.py`: markdown parser + style inference.
- `whisky_local/database.py`: schema + persistence helpers.
- `whisky_local/enrichment.py`: site crawl + image capture/classification.

## Quick Start

From the repository root:

```bash
python3 scripts/build_database.py --tracker DISTILLERY_STUDY_TRACKER.md --db data/distilleries.db
python3 scripts/serve_site.py --db data/distilleries.db --port 8080
```

Open `http://127.0.0.1:8080`.

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

## Practical Notes

- Crawling all distilleries can take a while and some sites block bots.
- Re-run periodically to refresh records and collect newly published images.
- If a site has no usable official URL in the tracker, image capture is skipped for that entry.
