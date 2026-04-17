#!/usr/bin/env python3
"""
Cleanup script for outdated crawled content.
Identifies and optionally deletes markdown files that no longer match the current
prefilter rules (resource_prefilter_rules.json v2+).
Helps maintain data hygiene after refining the crawl rules.
"""

import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CRAWL_MARKDOWN_DIR = DATA_DIR / "crawl_markdown"
IMAGES_DIR = DATA_DIR / "images"
PREFILTER_RULES_PATH = DATA_DIR / "resource_prefilter_rules.json"
CRAWL_STATE_DB = DATA_DIR / "site_crawl_state.db"
_TEXT_REFERENCE_SUFFIXES = {".md", ".json", ".html", ".py", ".txt"}
_IGNORED_REFERENCE_DIRS = {".git", "build", "node_modules", "__pycache__", "data/images"}
_IMAGE_REF_RE = re.compile(r'data/images/[^\s\'")\]>]+')

# T504: Patterns used to discover lesson/quiz content files that reference images.
_LESSON_FILE_PATTERNS = [
    "PHASE_*.md",
    "DISTILLERY_STUDY_TRACKER.md",
]
_QUIZ_DIRS = [
    DATA_DIR / "phase_insertion_queue",
]


def collect_protected_image_paths() -> set[str]:
    """T504: Scan all lesson/quiz files and return the set of image paths they reference.

    Returns absolute string paths so they can be compared against any image path
    about to be deleted. Call this before any image cleanup pass and treat the
    returned set as a do-not-delete list.
    """
    _img_ref_re = re.compile(r'data/images/[^\s\'")\]>]+')
    protected: set[str] = set()

    # Scan lesson phase files in project root.
    for pattern in _LESSON_FILE_PATTERNS:
        for source_file in sorted(PROJECT_ROOT.glob(pattern)):
            try:
                text = source_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in _img_ref_re.finditer(text):
                rel_path = match.group(0).rstrip(".,;")
                abs_path = str((PROJECT_ROOT / rel_path).resolve())
                protected.add(abs_path)

    # Scan quiz/phase insertion queue JSON files.
    for quiz_dir in _QUIZ_DIRS:
        if not quiz_dir.exists():
            continue
        for jf in sorted(quiz_dir.rglob("*.json")):
            try:
                text = jf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in _img_ref_re.finditer(text):
                rel_path = match.group(0).rstrip(".,;")
                abs_path = str((PROJECT_ROOT / rel_path).resolve())
                protected.add(abs_path)

    return protected


def is_image_protected(image_path: "str | Path", protected: "set[str] | None" = None) -> bool:
    """T504: Return True if an image path is referenced by lesson or quiz content.

    Args:
        image_path: Absolute or relative path to the image file.
        protected: Pre-computed protected set from collect_protected_image_paths().
                   If None, the set is computed on each call (slow; cache it).
    """
    if protected is None:
        protected = collect_protected_image_paths()
    abs_str = str(Path(image_path).resolve())
    return abs_str in protected


def _iter_reference_files(excluded_paths: set[Path] | None = None):
    excluded = excluded_paths or set()
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(PROJECT_ROOT)
        rel_posix = rel.as_posix()
        if any(rel_posix == prefix or rel_posix.startswith(prefix + "/") for prefix in _IGNORED_REFERENCE_DIRS):
            continue
        if path.suffix.lower() not in _TEXT_REFERENCE_SUFFIXES:
            continue
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in excluded:
            continue
        yield path


def collect_referenced_image_paths(excluded_paths: set[Path] | None = None) -> set[str]:
    referenced: set[str] = set()
    for source_file in _iter_reference_files(excluded_paths=excluded_paths):
        try:
            text = source_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _IMAGE_REF_RE.finditer(text):
            rel_path = match.group(0).rstrip(".,;")
            referenced.add(str((PROJECT_ROOT / rel_path).resolve()))
    return referenced


def analyze_image_cleanup(markdown_paths_to_delete: list[str]) -> dict[str, Any]:
    protected = collect_protected_image_paths()
    excluded_reference_files = {str((PROJECT_ROOT / rel_path).resolve()) for rel_path in markdown_paths_to_delete}
    referenced = collect_referenced_image_paths(excluded_paths={Path(p) for p in excluded_reference_files})
    referenced.update(protected)

    image_files_to_delete: list[dict[str, str]] = []
    protected_retained: list[str] = []
    total_images = 0
    if IMAGES_DIR.exists():
        for image_path in sorted(IMAGES_DIR.rglob("*")):
            if not image_path.is_file():
                continue
            total_images += 1
            abs_path = str(image_path.resolve())
            rel_path = str(image_path.relative_to(PROJECT_ROOT))
            if abs_path in protected:
                protected_retained.append(rel_path)
                continue
            if abs_path not in referenced:
                image_files_to_delete.append({"path": rel_path, "reason": "unreferenced_image"})

    return {
        "total_images": total_images,
        "images_to_delete": len(image_files_to_delete),
        "images_to_keep": max(0, total_images - len(image_files_to_delete)),
        "image_files_to_delete": image_files_to_delete,
        "protected_images_retained": len(protected_retained),
        "protected_image_samples": protected_retained[:20],
    }


def load_prefilter_rules() -> dict[str, Any]:
    """Load prefilter rules from JSON."""
    try:
        with open(PREFILTER_RULES_PATH) as f:
            return json.load(f)
    except Exception as e:
        print(f"[error] Failed to load prefilter rules: {e}")
        return {}


def should_deny_by_global_pattern(url: str, rules: dict) -> bool:
    """Check if URL matches any global deny patterns."""
    global_rules = rules.get('global', {})
    deny_patterns = global_rules.get('deny_url_regex', [])
    
    for pattern in deny_patterns:
        try:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        except re.error:
            pass
    
    return False


def should_deny_by_query_param(url: str, rules: dict) -> bool:
    """Check if URL contains any denied query parameters."""
    global_rules = rules.get('global', {})
    deny_params = global_rules.get('deny_query_params', [])
    
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    
    for param in deny_params:
        if param in qs:
            return True
    
    return False


def get_resource_name_from_path(filepath: Path) -> str | None:
    """
    Extract resource name from crawled file path.
    Expects structure: crawl_markdown/{resource_dir}/{filename}.md
    """
    parts = filepath.parts
    if len(parts) >= 2 and parts[-2] != 'crawl_markdown':
        return parts[-2]  # Parent directory is resource name
    return None


def should_deny_by_domain_rules(url: str, resource_name: str, rules: dict) -> bool:
    """Check if URL matches domain-specific deny rules."""
    domain_rules = rules.get('domain_rules', {})
    
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    
    if domain not in domain_rules:
        return False
    
    rule = domain_rules[domain]
    
    # Check allow_url_regex first (whitelist)
    allow_patterns = rule.get('allow_url_regex', [])
    if allow_patterns:
        allowed = False
        for pattern in allow_patterns:
            try:
                if re.search(pattern, url, re.IGNORECASE):
                    allowed = True
                    break
            except re.error:
                pass
        if not allowed:
            return True  # Domain has allow list, but URL not on it
    
    # Check deny patterns
    deny_patterns = rule.get('deny_url_regex', [])
    for pattern in deny_patterns:
        try:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        except re.error:
            pass
    
    return False


def should_deny_by_site_rules(url: str, resource_name: str, rules: dict) -> bool:
    """Check if URL matches site-specific deny rules."""
    site_rules = rules.get('site_rules', {})
    
    if resource_name not in site_rules:
        return False
    
    rule = site_rules[resource_name]
    
    # Check allow_url_regex first (whitelist)
    allow_patterns = rule.get('allow_url_regex', [])
    if allow_patterns:
        allowed = False
        for pattern in allow_patterns:
            try:
                if re.search(pattern, url, re.IGNORECASE):
                    allowed = True
                    break
            except re.error:
                pass
        if not allowed:
            return True  # Site has allow list, but URL not on it
    
    # Check deny patterns
    deny_patterns = rule.get('deny_url_regex', [])
    for pattern in deny_patterns:
        try:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        except re.error:
            pass
    
    return False


def get_url_from_database(markdown_path: str) -> str | None:
    """Look up URL from database using markdown path."""
    try:
        conn = sqlite3.connect(CRAWL_STATE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM pages WHERE markdown_path = ?", (markdown_path,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        pass
    return None


def extract_url_from_markdown(filepath: Path) -> str | None:
    """Extract source URL from markdown frontmatter or database."""
    # Try database first
    relative_path = str(filepath.relative_to(PROJECT_ROOT))
    url = get_url_from_database(relative_path)
    if url:
        return url
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Look for source_url in frontmatter (YAML)
        # Format: source_url: "https://..."
        match = re.search(r'source_url:\s*["\']?([^\n"\']+)["\']?', content)
        if match:
            return match.group(1).strip()
        
        # Alternative: look in JSON metadata block
        match = re.search(r'"source_url":\s*"([^"]+)"', content)
        if match:
            return match.group(1)
    
    except Exception as e:
        pass
    
    return None


def should_delete_file(filepath: Path, rules: dict) -> tuple[bool, str]:
    """
    Determine if a markdown file should be deleted based on prefilter rules.
    Strategy:
      1. If filename matches a deny pattern (e.g., -metadata.md), DELETE
      2. If we have URL from database, check URL against all rules
      3. Otherwise, KEEP (files without URLs are likely unsynced content)
    
    Returns: (should_delete, reason)
    """
    
    filename = filepath.name
    
    # First: check if filename itself matches deny pattern
    # This catches metadata files, index files, etc.
    global_rules = rules.get('global', {})
    deny_patterns = global_rules.get('deny_url_regex', [])
    
    for pattern in deny_patterns:
        try:
            if re.search(pattern, filename):
                return True, f"filename_matches_{pattern[:20]}"
        except re.error:
            pass
    
    # Second: try to get URL from database
    resource_name = get_resource_name_from_path(filepath)
    url = get_url_from_database(str(filepath.relative_to(PROJECT_ROOT)))
    
    if not url:
        # No URL available, keep the file
        return False, "no_url_in_database"
    
    # Check global patterns
    if should_deny_by_global_pattern(url, rules):
        return True, "global_deny_pattern"
    
    if should_deny_by_query_param(url, rules):
        return True, "deny_query_param"
    
    # Check domain rules
    if should_deny_by_domain_rules(url, resource_name or "", rules):
        return True, "domain_deny_rule"
    
    # Check site rules
    if should_deny_by_site_rules(url, resource_name or "", rules):
        return True, "site_deny_rule"
    
    return False, "keep"


def analyze_cleanup(dry_run: bool = True) -> dict[str, Any]:
    """
    Analyze which files would be deleted.
    Returns stats dict.
    """
    rules = load_prefilter_rules()
    if not rules:
        print("[error] Could not load prefilter rules")
        return {}
    
    stats = {
        'total_files': 0,
        'to_delete': 0,
        'to_keep': 0,
        'deletions_by_reason': {},
        'files_to_delete': [],
        'total_images': 0,
        'images_to_delete': 0,
        'images_to_keep': 0,
        'image_files_to_delete': [],
        'protected_images_retained': 0,
        'protected_image_samples': [],
    }
    
    if not CRAWL_MARKDOWN_DIR.exists():
        print(f"[error] Crawl directory not found: {CRAWL_MARKDOWN_DIR}")
        return stats
    
    # Scan all markdown files
    for filepath in sorted(CRAWL_MARKDOWN_DIR.rglob('*.md')):
        stats['total_files'] += 1
        
        should_delete, reason = should_delete_file(filepath, rules)
        
        if should_delete:
            stats['to_delete'] += 1
            stats['deletions_by_reason'][reason] = stats['deletions_by_reason'].get(reason, 0) + 1
            stats['files_to_delete'].append({
                'path': str(filepath.relative_to(PROJECT_ROOT)),
                'reason': reason
            })
        else:
            stats['to_keep'] += 1

    image_stats = analyze_image_cleanup([item['path'] for item in stats['files_to_delete']])
    stats.update(image_stats)
    
    return stats


def execute_cleanup(yes_delete: bool = False) -> dict[str, Any]:
    """
    Execute cleanup: delete outdated files.
    Args:
        yes_delete: If True, actually delete files. If False, dry-run.
    
    Returns: stats dict
    """
    stats = analyze_cleanup(dry_run=not yes_delete)
    
    print(f"\n{'='*70}")
    print(f"Cleanup Analysis Report")
    print(f"{'='*70}")

    # T504: report protected lesson/quiz image count.
    protected_images = collect_protected_image_paths()
    print(f"Protected lesson/quiz images: {len(protected_images)}")

    print(f"Total markdown files: {stats['total_files']}")
    print(f"Files to delete: {stats['to_delete']} ({100*stats['to_delete']/max(stats['total_files'], 1):.1f}%)")
    print(f"Files to keep: {stats['to_keep']}")
    print(f"Total images: {stats['total_images']}")
    print(f"Images to delete: {stats['images_to_delete']} ({100*stats['images_to_delete']/max(stats['total_images'], 1):.1f}%)")
    print(f"Protected images retained: {stats['protected_images_retained']}")
    print(f"\nDeletions by reason:")
    for reason, count in sorted(stats['deletions_by_reason'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {reason}: {count}")
    
    if stats['to_delete'] == 0:
        print("\nNo files to delete.")
        return stats
    
    print(f"\nTop 10 files to delete:")
    for item in stats['files_to_delete'][:10]:
        print(f"  - {item['path']} ({item['reason']})")
    if stats['image_files_to_delete']:
        print(f"\nTop 10 images to delete:")
        for item in stats['image_files_to_delete'][:10]:
            print(f"  - {item['path']} ({item['reason']})")
    if stats['protected_image_samples']:
        print(f"\nProtected images retained (sample):")
        for path in stats['protected_image_samples'][:10]:
            print(f"  - {path}")
    
    if not yes_delete:
        total_delete_count = stats['to_delete'] + stats['images_to_delete']
        print(f"\n[DRY RUN] Would delete {stats['to_delete']} markdown files and {stats['images_to_delete']} images ({total_delete_count} total).")
        print("Run with --yes-delete to actually delete.")
        return stats
    
    # Actually delete
    print(f"\n[EXECUTING] Deleting {stats['to_delete']} markdown files and {stats['images_to_delete']} images...")
    deleted_count = 0
    for item in stats['files_to_delete']:
        filepath = PROJECT_ROOT / item['path']
        try:
            filepath.unlink()
            deleted_count += 1
            if deleted_count % 100 == 0:
                print(f"  Deleted {deleted_count} entries...")
        except Exception as e:
            print(f"  [warn] Failed to delete {item['path']}: {e}")

    protected_set = collect_protected_image_paths()
    for item in stats['image_files_to_delete']:
        filepath = PROJECT_ROOT / item['path']
        try:
            if is_image_protected(filepath, protected_set):
                print(f"  [keep] protected image retained: {item['path']}")
                continue
            filepath.unlink()
            deleted_count += 1
            if deleted_count % 100 == 0:
                print(f"  Deleted {deleted_count} entries...")
        except Exception as e:
            print(f"  [warn] Failed to delete {item['path']}: {e}")
    
    print(f"\n[COMPLETE] Deleted {deleted_count} entries.")
    stats['deleted_count'] = deleted_count
    
    return stats


def print_sample_deletions(stats: dict, num_samples: int = 20):
    """Print sample of files that will be deleted."""
    if not stats.get('files_to_delete'):
        return
    
    print(f"\nSample of files to be deleted ({min(num_samples, len(stats['files_to_delete']))} of {len(stats['files_to_delete'])}):")
    for item in stats['files_to_delete'][:num_samples]:
        print(f"  [{item['reason']}] {item['path']}")


if __name__ == '__main__':
    import sys
    
    yes_delete = '--yes-delete' in sys.argv
    
    stats = execute_cleanup(yes_delete=yes_delete)
    print_sample_deletions(stats)
