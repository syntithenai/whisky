#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def build_static_site(
    project_root: Path,
    db_path: Path,
    web_data_root: Path,
    output_root: Path,
    base_path: str,
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
    )
    renderer = StaticRenderer()

    routes: list[tuple[str, callable]] = [
        ("/", renderer.render_home),
        ("/whisky-lessons", lambda: renderer.render_whisky_course(current_path="/whisky-lessons")),
        ("/the-whisky-course", lambda: renderer.render_whisky_course(current_path="/the-whisky-course")),
        ("/quizzes", renderer.render_quizzes),
        ("/resources", renderer.render_resources),
        ("/database", lambda: renderer.render_database("")),
        ("/glossary", renderer.render_glossary),
        ("/privacy", renderer.render_privacy),
        ("/quizzes/data", renderer.render_quizzes_data),
        ("/glossary/data", renderer.render_glossary_data),
    ]
    routes.extend((page_path, lambda route=page_path: renderer.render_phase_document(route)) for page_path in renderer.phase_pages)
    routes.extend(
        (f"{page_path}/raw", lambda route=page_path: renderer.render_phase_raw(f"{route}/raw"))
        for page_path in renderer.phase_pages
    )

    for route, callback in routes:
        write_text(output_root / output_path_for_route(route), capture(renderer, callback))

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

    data_output_root = output_root / "data-web"
    copy_tree_if_exists(web_data_root, data_output_root)
    write_text(data_output_root / "quizzes.json", capture(renderer, renderer.render_quizzes_data))
    write_text(data_output_root / "glossary.json", capture(renderer, renderer.render_glossary_data))

    for page_path in renderer.phase_pages:
        write_text(
            data_output_root / renderer.phase_data_relpath(page_path),
            capture(renderer, lambda route=page_path: renderer.render_phase_raw(f"{route}/raw")),
        )

    web_root = project_root / "web"
    copy_tree_if_exists(web_root, output_root / "web")
    shutil.copy2(web_root / "manifest.webmanifest", output_root / "manifest.webmanifest")
    shutil.copy2(web_root / "sw.js", output_root / "sw.js")

    media_root = output_root / "media" / "data"
    media_root.mkdir(parents=True, exist_ok=True)
    copy_tree_if_exists(project_root / "data" / "images", media_root / "images")
    for asset in (project_root / "data").iterdir():
        if asset.is_file() and asset.suffix.lower() in IMAGE_SUFFIXES:
            shutil.copy2(asset, media_root / asset.name)

    write_text(output_root / ".nojekyll", "")
    shutil.copy2(output_root / "index.html", output_root / "404.html")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a GitHub Pages-compatible static export of the whisky app.")
    parser.add_argument("--db", default="data/distilleries.db", help="Path to the SQLite database.")
    parser.add_argument("--web-data", default="data/web", help="Path to the exported JSON dataset directory.")
    parser.add_argument("--output", default="build/github-pages", help="Directory for the generated static site.")
    parser.add_argument("--base-path", default="/", help="Base path to use for generated links, for example /whisky.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output_root = (project_root / args.output).resolve()

    build_static_site(
        project_root=project_root,
        db_path=(project_root / args.db).resolve(),
        web_data_root=(project_root / args.web_data).resolve(),
        output_root=output_root,
        base_path=args.base_path,
    )

    print(json.dumps({"output": str(output_root), "basePath": args.base_path}, indent=2))


if __name__ == "__main__":
    main()