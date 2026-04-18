#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from html import escape as html_escape
import json
import shutil
from pathlib import Path

from serve_site import DistillerySiteHandler, configure_handler_class


IMAGE_SUFFIXES = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


class StaticRenderer(DistillerySiteHandler):
    def __init__(self) -> None:
        pass

    def send_html(self, text: str) -> None:
        self._captured_output = text

    def send_text(self, text: str) -> None:
        self._captured_output = text

    def send_json(self, payload: object) -> None:
        self._captured_output = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        detail = message or explain or "Unknown error"
        raise RuntimeError(f"{code}: {detail}")


def capture(renderer: StaticRenderer, callback) -> str:
    renderer._captured_output = None
    callback()
    output = getattr(renderer, "_captured_output", None)
    if output is None:
        raise RuntimeError("Renderer did not produce output")
    return output


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_path_for_route(route: str) -> Path:
    if route == "/":
        return Path("index.html")
    return Path(route.lstrip("/")) / "index.html"


def copy_tree_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def copy_google_verification_files(project_root: Path, output_root: Path) -> None:
    for candidate in sorted(project_root.glob("google*.html")):
        if candidate.is_file():
            shutil.copy2(candidate, output_root / candidate.name)


def write_ads_txt(project_root: Path, output_root: Path, adsense_client_id: str) -> bool:
    # Prefer an explicit project-level ads.txt file when present.
    project_ads = project_root / "ads.txt"
    if project_ads.exists() and project_ads.is_file():
        shutil.copy2(project_ads, output_root / "ads.txt")
        return True

    client = (adsense_client_id or "").strip()
    if not client.startswith("ca-pub-"):
        return False

    publisher = client[len("ca-") :]
    write_text(output_root / "ads.txt", f"google.com, {publisher}, DIRECT, f08c47fec0942fa0\n")
    return True


def _build_public_url(site_url: str, base_path: str, route: str) -> str:
    clean_site = site_url.strip().rstrip("/")
    clean_base = (base_path if base_path.startswith("/") else f"/{base_path}").rstrip("/")
    clean_route = route if route.startswith("/") else f"/{route}"
    route_with_base = f"{clean_base}{clean_route}" if clean_base else clean_route
    return f"{clean_site}{route_with_base}"


def _write_sitemap_and_robots(output_root: Path, indexable_routes: set[str], base_path: str, site_url: str) -> None:
    robots_lines = [
        "User-agent: *",
        "Allow: /",
    ]

    if site_url.strip():
        sitemap_url = _build_public_url(site_url, base_path, "/sitemap.xml")
        urls = sorted(_build_public_url(site_url, base_path, route) for route in indexable_routes)
        lastmod = date.today().isoformat()
        items = "\n".join(
            f"  <url><loc>{html_escape(url)}</loc><lastmod>{lastmod}</lastmod></url>" for url in urls
        )
        sitemap_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
            f"{items}\n"
            "</urlset>\n"
        )
        write_text(output_root / "sitemap.xml", sitemap_xml)
        robots_lines.append(f"Sitemap: {sitemap_url}")

    write_text(output_root / "robots.txt", "\n".join(robots_lines) + "\n")


def build_static_site(
    project_root: Path,
    db_path: Path,
    web_data_root: Path,
    output_root: Path,
    base_path: str,
    site_url: str,
) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    configure_handler_class(
        handler_class=StaticRenderer,
        project_root=project_root,
        db_path=db_path,
        web_data_root=web_data_root,
        static_mode=True,
        base_path=base_path,
        public_site_url=site_url,
    )
    renderer = StaticRenderer()
    indexable_routes: set[str] = set()

    def track_indexable(route: str) -> None:
        if route in {"/quizzes/data", "/glossary/data", "/flavors/data"}:
            return
        if route.endswith("/raw"):
            return
        indexable_routes.add(route)

    routes: list[tuple[str, callable]] = [
        ("/", renderer.render_home),
        ("/whisky-lessons", lambda: renderer.render_whisky_course(current_path="/whisky-lessons")),
        ("/the-whisky-course", lambda: renderer.render_whisky_course(current_path="/the-whisky-course")),
        ("/quizzes", renderer.render_quizzes),
        ("/resources", renderer.render_resources),
        ("/database", lambda: renderer.render_database("")),
        ("/glossary", renderer.render_glossary),
        ("/flavors", renderer.render_flavors),
        ("/privacy", renderer.render_privacy),
        ("/quizzes/data", renderer.render_quizzes_data),
        ("/glossary/data", renderer.render_glossary_data),
        ("/flavors/data", renderer.render_flavors_data),
    ]
    routes.extend((page_path, lambda route=page_path: renderer.render_phase_document(route)) for page_path in renderer.phase_pages)
    routes.extend(
        (f"{page_path}/raw", lambda route=page_path: renderer.render_phase_raw(f"{route}/raw"))
        for page_path in renderer.phase_pages
    )

    for route, callback in routes:
        write_text(output_root / output_path_for_route(route), capture(renderer, callback))
        track_indexable(route)

    dataset = renderer.load_exported_dataset()
    if not dataset:
        raise RuntimeError("Exported distillery dataset is missing. Run scripts/export_json_dataset.py first.")

    distilleries_payload, _taxonomy_payload = dataset
    distilleries = distilleries_payload.get("distilleries", [])
    if not isinstance(distilleries, list):
        raise RuntimeError("Invalid distillery dataset payload")

    for item in distilleries:
        if not isinstance(item, dict):
            continue
        distillery_id = str(item.get("id") or "").strip()
        slug = str(item.get("slug") or "").strip()
        if distillery_id:
            write_text(
                output_root / output_path_for_route(f"/distillery/{distillery_id}"),
                capture(renderer, lambda distillery_key=distillery_id: renderer.render_distillery(distillery_key)),
            )
        if slug and slug != distillery_id:
            write_text(
                output_root / output_path_for_route(f"/distillery/{slug}"),
                capture(renderer, lambda distillery_key=slug: renderer.render_distillery(distillery_key)),
            )
            track_indexable(f"/distillery/{slug}")
        elif distillery_id:
            track_indexable(f"/distillery/{distillery_id}")

    data_output_root = output_root / "data-web"
    copy_tree_if_exists(web_data_root, data_output_root)
    write_text(data_output_root / "quizzes.json", capture(renderer, renderer.render_quizzes_data))
    write_text(data_output_root / "glossary.json", capture(renderer, renderer.render_glossary_data))
    write_text(data_output_root / "flavors.json", capture(renderer, renderer.render_flavors_data))

    # Generate products listing and detail pages.
    write_text(output_root / output_path_for_route("/products"), capture(renderer, renderer.render_products))
    track_indexable("/products")
    products_for_categories = [
        p for p in renderer._load_products(include_archive=True) if renderer._product_has_usable_image(p)
    ]
    category_names = sorted({str(p.get("category") or "Other") for p in products_for_categories})
    for category_name in category_names:
        category_slug = renderer._category_slug(category_name)
        category_route = f"/products/category/{category_slug}"
        write_text(
            output_root / output_path_for_route(category_route),
            capture(renderer, lambda slug=category_slug: renderer.render_products(category_slug=slug)),
        )
        track_indexable(category_route)

    for product in renderer._load_products(include_archive=True):
        slug = str(product.get("slug") or "").strip()
        if slug and renderer._product_has_usable_image(product):
            try:
                detail_html = capture(renderer, lambda s=slug: renderer.render_product_detail(s))
            except RuntimeError as exc:
                # Keep the static build resilient when product data lists a stale slug.
                print(f"Skipping product detail page for '{slug}': {exc}")
                continue
            write_text(output_root / "products" / slug / "index.html", detail_html)
            track_indexable(f"/products/{slug}")

    for page_path in renderer.phase_pages:
        write_text(
            data_output_root / renderer.phase_data_relpath(page_path),
            capture(renderer, lambda route=page_path: renderer.render_phase_raw(f"{route}/raw")),
        )

    web_root = project_root / "web"
    copy_tree_if_exists(web_root, output_root / "web")
    shutil.copy2(web_root / "manifest.webmanifest", output_root / "manifest.webmanifest")
    shutil.copy2(web_root / "sw.js", output_root / "sw.js")

    # Generate resource detail pages and copy crawl markdown as raw pages.
    resources_json_path = web_data_root / "resources.json"
    if resources_json_path.exists():
        resources_payload = json.loads(resources_json_path.read_text(encoding="utf-8"))
        resource_slugs = sorted(
            {
                str(resource.get("slug") or "").strip()
                for resource in resources_payload.get("resources", [])
                if isinstance(resource, dict) and str(resource.get("slug") or "").strip()
            }
        )
        for slug in resource_slugs:
            write_text(
                output_root / "resources" / slug / "index.html",
                capture(renderer, lambda s=slug: renderer.render_resource_detail(s)),
            )
            track_indexable(f"/resources/{slug}")

    crawl_markdown_root = project_root / "data" / "crawl_markdown"
    if crawl_markdown_root.exists():
        for crawl_dir in sorted(crawl_markdown_root.iterdir()):
            if not crawl_dir.is_dir() or not crawl_dir.name.startswith("resource-"):
                continue
            slug = crawl_dir.name[len("resource-"):]
            pages_out = output_root / "resources" / slug / "pages"
            pages_out.mkdir(parents=True, exist_ok=True)
            for md_file in sorted(crawl_dir.iterdir()):
                if md_file.is_file() and md_file.suffix == ".md":
                    shutil.copy2(md_file, pages_out / md_file.name)

    media_root = output_root / "media" / "data"
    media_root.mkdir(parents=True, exist_ok=True)
    copy_tree_if_exists(project_root / "data" / "images", media_root / "images")
    copy_tree_if_exists(project_root / "data" / "products" / "images", media_root / "products" / "images")
    for asset in (project_root / "data").iterdir():
        if asset.is_file() and asset.suffix.lower() in IMAGE_SUFFIXES:
            shutil.copy2(asset, media_root / asset.name)

    copy_google_verification_files(project_root=project_root, output_root=output_root)
    write_ads_txt(project_root=project_root, output_root=output_root, adsense_client_id=renderer.adsense_client_id)
    _write_sitemap_and_robots(output_root=output_root, indexable_routes=indexable_routes, base_path=base_path, site_url=site_url)

    write_text(output_root / ".nojekyll", "")
    shutil.copy2(output_root / "index.html", output_root / "404.html")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a GitHub Pages-compatible static export of the whisky app.")
    parser.add_argument("--db", default="data/distilleries.db", help="Path to the SQLite database.")
    parser.add_argument("--web-data", default="data/web", help="Path to the exported JSON dataset directory.")
    parser.add_argument("--output", default="build/github-pages", help="Directory for the generated static site.")
    parser.add_argument("--base-path", default="/", help="Base path to use for generated links, for example /whisky.")
    parser.add_argument(
        "--site-url",
        default="",
        help="Absolute public site URL used for canonical metadata and sitemap (for example https://example.com).",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output_root = (project_root / args.output).resolve()

    build_static_site(
        project_root=project_root,
        db_path=(project_root / args.db).resolve(),
        web_data_root=(project_root / args.web_data).resolve(),
        output_root=output_root,
        base_path=args.base_path,
        site_url=args.site_url,
    )

    print(json.dumps({"output": str(output_root), "basePath": args.base_path, "siteUrl": args.site_url}, indent=2))


if __name__ == "__main__":
    main()