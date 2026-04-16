#!/usr/bin/env python3
"""
Enhancement module for crawl_whisky_sites.py
Extracts images from crawled content, matches them to products, downloads images,
and creates/updates product markdown files with comprehensive metadata.
"""

import json
import re
import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import hashlib
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PRODUCTS_DIR = DATA_DIR / "products"
PRODUCTS_IMAGES_DIR = PRODUCTS_DIR / "images"


def setup_directories():
    """Ensure required directories exist."""
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    PRODUCTS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def extract_image_urls_from_html(html_content: str, base_url: str) -> list[dict[str, str]]:
    """
    Extract image URLs and metadata from HTML content.
    
    Returns list of dicts with keys: url, alt_text, title, context_text
    """
    images = []
    
    # Find <img> tags
    img_pattern = r'<img\s+[^>]*?(?:src|data-src)\s*=\s*["\']([^"\']+)["\'][^>]*?(?:alt\s*=\s*["\']([^"\']*)["\'])?[^>]*?>'
    
    for match in re.finditer(img_pattern, html_content, re.IGNORECASE):
        url = match.group(1)
        alt_text = match.group(2) or ""
        
        # Resolve relative URLs
        if url.startswith('http://') or url.startswith('https://'):
            full_url = url
        elif url.startswith('//'):
            full_url = f"https:{url}"
        elif url.startswith('/'):
            parsed_base = urlparse(base_url)
            full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{url}"
        else:
            full_url = urljoin(base_url, url)
        
        # Skip very small images (likely icons)
        if 'icon' in url.lower() or 'logo' in url.lower() or 'favicon' in url.lower():
            continue
        
        # Skip tracking pixels
        if re.search(r'[\?&](pixel|tracker|utm)', url, re.IGNORECASE):
            continue
        
        images.append({
            'url': full_url,
            'alt_text': alt_text.strip(),
            'title': "",
            'context': ""
        })
    
    # Also look for picture/source tags
    picture_pattern = r'<picture[^>]*>.*?<source[^>]*?srcset\s*=\s*["\']([^"\']+)["\']'
    for match in re.finditer(picture_pattern, html_content, re.IGNORECASE | re.DOTALL):
        url = match.group(1).split()[0]  # srcset can have multiple URLs
        if url.startswith(('http://', 'https://', '//', '/')):
            full_url = urljoin(base_url, url) if not url.startswith('http') else url
            images.append({
                'url': full_url,
                'alt_text': "",
                'title': "",
                'context': ""
            })
    
    # Deduplicate by URL
    seen = set()
    unique_images = []
    for img in images:
        if img['url'] not in seen:
            seen.add(img['url'])
            unique_images.append(img)
    
    return unique_images


def match_products_to_images(products: list[dict[str, Any]], 
                            images: list[dict[str, str]], 
                            content_text: str) -> list[dict[str, Any]]:
    """
    Match products to images based on heuristics.
    Returns products with matched image URLs.
    """
    matched_products = []
    
    for product in products:
        product_name = (product.get('name') or '').lower()
        product_copy = dict(product)
        product_copy['image_url'] = None
        
        if not product_name:
            matched_products.append(product_copy)
            continue
        
        # Try to find image matching product name
        best_image = None
        best_score = 0
        
        for image in images:
            score = 0
            
            # Check if product name appears near product links
            if product.get('purchase_links'):
                for link in product['purchase_links'][:1]:  # Check first link
                    # Simple heuristic: same domain likely = same product
                    try:
                        if urlparse(image['url']).netloc == urlparse(link).netloc:
                            score += 3
                    except:
                        pass
            
            # Check image alt text for product keywords
            alt_text = (image.get('alt_text') or '').lower()
            if product_name in alt_text:
                score += 2
            elif any(word in alt_text for word in product_name.split()[:2]):
                score += 1
            
            # Check URL for product name keywords
            url_text = image['url'].lower()
            if any(word in url_text for word in product_name.split()[:2]):
                score += 1
            
            # Prefer larger images (simple heuristic based on URL patterns)
            if any(size in url_text for size in ['1920', '1200', '1024', 'large', 'xl', 'big']):
                score += 0.5
            
            if score > best_score:
                best_score = score
                best_image = image['url']
        
        if best_image:
            product_copy['image_url'] = best_image
        
        matched_products.append(product_copy)
    
    return matched_products


def download_image(url: str, timeout: int = 60) -> bytes | None:
    """Download image from URL, return bytes or None on failure."""
    try:
        req = Request(url, headers={'User-Agent': 'WhiskyCrawler/1.0'})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        print(f"  [warn] Failed to download image {url}: {e}")
        return None


def get_image_extension(content: bytes) -> str | None:
    """Detect image type from content bytes."""
    if content.startswith(b'\xFF\xD8\xFF'):
        return 'jpg'
    elif content.startswith(b'\x89PNG'):
        return 'png'
    elif content.startswith(b'GIF8'):
        return 'gif'
    elif content.startswith(b'RIFF') and b'WEBP' in content[:20]:
        return 'webp'
    return None


def save_product_image(image_bytes: bytes, product_name: str, distillery: str = "") -> str | None:
    """
    Save product image and return relative path.
    Filename: {slugified_distillery}_{slugified_product}.{ext}
    """
    if not image_bytes:
        return None
    
    ext = get_image_extension(image_bytes)
    if not ext:
        print(f"  [warn] Could not detect image format for {product_name}")
        return None
    
    # Create slug from product name and distillery
    def slugify(text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.strip('-')
    
    distillery_slug = slugify(distillery) if distillery else "unknown"
    product_slug = slugify(product_name)
    
    filename = f"{distillery_slug}_{product_slug}.{ext}"
    filepath = PRODUCTS_IMAGES_DIR / filename
    
    # Check if file already exists with same content
    if filepath.exists():
        with open(filepath, 'rb') as f:
            if f.read() == image_bytes:
                # Same file, no need to redownload
                return str(filepath.relative_to(PROJECT_ROOT))
    
    try:
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        print(f"  [save] Saved product image: {filename}")
        return str(filepath.relative_to(PROJECT_ROOT))
    except Exception as e:
        print(f"  [error] Failed to save image {filename}: {e}")
        return None


def generate_product_markdown(product: dict[str, Any], 
                             distillery: str = "",
                             image_path: str | None = None) -> str:
    """Generate markdown content for a product."""
    
    product_name = product.get('name', 'Unknown Product')
    
    # Extract metadata
    facts = product.get('facts', [])
    price_mentions = product.get('price_mentions', [])
    purchase_links = product.get('purchase_links', [])
    source_url = product.get('source_url', '')
    confidence = product.get('confidence', 'medium')
    
    # Try to extract ABV, category from facts
    abv = ""
    category = ""
    for fact in facts:
        if 'abv' in fact.lower() or '%' in fact:
            abv_match = re.search(r'(\d+(?:\.\d+)?)\s*%', fact)
            if abv_match and not abv:
                abv = abv_match.group(1)
        if 'category' in fact.lower() or 'type' in fact.lower():
            for cat in ['whisky', 'bourbon', 'rum', 'gin', 'vodka', 'brandy', 'liqueur', 'spiritswhiskey']:
                if cat in fact.lower():
                    category = cat.title()
                    break
    
    # Try to extract price
    price = ""
    for mention in price_mentions:
        if '$' in mention or '€' in mention or '£' in mention:
            price = mention
            break
    
    # Build frontmatter
    frontmatter = {
        'title': product_name,
        'slug': re.sub(r'[^\w-]', '', product_name.lower().replace(' ', '-')),
        'abv': abv,
        'price': price,
        'category': category,
        'distillery': distillery,
        'source_url': source_url,
        'image': image_path or "",
        'facts': facts[:5],  # Top 5 facts
        'purchase_links': purchase_links[:3],  # Top 3 links
        'confidence': confidence,
        'captured_at': datetime.utcnow().isoformat() + 'Z'
    }
    
    # Format frontmatter as YAML
    lines = ['---']
    for key, value in frontmatter.items():
        if isinstance(value, list):
            if value:
                lines.append(f'{key}:')
                for item in value:
                    lines.append(f'  - {json.dumps(item)}')
            else:
                lines.append(f'{key}: []')
        elif isinstance(value, str):
            lines.append(f'{key}: {json.dumps(value)}')
        elif value:
            lines.append(f'{key}: {value}')
    lines.append('---')
    
    return '\n'.join(lines) + '\n\n'


def create_or_update_product_file(product: dict[str, Any], 
                                  distillery: str = "",
                                  image_path: str | None = None) -> str | None:
    """Create or update product markdown file, return filepath."""
    
    product_name = product.get('name', '')
    if not product_name:
        return None
    
    # Create filename
    slug = re.sub(r'[^\w-]', '', product_name.lower().replace(' ', '-'))
    filename = f"{slug}.md"
    filepath = PRODUCTS_DIR / filename
    
    # Generate content
    content = generate_product_markdown(product, distillery, image_path)
    
    # Check if file exists and has been modified
    if filepath.exists():
        with open(filepath, 'r') as f:
            existing = f.read()
        if existing == content:
            # No changes
            return str(filepath.relative_to(PROJECT_ROOT))
    
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  [product] Created/updated: {filename}")
        return str(filepath.relative_to(PROJECT_ROOT))
    except Exception as e:
        print(f"  [error] Failed to create product file {filename}: {e}")
        return None


def sync_product_images_from_crawl(page_data: dict[str, Any]) -> dict[str, Any]:
    """
    Main orchestration function called from crawl pipeline.
    Processes page data: extracts images, matches to products, downloads & saves.
    
    Args:
        page_data: Page crawl data with html_content, products, distillery, source_url
    
    Returns:
        Updated page_data with product image data
    """
    
    setup_directories()
    
    html_content = page_data.get('html_content', '')
    products = page_data.get('products', [])
    distillery = page_data.get('distillery', '')
    source_url = page_data.get('source_url', '')
    
    if not html_content or not products:
        return page_data
    
    # Extract images from HTML
    images = extract_image_urls_from_html(html_content, source_url)
    if not images:
        return page_data
    
    # Match products to images
    matched_products = match_products_to_images(products, images, html_content)
    
    # Process matched products
    product_updates = []
    for product in matched_products:
        image_url = product.get('image_url')
        if not image_url:
            product_updates.append(product)
            continue
        
        # Download image
        image_bytes = download_image(image_url)
        if not image_bytes:
            product_updates.append(product)
            continue
        
        # Save image
        image_path = save_product_image(image_bytes, product.get('name', ''), distillery)
        if image_path:
            product['image_path'] = image_path
            # Create/update product markdown file
            create_or_update_product_file(product, distillery, image_path)
        
        product_updates.append(product)
    
    page_data['products'] = product_updates
    page_data['image_sync_completed'] = True
    
    return page_data


if __name__ == '__main__':
    print("Product image enhancement module loaded.")
    print(f"Products directory: {PRODUCTS_DIR}")
    print(f"Images directory: {PRODUCTS_IMAGES_DIR}")
