# Product Image Sync Implementation

## Overview
Implemented two new features for the whisky crawler to enhance product data quality:
1. **Image Extraction & Product Matching** - Capture images from crawled content and match them to products
2. **Outdated File Cleanup** - Remove obsolete crawled files based on refined prefilter rules (v2)

## Modules Created

### 1. `scripts/enhance_products_with_images.py`
**Purpose:** Extract images from HTML content, match to products, download images, and create product markdown records.

**Key Functions:**

- `extract_image_urls_from_html(html_content, base_url)` → `list[dict]`
  - Parses HTML for `<img>` and `<picture>` tags
  - Resolves relative URLs to absolute URLs
  - Filters out icons, logos, tracking pixels
  - Returns list of image dicts with: url, alt_text, title, context

- `match_products_to_images(products, images, content_text)` → `list[dict]`
  - Heuristics for matching products to images:
    - Product name appears in image alt text (score +2)
    - Keywords from product name in URL (score +1)
    - Same domain as purchase links (score +3)
    - Prefer larger images (score +0.5)
  - Returns products with matched image URLs

- `download_image(url, timeout=60)` → `bytes | None`
  - Downloads image from URL with User-Agent header
  - Robust error handling

- `get_image_extension(content)` → `str | None`
  - Detects image format from file bytes
  - Supports: JPEG, PNG, GIF, WebP

- `save_product_image(image_bytes, product_name, distillery="")` → `str | None`
  - Saves image to `/data/products/images/`
  - Filename format: `{distillery_slug}_{product_slug}.{ext}`
  - Deduplicates by checking file content
  - Returns relative path for reference in markdown

- `generate_product_markdown(product, distillery="", image_path=None)` → `str`
  - Generates YAML frontmatter with product metadata
  - Extracts: ABV, category, price from product facts
  - Returns markdown content ready for file write

- `create_or_update_product_file(product, distillery="", image_path=None)` → `str | None`
  - Creates/updates product markdown in `/data/products/`
  - Filename: `{product_slug}.md`
  - Only writes if content differs (avoids unnecessary updates)

- `sync_product_images_from_crawl(page_data)` → `dict`
  - **Main orchestration function** to call from crawl pipeline
  - Coordinates all steps: extract → match → download → save → markdown
  - Input: page_data dict with html_content, products, distillery, source_url
  - Returns: updated page_data with product image data

**Integration Points:**
- Can be called from `crawl_whisky_sites.py` after page content extraction
- Processes multiple products per page
- Graceful degradation if images unavailable or matching fails

**Directory Structure:**
```
data/products/
  ├── images/
  │   ├── glenfiddich_12-year-old.jpg
  │   ├── macallan_sherry-oak.jpg
  │   └── ...
  ├── glenfiddich-12-year-old.md
  ├── macallan-sherry-oak.md
  └── ...
```

### 2. `scripts/cleanup_outdated_crawl.py`
**Purpose:** Identify and delete markdown files that no longer match current prefilter rules.

**Key Functions:**

- `load_prefilter_rules()` → `dict`
  - Loads `resource_prefilter_rules.json` (v2+)
  - Returns rule configuration

- `should_deny_by_global_pattern(url, rules)` → `bool`
  - Checks URL against 25 global deny patterns
  - Patterns: `/tag/`, `/category/`, `/archive`, pagination, etc.

- `should_deny_by_query_param(url, rules)` → `bool`
  - Checks for denied query parameters: page, utm_*, fbclid, etc.

- `should_deny_by_domain_rules(url, resource_name, rules)` → `bool`
  - Applies domain-specific rules (14 domains configured)
  - Evaluates allow_url_regex whitelist and deny patterns

- `should_deny_by_site_rules(url, resource_name, rules)` → `bool`
  - Applies site-specific rules (23 sites configured)
  - Allows per-resource precise filtering

- `get_url_from_database(markdown_path)` → `str | None`
  - Queries `site_crawl_state.db` to retrieve URL for a markdown file
  - Enables smart URL-based filtering without reparsing markdown

- `should_delete_file(filepath, rules)` → `(bool, str)`
  - **Core deletion logic**
  - Strategy:
    1. Check if filename matches deny pattern → DELETE (catches -metadata.md, etc.)
    2. Get URL from database, check against all rules
    3. No URL available? → KEEP (unsynced files)
  - Returns: (should_delete, reason_code)

- `analyze_cleanup(dry_run=True)` → `dict`
  - Scans all markdown files in `crawl_markdown/`
  - Classifies each file: delete or keep
  - Returns stats: total_files, to_delete, deletions_by_reason, file_list

- `execute_cleanup(yes_delete=False)` → `dict`
  - Runs cleanup analysis + optionally deletes files
  - Dry-run by default; use `--yes-delete` flag to execute
  - Prints detailed report with reason breakdowns
  - Handles deletion errors gracefully

**Deletion Reasons:**
- `filename_matches_-metadata.md$` - Metadata-only files (502 deleted)
- `global_deny_pattern` - URL matches global deny pattern
- `deny_query_param` - URL contains denied query parameter
- `domain_deny_rule` - URL fails domain-specific filtering
- `site_deny_rule` - URL fails site-specific filtering
- `no_url_in_database` - Kept (no URL available for checking)

**Usage:**
```bash
# Dry-run analysis
python3 scripts/cleanup_outdated_crawl.py

# Execute deletion
python3 scripts/cleanup_outdated_crawl.py --yes-delete
```

## Cleanup Results

**Execution Date:** 2026-04-14

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total markdown files | 1,286 | 782 | -504 (-39.2%) |
| Metadata-only files | 502 | 0 | -502 |
| Other filtered files | 2 | 0 | -2 |
| Content files retained | 782 | 782 | ✓ |

**Deletions by Category:**
- `-metadata.md` pattern: 502 files (99.6%)
- Sitemap/TOC pattern: 1 file
- Error page pattern: 1 file

**Resource Impact:**
- Metadata-only files (38.9% of crawl) eliminated
- Clean separation between content and metadata
- Improved crawl_markdown directory signal-to-noise ratio
- Smaller directory for processing

## Integration with crawl_whisky_sites.py

### To integrate image sync:

```python
# In crawl pipeline, after extracting page metadata:
from scripts.enhance_products_with_images import sync_product_images_from_crawl

page_data = {
    'html_content': raw_html,
    'products': extracted_products,
    'distillery': distillery_name,
    'source_url': page_url
}

# Enhance with images
page_data = sync_product_images_from_crawl(page_data)

# Now page_data['products'] has image_path for matched products
# Product markdown files created in /data/products/
```

### Database Requirements:
- Cleanup script queries `site_crawl_state.db` (already present)
- Image sync reads `html_content` (available from CDP)
- Product markdown stored separately from crawl_markdown

## Configuration

### Prefilter Rules (resource_prefilter_rules.json)
- **Version:** 2 (deployed and validated)
- **Global Rules:** 25 deny patterns + 11 query params
- **Domain Rules:** 14 domains with precision filtering
- **Site Rules:** 23 individual resources with explicit rules

### Product Image Settings
- **Storage:** `/data/products/images/`
- **Filename Format:** `{distillery_slug}_{product_slug}.{ext}`
- **Supported Formats:** JPEG, PNG, GIF, WebP
- **Download Timeout:** 60 seconds

## Next Steps

1. **Integrate into Crawl Pipeline:**
   - Modify `crawl_whisky_sites.py` to call `sync_product_images_from_crawl()`
   - Execute after page.py processing, before database storage

2. **Run Production Crawl:**
   - Execute with v2 prefilter rules
   - Expect ~40% baseline noise reduction
   - Track image extraction success rate

3. **Product Database Growth:**
   - Monitor `/data/products/` directory
   - Validate product metadata accuracy
   - Track image matching success rates

4. **Baseline Metrics:**
   - Document post-cleanup crawl stats
   - Compare baseline vs. v2 rules effectiveness
   - Measure product image extraction rates

## Testing

**Manual verification completed:**
- [x] Image extraction from sample HTML pages
- [x] Product-image matching heuristics
- [x] Image download and format detection
- [x] Product markdown generation with YAML frontmatter
- [x] Cleanup analysis on 1,286 files
- [x] Deletion of 504 outdated files verified

**To test new features:**
```bash
# Test cleanup script
python3 scripts/cleanup_outdated_crawl.py

# Test image sync on sample page (after integration)
python3 -c "
from scripts.enhance_products_with_images import sync_product_images_from_crawl
# Provide test page_data
"
```

## Dependencies

- **Standard Library Only:** pathlib, json, re, sqlite3, urllib, hashlib, datetime, typing
- **No External Dependencies Required:** Uses built-in Python modules only

## Status

✅ **Complete and Ready for Integration**

- Image extraction module: Ready for pipeline integration
- Cleanup script: Executed successfully (504 files deleted)
- Product markdown structure: Established and tested
- Database queries: Verified working
- No new dependencies required
