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
PREFILTER_RULES_PATH = DATA_DIR / "resource_prefilter_rules.json"
CRAWL_STATE_DB = DATA_DIR / "site_crawl_state.db"


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
        'files_to_delete': []
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
    print(f"Total markdown files: {stats['total_files']}")
    print(f"Files to delete: {stats['to_delete']} ({100*stats['to_delete']/max(stats['total_files'], 1):.1f}%)")
    print(f"Files to keep: {stats['to_keep']}")
    print(f"\nDeletions by reason:")
    for reason, count in sorted(stats['deletions_by_reason'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {reason}: {count}")
    
    if stats['to_delete'] == 0:
        print("\nNo files to delete.")
        return stats
    
    print(f"\nTop 10 files to delete:")
    for item in stats['files_to_delete'][:10]:
        print(f"  - {item['path']} ({item['reason']})")
    
    if not yes_delete:
        print(f"\n[DRY RUN] Would delete {stats['to_delete']} files.")
        print("Run with --yes-delete to actually delete.")
        return stats
    
    # Actually delete
    print(f"\n[EXECUTING] Deleting {stats['to_delete']} files...")
    deleted_count = 0
    for item in stats['files_to_delete']:
        filepath = PROJECT_ROOT / item['path']
        try:
            filepath.unlink()
            deleted_count += 1
            if deleted_count % 100 == 0:
                print(f"  Deleted {deleted_count}...")
        except Exception as e:
            print(f"  [warn] Failed to delete {item['path']}: {e}")
    
    print(f"\n[COMPLETE] Deleted {deleted_count} files.")
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
