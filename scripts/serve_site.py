#!/usr/bin/env python3
from __future__ import annotations

import argparse
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mimetypes
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, unquote, urlparse


class DistillerySiteHandler(BaseHTTPRequestHandler):
    db_path: Path
    project_root: Path
    web_data_root: Path
    static_mode: bool
    phase1_markdown_path: Path
    quiz_markdown_paths: list[Path]
    phase_pages: dict[str, dict[str, str]]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/manifest.webmanifest":
            self.serve_file(self.project_root / "web" / "manifest.webmanifest", "application/manifest+json")
            return

        if parsed.path == "/sw.js":
            self.serve_file(self.project_root / "web" / "sw.js", "application/javascript; charset=utf-8")
            return

        if parsed.path.startswith("/web/"):
            rel = parsed.path[len("/web/") :]
            self.serve_file(self.project_root / "web" / rel)
            return

        if parsed.path.startswith("/data-web/"):
            rel = parsed.path[len("/data-web/") :]
            self.serve_file(self.web_data_root / rel)
            return

        if parsed.path.startswith("/media/"):
            self.serve_media(parsed.path)
            return

        if parsed.path.endswith("/raw") and parsed.path[:-4] in self.phase_pages:
            self.render_phase_raw(parsed.path)
            return

        if parsed.path == "/quizzes":
            self.render_quizzes()
            return

        if parsed.path == "/quizzes/data":
            self.render_quizzes_data()
            return

        if parsed.path == "/":
            self.render_home()
            return

        if parsed.path == "/whisky-lessons":
          self.render_whisky_course(current_path="/whisky-lessons")
          return

        if parsed.path == "/the-whisky-course":
          self.render_whisky_course(current_path="/the-whisky-course")
          return

        if parsed.path in self.phase_pages:
            self.render_phase_document(parsed.path)
            return

        if parsed.path == "/database":
            self.render_database(parsed.query)
            return

        if parsed.path.startswith("/distillery/"):
            distillery_id = parsed.path.split("/")[-1]
            self.render_distillery(distillery_id)
            return

        self.send_error(404, "Not found")

    def db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def serve_file(self, file_path: Path, forced_content_type: str | None = None) -> None:
      if not file_path.exists() or not file_path.is_file():
        self.send_error(404, "File not found")
        return

      mime, _ = mimetypes.guess_type(str(file_path))
      payload = file_path.read_bytes()
      self.send_response(200)
      self.send_header("Content-Type", forced_content_type or mime or "application/octet-stream")
      self.send_header("Content-Length", str(len(payload)))
      self.end_headers()
      self.wfile.write(payload)

    def load_exported_dataset(self) -> tuple[dict[str, object], dict[str, object]] | None:
      distilleries_path = self.web_data_root / "distilleries.json"
      taxonomy_path = self.web_data_root / "taxonomy.json"
      if not distilleries_path.exists() or not taxonomy_path.exists():
        return None

      try:
        distilleries_payload = json.loads(distilleries_path.read_text(encoding="utf-8"))
        taxonomy_payload = json.loads(taxonomy_path.read_text(encoding="utf-8"))
      except (OSError, json.JSONDecodeError):
        return None

      if not isinstance(distilleries_payload, dict) or not isinstance(taxonomy_payload, dict):
        return None

      return distilleries_payload, taxonomy_payload

    def send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, payload_obj: object) -> None:
      payload = json.dumps(payload_obj, ensure_ascii=True).encode("utf-8")
      self.send_response(200)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(payload)))
      self.end_headers()
      self.wfile.write(payload)

    def _normalize_external_url(self, url: str) -> str:
      parsed = urlparse(url.strip())
      if parsed.scheme.lower() not in {"http", "https"}:
        return ""

      host = parsed.netloc.lower()
      if host.startswith("www."):
        host = host[4:]

      path = parsed.path or ""
      if path != "/" and path.endswith("/"):
        path = path[:-1]
      if path == "/":
        path = ""

      return f"{host}{path}"

    def _distillery_official_site_map(self) -> dict[str, str]:
      link_map: dict[str, str] = {}
      with self.db() as conn:
        rows = conn.execute(
          "SELECT id, official_site FROM distilleries WHERE official_site LIKE 'http%'"
        ).fetchall()

      for row in rows:
        normalized = self._normalize_external_url(row["official_site"] or "")
        if normalized:
          link_map[normalized] = f"/distillery/{row['id']}"

      return link_map

    def _rewrite_distillery_markdown_links(self, text: str) -> str:
      link_map = self._distillery_official_site_map()
      if not link_map:
        return text

      def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        target = match.group(2)
        rewritten = link_map.get(self._normalize_external_url(target))
        if not rewritten:
          return match.group(0)
        return f"[{label}]({rewritten})"

      return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", replace_link, text)

    def nav_link(self, href: str, label: str, current_path: str) -> str:
        cls = "top-link active" if href == current_path else "top-link"
        return f"<a class=\"{cls}\" href=\"{href}\">{escape(label)}</a>"

    def nav_lessons_dropdown(self, current_path: str) -> str:
      phase_entries = sorted(
        self.phase_pages.items(),
        key=lambda item: int(item[0].split("-")[-1]),
      )
      phase_links = "".join(
        f"<a class=\"top-dropdown-item\" href=\"{escape(path)}\">{escape('Phase ' + path.split('-')[-1] + ': ' + page['title'])}</a>"
        for path, page in phase_entries
      )
      active = current_path in {"/whisky-lessons", "/the-whisky-course"} or current_path in self.phase_pages
      trigger_cls = "top-link active" if active else "top-link"
      return (
        "<div class=\"top-dropdown\">"
        f"<a class=\"{trigger_cls}\" href=\"/whisky-lessons\">Whisky Lessons</a>"
        "<div class=\"top-dropdown-menu\">"
        f"{phase_links}"
        "</div>"
        "</div>"
      )

    def page_shell(self, title: str, body: str, current_path: str) -> str:
        nav = "".join(
            [
                self.nav_link("/", "Home", current_path),
          self.nav_lessons_dropdown(current_path),
          self.nav_link("/quizzes", "Quizzes", current_path),
                self.nav_link("/database", "Distilleries", current_path),
            ]
        )

        return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #efe7d7;
      --panel: #fff9ef;
      --ink: #21170f;
      --muted: #685648;
      --accent: #8f3f22;
      --line: #d4bf9f;
      --top: #2f1d14;
      --topInk: #f8edda;
      --topHover: #4a2c1f;
      --indexBg: #f7ecd8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: Georgia, 'Times New Roman', serif;
      background:
        radial-gradient(1200px 500px at top left, #f8f1e4 0, var(--bg) 55%),
        linear-gradient(135deg, #ece2cf 0, #f2eadb 100%);
    }}
    a {{ color: #7f3318; }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 50;
      background: var(--top);
      color: var(--topInk);
      border-bottom: 1px solid #5a3a2b;
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.2);
    }}
    .topbar-inner {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 12px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .brand {{
      margin: 0;
      font-size: 16px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--topInk);
    }}
    .menu-toggle {{
      display: none;
      border: 1px solid #82604e;
      border-radius: 8px;
      background: transparent;
      color: var(--topInk);
      padding: 7px 10px;
      font-weight: 700;
      cursor: pointer;
    }}
    .top-links {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .top-link {{
      text-decoration: none;
      color: var(--topInk);
      background: transparent;
      border-radius: 999px;
      border: 1px solid transparent;
      padding: 7px 12px;
      font-size: 13px;
    }}
    .top-link:hover {{
      background: var(--topHover);
      border-color: #74513f;
    }}
    .top-link.active {{
      background: #f3dcc0;
      color: #341d13;
      border-color: #f3dcc0;
      font-weight: 700;
    }}
    .top-dropdown {{
      position: relative;
    }}
    .top-dropdown-menu {{
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      min-width: 320px;
      background: #f8edda;
      border: 1px solid #74513f;
      border-radius: 10px;
      box-shadow: 0 8px 18px rgba(0, 0, 0, 0.2);
      padding: 6px;
      display: none;
      z-index: 80;
    }}
    .top-dropdown:hover .top-dropdown-menu,
    .top-dropdown:focus-within .top-dropdown-menu {{
      display: block;
    }}
    .top-dropdown-item {{
      display: block;
      text-decoration: none;
      color: #3a2217;
      border-radius: 8px;
      padding: 7px 9px;
      font-size: 13px;
    }}
    .top-dropdown-item:hover {{
      background: #e8d5b8;
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
    }}
    .hero {{
      padding: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      margin-bottom: 18px;
    }}
    .grid {{ display: grid; gap: 16px; }}
    .grid-2 {{ grid-template-columns: 320px 1fr; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
    }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 14px;
    }}
    .card-link {{
      display: block;
      text-decoration: none;
      color: inherit;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      transition: transform 120ms ease, box-shadow 120ms ease;
    }}
    .card-link:hover {{
      transform: translateY(-2px);
      box-shadow: 0 10px 20px rgba(70, 42, 28, 0.12);
    }}
    .card-link h2 {{ margin: 0 0 8px 0; font-size: 18px; }}
    .results {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    .results th, .results td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 8px; vertical-align: top; }}
    input, select {{ width: 100%; padding: 8px; margin-bottom: 8px; border: 1px solid #c8b39a; border-radius: 8px; background: #fffdf8; }}
    button {{ border: 0; background: var(--accent); color: white; padding: 9px 12px; border-radius: 9px; cursor: pointer; }}
    .chips {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .chip {{ background: #efe3cf; border: 1px solid #cdb79f; border-radius: 999px; padding: 4px 10px; font-size: 12px; }}
    .filter-group {{ margin-top: 10px; margin-bottom: 12px; }}
    .filter-group h3 {{ margin: 0 0 8px 0; font-size: 14px; color: var(--muted); }}
    .chip-check {{ display: inline-flex; margin: 0 6px 6px 0; cursor: pointer; }}
    .chip-check input {{ display: none; }}
    .chip-check span {{ border: 1px solid #cdb79f; background: #f6ecdb; color: #5d4a37; border-radius: 999px; padding: 4px 10px; font-size: 12px; }}
    .chip-check input:checked + span {{ background: #a3572a; color: #fff; border-color: #a3572a; }}
    .images {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .images figure {{ margin: 0; background: white; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
    .images img {{ width: 100%; height: 180px; object-fit: cover; display: block; background: #f1ece3; }}
    .images figcaption {{ padding: 6px 8px; font-size: 12px; color: var(--muted); }}
    .phase1-layout {{
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 16px;
      align-items: start;
    }}
    .topic-index {{
      position: sticky;
      top: 78px;
      max-height: calc(100vh - 92px);
      overflow: auto;
      background: var(--indexBg);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
    }}
    .topic-index-header {{ display: flex; align-items: center; justify-content: space-between; margin: 0 0 10px 0; gap: 8px; }}
    .topic-index h2 {{ margin: 0; font-size: 15px; }}
    .quiz-nav-btn {{ font-size: 12px; font-weight: 600; color: #fff; background: #7a3e1e; border-radius: 999px; padding: 3px 10px; text-decoration: none; white-space: nowrap; flex-shrink: 0; }}
    .quiz-nav-btn:hover {{ background: #5a2815; }}
    .topic-index ul {{ list-style: none; margin: 0; padding: 0; }}
    .topic-index li {{ margin: 5px 0; }}
    .topic-index li.l3 {{ margin-left: 12px; }}
    .topic-index li.l4 {{ margin-left: 24px; }}
    .topic-index a {{ text-decoration: none; color: #5a2815; }}
    .topic-index a:hover {{ text-decoration: underline; }}
    .topic-index a.quiz-nav-btn {{ color: #fff; text-decoration: none; }}
    .topic-index a.quiz-nav-btn:hover {{ color: #fff; text-decoration: none; }}
    .markdown-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px;
      line-height: 1.6;
    }}
    .markdown-panel h1, .markdown-panel h2, .markdown-panel h3, .markdown-panel h4 {{
      scroll-margin-top: 82px;
      color: #2d180f;
    }}
    .markdown-panel h1 {{ font-size: 30px; margin-top: 0; }}
    .markdown-panel h2 {{ font-size: 24px; margin-top: 28px; }}
    .markdown-panel h3 {{ font-size: 20px; margin-top: 20px; }}
    .markdown-panel table {{ width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 14px; }}
    .markdown-panel th, .markdown-panel td {{ border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
    .markdown-panel code {{ background: #f1e7d4; padding: 1px 5px; border-radius: 4px; }}
    .markdown-panel pre {{ background: #2e211a; color: #f6e9d5; border-radius: 10px; overflow: auto; padding: 12px; }}
    .markdown-panel img {{ width: 100%; max-width: 720px; border-radius: 8px; border: 1px solid var(--line); }}
    .progress-track {{
      width: 100%;
      height: 10px;
      background: #e7d5bc;
      border-radius: 999px;
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      background: linear-gradient(90deg, #8f3f22 0, #c26935 100%);
      transition: width 150ms ease;
    }}
    .quiz-summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .quiz-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      display: block;
      text-decoration: none;
      color: inherit;
    }}
    a.quiz-card {{ cursor: pointer; }}
    a.quiz-card:hover {{ border-color: #8b6f47; }}
    .quiz-card {{ scroll-margin-top: 84px; }}
    #phaseQuizPanel {{ scroll-margin-top: 84px; }}
    .quiz-card h3 {{ margin: 0 0 10px 0; }}
    .quiz-meta {{ margin: 6px 0 10px 0; font-size: 13px; color: var(--muted); }}
    .quiz-question {{
      border-top: 1px solid #e4d3bc;
      margin-top: 10px;
      padding-top: 10px;
    }}
    .quiz-question p {{ margin: 0 0 8px 0; }}
    .quiz-option {{
      display: block;
      background: #f8efdf;
      border: 1px solid #d9c6aa;
      border-radius: 8px;
      padding: 8px;
      margin: 6px 0;
      cursor: pointer;
    }}
    .quiz-option input {{ margin-right: 8px; width: auto; }}
    .quiz-actions {{ margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
    .button-secondary {{
      border: 1px solid #ab8a6d;
      background: #f3e5cf;
      color: #4f2e20;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
    }}
    .course-jump {{
      max-width: 420px;
      margin-top: 10px;
    }}
    .course-phase {{
      margin-bottom: 16px;
      scroll-margin-top: 84px;
    }}
    .course-phase h2 {{
      margin-top: 0;
      margin-bottom: 10px;
    }}
    .course-phase-content {{
      line-height: 1.6;
    }}
    .course-phase-content h1,
    .course-phase-content h2,
    .course-phase-content h3,
    .course-phase-content h4 {{
      scroll-margin-top: 84px;
      color: #2d180f;
    }}
    .course-phase-content h1 {{ font-size: 28px; margin-top: 0; }}
    .course-phase-content h2 {{ font-size: 22px; margin-top: 24px; }}
    .course-phase-content h3 {{ font-size: 19px; margin-top: 18px; }}
    .course-phase-content table {{ width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 14px; }}
    .course-phase-content th, .course-phase-content td {{ border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
    .course-phase-content code {{ background: #f1e7d4; padding: 1px 5px; border-radius: 4px; }}
    .course-phase-content pre {{ background: #2e211a; color: #f6e9d5; border-radius: 10px; overflow: auto; padding: 12px; }}
    .course-phase-content img {{ width: 100%; max-width: 720px; border-radius: 8px; border: 1px solid var(--line); }}

    @media (max-width: 900px) {{
      .grid-2 {{ grid-template-columns: 1fr; }}
      .menu-toggle {{ display: inline-flex; }}
      .top-links {{
        display: none;
        width: 100%;
        padding-top: 10px;
        flex-direction: column;
        align-items: stretch;
      }}
      .topbar-inner {{
        flex-wrap: wrap;
      }}
      .top-links.open {{ display: flex; }}
      .top-link {{ text-align: center; border-radius: 10px; border: 1px solid #74513f; }}
      .top-dropdown {{ width: 100%; }}
      .top-dropdown-menu {{
        position: static;
        display: block;
        min-width: 0;
        margin-top: 6px;
      }}
      .phase1-layout {{ grid-template-columns: 1fr; }}
      .topic-index {{ position: static; max-height: none; }}
    }}
  </style>
</head>
<body>
  <header class=\"topbar\">
    <div class=\"topbar-inner\">
      <h1 class=\"brand\">Whisky Study Site</h1>
      <button id=\"menuToggle\" class=\"menu-toggle\" aria-expanded=\"false\" aria-controls=\"topLinks\">Menu</button>
      <nav id=\"topLinks\" class=\"top-links\">{nav}</nav>
    </div>
  </header>
  <div class=\"wrap\">{body}</div>
  <script>
    const toggle = document.getElementById('menuToggle');
    const links = document.getElementById('topLinks');
    if (toggle && links) {{
      toggle.addEventListener('click', () => {{
        const isOpen = links.classList.toggle('open');
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      }});
    }}

    if ('serviceWorker' in navigator) {{
      window.addEventListener('load', () => {{
        navigator.serviceWorker.register('/sw.js').catch(() => {{
          // PWA support is optional; failing registration should not break the site.
        }});
      }});
    }}

    function escapeHtml(text) {{
      return text
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
    }}

    function slugify(text) {{
      return text
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9\\s-]/g, '')
        .replace(/\\s+/g, '-')
        .replace(/-+/g, '-');
    }}

    function inlineMarkdown(text) {{
      let out = escapeHtml(text);
      out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
      out = out.replace(/!\\[([^\\]]*)\\]\\(([^)]+)\\)/g, (_m, alt, src) => {{
        const cleaned = src.startsWith('data/') ? '/media/' + src : src;
        return '<img src="' + cleaned + '" alt="' + escapeHtml(alt) + '" loading="lazy" />';
      }});
        out = out.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, (_m, label, href) => {{
          const isExternal = href.startsWith('http://') || href.startsWith('https://');
          const attrs = isExternal ? ' target="_blank" rel="noreferrer"' : '';
          return '<a href="' + href + '"' + attrs + '>' + label + '</a>';
        }});
      out = out.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
      out = out.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
      return out;
    }}

    function splitTableRow(line) {{
      return line
        .trim()
        .replace(/^\\|/, '')
        .replace(/\\|$/, '')
        .split('|')
        .map((cell) => inlineMarkdown(cell.trim()));
    }}

    function isTableDivider(line) {{
      const t = line.trim();
      if (!t.includes('|')) {{
        return false;
      }}
      return /^\\|?[\\s:-]+\\|[\\s|:-]*$/.test(t);
    }}

    function markdownToHtml(md) {{
      const lines = md.replace(/\\r\\n/g, '\\n').split('\\n');
      const html = [];
      const headingIds = new Map();
      let inCode = false;
      let codeLines = [];
      let inList = false;
      let listType = '';
      let paragraphParts = [];

      function closeList() {{
        if (inList) {{
          html.push('</' + listType + '>');
          inList = false;
          listType = '';
        }}
      }}

      function closeParagraph() {{
        if (paragraphParts.length > 0) {{
          html.push('<p>' + paragraphParts.join(' ') + '</p>');
          paragraphParts = [];
        }}
      }}

      for (let i = 0; i < lines.length; i += 1) {{
        const line = lines[i];
        const trimmed = line.trim();

        if (trimmed.startsWith('```')) {{
          closeParagraph();
          closeList();
          if (!inCode) {{
            inCode = true;
            codeLines = [];
          }} else {{
            html.push('<pre><code>' + escapeHtml(codeLines.join('\\n')) + '</code></pre>');
            inCode = false;
            codeLines = [];
          }}
          continue;
        }}

        if (inCode) {{
          codeLines.push(line);
          continue;
        }}

        if (trimmed === '') {{
          closeParagraph();
          closeList();
          continue;
        }}

        if (trimmed.startsWith('|') && i + 1 < lines.length && isTableDivider(lines[i + 1])) {{
          closeParagraph();
          closeList();
          const headerCells = splitTableRow(lines[i]);
          const rows = [];
          i += 2;
          while (i < lines.length && lines[i].trim().startsWith('|')) {{
            rows.push(splitTableRow(lines[i]));
            i += 1;
          }}
          i -= 1;

          let tableHtml = '<table><thead><tr>';
          for (const cell of headerCells) {{
            tableHtml += '<th>' + cell + '</th>';
          }}
          tableHtml += '</tr></thead><tbody>';

          for (const row of rows) {{
            tableHtml += '<tr>';
            for (const cell of row) {{
              tableHtml += '<td>' + cell + '</td>';
            }}
            tableHtml += '</tr>';
          }}
          tableHtml += '</tbody></table>';
          html.push(tableHtml);
          continue;
        }}

        const headingMatch = trimmed.match(/^(#{{1,6}})\\s+(.+)$/);
        if (headingMatch) {{
          closeParagraph();
          closeList();
          const level = headingMatch[1].length;
          const text = headingMatch[2].trim();
          const base = slugify(text) || 'section';
          const count = headingIds.get(base) || 0;
          headingIds.set(base, count + 1);
          const id = count > 0 ? base + '-' + (count + 1) : base;
          html.push('<h' + level + ' id="' + id + '">' + inlineMarkdown(text) + '</h' + level + '>');
          continue;
        }}

        if (/^(-|\\*){{3,}}$/.test(trimmed)) {{
          closeParagraph();
          closeList();
          html.push('<hr />');
          continue;
        }}

        const listMatch = line.match(/^\\s*([-*+]|\\d+\\.)\\s+(.+)$/);
        if (listMatch) {{
          closeParagraph();
          const currentListType = /\\d+\\./.test(listMatch[1]) ? 'ol' : 'ul';
          if (!inList || listType !== currentListType) {{
            closeList();
            html.push('<' + currentListType + '>');
            inList = true;
            listType = currentListType;
          }}
          html.push('<li>' + inlineMarkdown(listMatch[2].trim()) + '</li>');
          continue;
        }}

        paragraphParts.push(inlineMarkdown(trimmed));
      }}

      closeParagraph();
      closeList();
      if (inCode) {{
        html.push('<pre><code>' + escapeHtml(codeLines.join('\\n')) + '</code></pre>');
      }}
      return html.join('\\n');
    }}

    function buildTopicIndex(contentEl, indexEl) {{
      const headings = contentEl.querySelectorAll('h2, h3, h4');
      if (!headings.length) {{
        indexEl.innerHTML = '<p class="muted">No section headings found.</p>';
        return;
      }}

      let html = '<div class="topic-index-header"><h2>Topics</h2><a id="quizNavBtn" class="quiz-nav-btn" href="#phaseQuizPanel">Quiz ↓</a></div><ul>';
      headings.forEach((heading) => {{
        const levelClass = heading.tagName.toLowerCase() === 'h2' ? 'l2' : (heading.tagName.toLowerCase() === 'h3' ? 'l3' : 'l4');
        html += '<li class="' + levelClass + '"><a href="#' + heading.id + '">' + escapeHtml(heading.textContent || '') + '</a></li>';
      }});
      html += '</ul>';
      indexEl.innerHTML = html;
    }}

    function loadQuizProgress() {{
      try {{
        const raw = localStorage.getItem('whiskyQuizProgressV1');
        if (!raw) {{
          return {{}};
        }}
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {{}};
      }} catch (_error) {{
        return {{}};
      }}
    }}

    function saveQuizProgress(progress) {{
      localStorage.setItem('whiskyQuizProgressV1', JSON.stringify(progress));
    }}

    function ensureQuizAnswers(progress, quizId) {{
      if (!progress[quizId] || typeof progress[quizId] !== 'object') {{
        progress[quizId] = {{}};
      }}
      return progress[quizId];
    }}

    function renderPhaseQuizList(quizListEl, quizzes, progress) {{
      if (!quizzes.length) {{
        quizListEl.innerHTML = '<p class="muted">No quiz found for this phase.</p>';
        return;
      }}

      const cards = [];
      for (const quiz of quizzes) {{
        const quizAnswers = ensureQuizAnswers(progress, quiz.id);
        let answered = 0;
        let correct = 0;
        for (const question of quiz.questions) {{
          const answer = quizAnswers[String(question.number)];
          if (answer) {{
            answered += 1;
            if (question.correct && answer === question.correct) {{
              correct += 1;
            }}
          }}
        }}

        let questionBlocks = '';
        for (const question of quiz.questions) {{
          const qKey = String(question.number);
          const chosen = quizAnswers[qKey] || '';
          let optionBlocks = '';
          for (const option of question.options) {{
            const inputId = quiz.id + '-q' + question.number + '-' + option.id;
            const checked = chosen === option.id ? 'checked' : '';
            optionBlocks +=
              '<label class="quiz-option" for="' + inputId + '">' +
                '<input class="quiz-option-input" type="radio" name="' + quiz.id + '-q' + question.number + '" id="' + inputId + '" data-quiz="' + quiz.id + '" data-question="' + question.number + '" data-option="' + option.id + '" ' + checked + ' />' +
                '<strong>' + option.id + ')</strong> ' + escapeHtml(option.text) +
              '</label>';
          }}

          let feedbackText = '';
          if (chosen) {{
            const isCorrect = question.correct && chosen === question.correct;
            const status = isCorrect ? 'Correct.' : 'Not quite.';
            const correctPart = question.correct ? ' Correct answer: <strong>' + question.correct + '</strong>.' : '';
            const moreInfo = question.more_info ? ' ' + escapeHtml(question.more_info) : '';
            feedbackText = '<p class="muted"><strong>' + status + '</strong>' + correctPart + moreInfo + '</p>';
          }}
          questionBlocks +=
            '<div class="quiz-question">' +
              '<p><strong>' + question.number + '.</strong> ' + escapeHtml(question.prompt) + '</p>' +
              optionBlocks +
              feedbackText +
            '</div>';
        }}

        cards.push(
          '<article class="quiz-card" id="quiz-' + quiz.id + '">' +
            '<h3>' + escapeHtml(quiz.title) + '</h3>' +
            '<p class="quiz-meta">Progress: ' + answered + '/' + quiz.questions.length + ' answered | ' + correct + ' correct</p>' +
            questionBlocks +
            '<div class="quiz-actions"><button class="button-secondary quiz-reset" data-quiz-reset="' + quiz.id + '">Reset quiz</button></div>' +
          '</article>'
        );
      }}
      quizListEl.innerHTML = cards.join('');
    }}

    async function renderPhaseQuizPanel(pagePath) {{
      const panelEl = document.getElementById('phaseQuizPanel');
      const listEl = document.getElementById('phaseQuizList');
      if (!panelEl || !listEl || !pagePath) {{
        return;
      }}

      try {{
        const response = await fetch('/quizzes/data');
        if (!response.ok) {{
          throw new Error('Quiz data unavailable');
        }}
        const payload = await response.json();
        const allQuizzes = payload.quizzes || [];
        const phaseQuizzes = allQuizzes.filter((quiz) => quiz.pagePath === pagePath);
        const progress = loadQuizProgress();

        renderPhaseQuizList(listEl, phaseQuizzes, progress);

        listEl.addEventListener('change', function (event) {{
          const target = event.target;
          if (!target || !target.classList.contains('quiz-option-input')) {{
            return;
          }}
          const quizId = target.getAttribute('data-quiz');
          const questionNumber = target.getAttribute('data-question');
          const option = target.getAttribute('data-option');
          if (!quizId || !questionNumber || !option) {{
            return;
          }}
          const quizAnswers = ensureQuizAnswers(progress, quizId);
          quizAnswers[String(questionNumber)] = option;
          saveQuizProgress(progress);
          renderPhaseQuizList(listEl, phaseQuizzes, progress);
        }});

        listEl.addEventListener('click', function (event) {{
          const target = event.target;
          if (!target || !target.matches('[data-quiz-reset]')) {{
            return;
          }}
          const quizId = target.getAttribute('data-quiz-reset');
          if (!quizId) {{
            return;
          }}
          progress[quizId] = {{}};
          saveQuizProgress(progress);
          renderPhaseQuizList(listEl, phaseQuizzes, progress);
        }});
      }} catch (_error) {{
        listEl.innerHTML = '<p class="muted">Unable to load quiz data.</p>';
      }}
    }}

    async function renderMarkdownPage() {{
      const contentEl = document.getElementById('phaseMarkdownContent') || document.getElementById('phase1Content');
      const indexEl = document.getElementById('topicIndex');
      if (!contentEl || !indexEl) {{
        return;
      }}

      const sourceUrl = contentEl.dataset.markdownUrl;
      const pagePath = contentEl.dataset.pagePath || '/phase-1';
      if (!sourceUrl) {{
        contentEl.innerHTML = '<p>Missing markdown source URL.</p>';
        return;
      }}

      try {{
        const response = await fetch(sourceUrl);
        if (!response.ok) {{
          throw new Error('Could not load markdown source.');
        }}
        const markdown = await response.text();
        contentEl.innerHTML = markdownToHtml(markdown);

        contentEl.querySelectorAll('img').forEach((img) => {{
          if (!img.getAttribute('src')) {{
            return;
          }}
          const src = img.getAttribute('src');
          if (src && src.startsWith('data/')) {{
            img.setAttribute('src', '/media/' + src);
          }}
        }});

        buildTopicIndex(contentEl, indexEl);
        await renderPhaseQuizPanel(pagePath);
      }} catch (_error) {{
        contentEl.innerHTML = '<p>Unable to render phase markdown content.</p>';
        indexEl.innerHTML = '<p class="muted">Topic index unavailable.</p>';
      }}
    }}

    async function renderCoursePage() {{
      const courseWrap = document.getElementById('coursePhases');
      if (!courseWrap) {{
        return;
      }}

      const sections = Array.from(courseWrap.querySelectorAll('[data-phase-path]'));
      for (const section of sections) {{
        const phasePath = section.getAttribute('data-phase-path');
        const contentEl = section.querySelector('.course-phase-content');
        if (!phasePath || !contentEl) {{
          continue;
        }}

        try {{
          const response = await fetch(phasePath + '/raw');
          if (!response.ok) {{
            throw new Error('Unable to load phase');
          }}
          const markdown = await response.text();
          contentEl.innerHTML = markdownToHtml(markdown);

          contentEl.querySelectorAll('img').forEach((img) => {{
            const src = img.getAttribute('src');
            if (src && src.startsWith('data/')) {{
              img.setAttribute('src', '/media/' + src);
            }}
          }});
        }} catch (_error) {{
          contentEl.innerHTML = '<p class="muted">Unable to load this phase right now.</p>';
        }}
      }}

      const jump = document.getElementById('coursePhaseJump');
      if (jump) {{
        jump.addEventListener('change', function () {{
          const targetId = jump.value;
          if (!targetId) {{
            return;
          }}
          const target = document.getElementById(targetId);
          if (target) {{
            target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          }}
        }});
      }}
    }}

    renderMarkdownPage();
    renderCoursePage();
  </script>
</body>
</html>
"""

    def render_home(self) -> None:
        body = """
        <section class=\"hero\">
          <h1>Whisky Learning Website</h1>
          <p class=\"muted\">Study all course phases in one place, take quizzes, and browse the local distillery research database.</p>
        </section>

        <section class=\"cards\">
            <a class=\"card-link\" href=\"/whisky-lessons\">
              <h2>Whisky Lessons</h2>
              <p class=\"muted\">Lesson index page linking all phase pages, with direct access from the Whisky Lessons dropdown in navigation.</p>
          </a>
          <a class=\"card-link\" href=\"/phase-1\">
            <h2>Orientation and Foundations</h2>
            <p class=\"muted\">The expanded markdown is rendered directly in-browser with a left-hand topic index built from headings.</p>
          </a>
          <a class=\"card-link\" href=\"/quizzes\">
            <h2>Quizzes</h2>
            <p class=\"muted\">Take multiple-choice quizzes from phase documents and track completion in browser storage.</p>
          </a>
          <a class=\"card-link\" href=\"/database\">
            <h2>Distillery Database</h2>
            <p class=\"muted\">Search by region, country, style, operating status, confidence, and image availability.</p>
          </a>
        </section>
        """
        self.send_html(self.page_shell("Whisky Study Site", body, "/"))

    def render_whisky_course(self, current_path: str = "/whisky-lessons") -> None:
        phase_entries = sorted(
            self.phase_pages.items(),
            key=lambda item: int(item[0].split("-")[-1]),
        )

        phase_cards = "".join(
            (
                f"<a class='card-link' href='{escape(page_path)}'>"
                f"<h2>{escape(page['title'])}</h2>"
                f"<p class='muted'>Open lesson page ({escape(page['source'])})</p>"
                "</a>"
            )
            for page_path, page in phase_entries
        )

        body = f"""
        <section class=\"hero\">
          <h1>Whisky Lessons</h1>
          <p class=\"muted\">This page links all lesson phases. The Whisky Lessons navigation item includes a dropdown menu for direct access to every phase page.</p>
        </section>

        <section class=\"cards\">
          {phase_cards}
        </section>
        """
        self.send_html(self.page_shell("Whisky Lessons", body, current_path))

    def render_phase_document(self, page_path: str) -> None:
        page = self.phase_pages.get(page_path)
        if not page:
            self.send_error(404, "Phase page not found")
            return

        title = page["title"]
        body = f"""
        <section class=\"phase1-layout\">
          <aside id=\"topicIndex\" class=\"topic-index\">
            <p class=\"muted\">Building topic index...</p>
          </aside>
          <article id=\"phaseMarkdownContent\" class=\"markdown-panel\" data-markdown-url=\"{escape(page_path)}/raw\" data-page-path=\"{escape(page_path)}\">
            <p class=\"muted\">Loading markdown content...</p>
          </article>
        </section>

        <section id=\"phaseQuizPanel\" class=\"panel\" data-page-path=\"{escape(page_path)}\" style=\"margin-top: 16px;\">
          <h2>Quiz</h2>
          <div id=\"phaseQuizList\"><p class=\"muted\">Loading quiz...</p></div>
        </section>
        """
        self.send_html(self.page_shell(title, body, page_path))

    def render_phase_raw(self, raw_path: str) -> None:
        page_path = raw_path[:-4]
        page = self.phase_pages.get(page_path)
        if not page:
            self.send_error(404, "Phase markdown not found")
            return
        md_path = Path(page["markdown_path"])
        if not md_path.exists():
            self.send_error(404, "Phase markdown file not found")
            return
        text = md_path.read_text(encoding="utf-8")
        text = self._rewrite_distillery_markdown_links(text)
        # Strip quiz section (## N. Quiz: ... through answer key and more info)
        # so it is not duplicated above the interactive quiz panel
        text = re.sub(r"\n## \d+\. Quiz:[\s\S]*?(?=\n---|\Z)", "", text)
        # Strip Image Notes section (always at end of file)
        text = re.sub(r"\n## Image Notes[\s\S]*\Z", "", text)
        self.send_text(text)

    def render_phase1(self) -> None:
        self.render_phase_document("/phase-1")

    def render_phase1_raw(self) -> None:
        self.render_phase_raw("/phase-1/raw")

    def _slugify(self, value: str) -> str:
        lowered = value.lower().strip()
        return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")

    def _parse_quizzes_from_markdown(self, path: Path, page_path: str) -> list[dict[str, object]]:
        if not path.exists():
            return []

        lines = path.read_text(encoding="utf-8").splitlines()
        quizzes: list[dict[str, object]] = []
        i = 0
        while i < len(lines):
            quiz_heading = re.match(r"^##\s+\d+\.\s+Quiz:\s*(.+)$", lines[i].strip())
            if not quiz_heading:
                i += 1
                continue

            quiz_title = quiz_heading.group(1).strip()
            i += 1
            questions: list[dict[str, object]] = []

            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith("### Quiz Answer Key") or stripped.startswith("## "):
                    break
                if not stripped:
                    i += 1
                    continue

                q_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
                if q_match:
                    q_number = int(q_match.group(1))
                    q_text = q_match.group(2).strip()
                    i += 1
                    options: list[dict[str, str]] = []
                    while i < len(lines):
                        opt_line = lines[i].strip()
                        opt_match = re.match(r"^([A-Z])\)\s+(.+)$", opt_line)
                        if opt_match:
                            options.append({"id": opt_match.group(1), "text": opt_match.group(2).strip()})
                            i += 1
                            continue
                        if not opt_line:
                            i += 1
                            continue
                        break

                    questions.append(
                        {
                            "number": q_number,
                            "prompt": q_text,
                            "options": options,
                            "correct": "",
                            "more_info": "",
                        }
                    )
                    continue

                i += 1

            answer_map: dict[int, str] = {}
            if i < len(lines) and lines[i].strip().startswith("### Quiz Answer Key"):
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("|"):
                    if lines[i].strip().startswith("## "):
                        break
                    i += 1

                while i < len(lines) and lines[i].strip().startswith("|"):
                    row = lines[i].strip()
                    i += 1
                    if "---" in row:
                        continue
                    cells = [cell.strip() for cell in row.strip("|").split("|")]
                    if len(cells) < 2:
                        continue
                    if not cells[0].isdigit():
                        continue
                    answer = cells[1].upper().strip()
                    if re.fullmatch(r"[A-Z]", answer):
                        answer_map[int(cells[0])] = answer

                more_info_map: dict[int, str] = {}
                while i < len(lines) and not lines[i].strip():
                    i += 1

                if i < len(lines) and lines[i].strip().startswith("### Quiz More Information"):
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("|"):
                        if lines[i].strip().startswith("## "):
                            break
                        i += 1

                    while i < len(lines) and lines[i].strip().startswith("|"):
                        row = lines[i].strip()
                        i += 1
                        if "---" in row:
                            continue
                        cells = [cell.strip() for cell in row.strip("|").split("|")]
                        if len(cells) < 2:
                            continue
                        if not cells[0].isdigit():
                            continue
                        more_info = " | ".join(cells[1:]).strip()
                        if more_info:
                            more_info_map[int(cells[0])] = more_info

            for question in questions:
                q_num = int(question["number"])
                question["correct"] = answer_map.get(q_num, "")
                question["more_info"] = more_info_map.get(q_num, "")

            if questions:
                quiz_id = f"{path.stem.lower()}-{self._slugify(quiz_title)}"
                quizzes.append(
                    {
                        "id": quiz_id,
                        "title": quiz_title,
                        "phase": path.stem,
                        "pagePath": page_path,
                        "source": path.name,
                        "questions": questions,
                    }
                )

        return quizzes

    def _collect_quizzes_data(self) -> list[dict[str, object]]:
        collected: list[dict[str, object]] = []
        for page_path, page in self.phase_pages.items():
            markdown_path = Path(page["markdown_path"])
            collected.extend(self._parse_quizzes_from_markdown(markdown_path, page_path))
        return collected

    def render_quizzes_data(self) -> None:
        self.send_json({"quizzes": self._collect_quizzes_data()})

    def render_quizzes(self) -> None:
        body = """
        <section class=\"hero\">
          <h1>Quizzes</h1>
          <p class=\"muted\">Track quiz progress across all phases. Open each quiz on its source content page to answer questions.</p>
          <div id=\"quizOverall\" class=\"panel\"><p class=\"muted\">Loading quiz progress...</p></div>
        </section>

        <section id=\"quizSummary\" class=\"quiz-summary\"></section>

        <script>
          (function () {
            const storageKey = 'whiskyQuizProgressV1';
            const summaryEl = document.getElementById('quizSummary');
            const overallEl = document.getElementById('quizOverall');

            if (!summaryEl || !overallEl) {
              return;
            }

            function loadProgress() {
              try {
                const raw = localStorage.getItem(storageKey);
                if (!raw) {
                  return {};
                }
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === 'object') {
                  return parsed;
                }
                return {};
              } catch (_error) {
                return {};
              }
            }

            function saveProgress(progress) {
              localStorage.setItem(storageKey, JSON.stringify(progress));
            }

            function ensureQuizAnswers(progress, quizId) {
              if (!progress[quizId] || typeof progress[quizId] !== 'object') {
                progress[quizId] = {};
              }
              return progress[quizId];
            }

            function computeMetrics(quiz, quizAnswers) {
              const total = quiz.questions.length;
              let answered = 0;
              let correct = 0;
              for (const question of quiz.questions) {
                const qKey = String(question.number);
                const answer = quizAnswers[qKey];
                if (answer) {
                  answered += 1;
                  if (question.correct && answer === question.correct) {
                    correct += 1;
                  }
                }
              }
              const completion = total > 0 ? Math.round((answered / total) * 100) : 0;
              return { total, answered, correct, completion };
            }

            function progressBar(percent) {
              return '<div class=\\\"progress-track\\\"><div class=\\\"progress-fill\\\" style=\\\"width:' + percent + '%\\\"></div></div>';
            }

            function renderAll(quizzes, progress) {
              let totalQuestions = 0;
              let totalAnswered = 0;
              let totalCorrect = 0;
              let fullyComplete = 0;

              const summaryHtml = [];

              for (const quiz of quizzes) {
                const quizAnswers = ensureQuizAnswers(progress, quiz.id);
                const metrics = computeMetrics(quiz, quizAnswers);

                totalQuestions += metrics.total;
                totalAnswered += metrics.answered;
                totalCorrect += metrics.correct;
                if (metrics.answered === metrics.total && metrics.total > 0) {
                  fullyComplete += 1;
                }

                const cardUrl = quiz.pagePath + '#phaseQuizPanel';
                summaryHtml.push(
                  '<a class=\\\"quiz-card\\\" href=\\\"' + cardUrl + '\\\">' +
                    '<h3>' + escapeHtml(quiz.title) + '</h3>' +
                    '<p class=\\\"quiz-meta\\\">' + escapeHtml(quiz.phase) + ' | ' + metrics.answered + '/' + metrics.total + ' answered | ' + metrics.correct + ' correct</p>' +
                    progressBar(metrics.completion) +
                  '</a>'
                );
              }

              const overallPercent = totalQuestions > 0 ? Math.round((totalAnswered / totalQuestions) * 100) : 0;
              overallEl.innerHTML =
                '<h2>Overall Progress</h2>' +
                '<p class=\\\"quiz-meta\\\">' +
                  totalAnswered + '/' + totalQuestions + ' answered | ' +
                  totalCorrect + ' correct selections | ' +
                  fullyComplete + '/' + quizzes.length + ' quizzes complete' +
                '</p>' +
                progressBar(overallPercent);

              summaryEl.innerHTML = summaryHtml.join('');
            }

            async function init() {
              const progress = loadProgress();
              const response = await fetch('/quizzes/data');
              if (!response.ok) {
                throw new Error('Unable to load quiz data');
              }
              const payload = await response.json();
              const quizzes = payload.quizzes || [];

              renderAll(quizzes, progress);
            }

            init().catch(function () {
              overallEl.innerHTML = '<p>Unable to load quiz page.</p>';
              summaryEl.innerHTML = '';
            });
          }());
        </script>
        """

        self.send_html(self.page_shell("Whisky Quizzes", body, "/quizzes"))

    def render_database(self, query_string: str) -> None:
        dataset = self.load_exported_dataset()
        if dataset:
            self.render_database_json_app()
            return
        if self.static_mode:
            self.send_error(500, "Static mode requires exported JSON dataset files in data/web")
            return
        self.render_database_sql(query_string)

    def render_database_json_app(self) -> None:
        body = """
        <section class=\"hero\">
          <h1>Whisky Distillery Research Database</h1>
        </section>

        <div class=\"grid grid-2\">
          <aside class=\"panel\">
            <h2>Search</h2>
            <form id=\"dbFilterForm\">
              <div class=\"quiz-actions\" style=\"margin-bottom:12px;\">
                <button type=\"submit\">Search</button>
                <button id=\"resetFilters\" type=\"button\" class=\"button-secondary\">Reset</button>
              </div>

              <label>Name</label>
              <input id=\"fName\" name=\"name\" />

              <label>Country</label>
              <select id=\"fCountry\" name=\"country\"><option value=\"\"></option></select>

              <label>Region</label>
              <select id=\"fRegion\" name=\"region\"><option value=\"\"></option></select>

              <label>Whisky Style (text)</label>
              <input id=\"fStyle\" name=\"style\" placeholder=\"peated, single malt, sherry cask...\" />

              <div class=\"filter-group\">
                <h3>Whisky Style Facets</h3>
                <div id=\"styleFacetWrap\"></div>
              </div>

              <div class=\"filter-group\">
                <h3>Image Type</h3>
                <div id=\"imageFacetWrap\"></div>
              </div>

              <label>Operating Status</label>
              <select id=\"fOperating\" name=\"operating_status\">
                <option value=\"active\">Active (hide closed)</option>
                <option value=\"all\">All statuses</option>
              </select>

              <label>Website Confidence</label>
              <select id=\"fConfidence\" name=\"confidence\"><option value=\"\"></option></select>

              <label><input id=\"fHasImages\" type=\"checkbox\" name=\"has_images\" value=\"1\" style=\"width:auto;margin-right:8px;\" />Only distilleries with images</label>

            </form>
          </aside>

          <section class=\"panel\">
            <h2 id=\"resultsHeading\">Results</h2>
            <table class=\"results\">
              <thead>
                <tr>
                  <th>Distillery</th>
                  <th>Country</th>
                  <th>Region</th>
                  <th>Operating</th>
                  <th>Confidence</th>
                  <th>Styles</th>
                  <th>Images</th>
                </tr>
              </thead>
              <tbody id=\"resultsBody\"></tbody>
            </table>
            <p id=\"datasetStatus\" class=\"muted\" style=\"margin-top:12px;\"></p>
          </section>
        </div>

        <script>
          (function () {
            const form = document.getElementById('dbFilterForm');
            const resultsBody = document.getElementById('resultsBody');
            const resultsHeading = document.getElementById('resultsHeading');
            const datasetStatus = document.getElementById('datasetStatus');
            const styleFacetWrap = document.getElementById('styleFacetWrap');
            const imageFacetWrap = document.getElementById('imageFacetWrap');
            const resetFilters = document.getElementById('resetFilters');

            const fields = {
              name: document.getElementById('fName'),
              country: document.getElementById('fCountry'),
              region: document.getElementById('fRegion'),
              style: document.getElementById('fStyle'),
              operating_status: document.getElementById('fOperating'),
              confidence: document.getElementById('fConfidence'),
              has_images: document.getElementById('fHasImages'),
            };

            if (!form || !resultsBody || !resultsHeading || !datasetStatus || !styleFacetWrap || !imageFacetWrap) {
              return;
            }

            function htmlEscape(text) {
              return (text || '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;');
            }

            function optionHtml(value, selectedValue) {
              return '<option value="' + htmlEscape(value) + '"' + (value === selectedValue ? ' selected' : '') + '>' + htmlEscape(value) + '</option>';
            }

            function checkedChip(name, value, selectedSet) {
              const checked = selectedSet.has(value) ? ' checked' : '';
              return '<label class="chip-check"><input type="checkbox" name="' + name + '" value="' + htmlEscape(value) + '"' + checked + ' /><span>' + htmlEscape(value) + '</span></label>';
            }

            function getStateFromUrl() {
              const params = new URLSearchParams(window.location.search);
              return {
                name: params.get('name') || '',
                country: params.get('country') || '',
                region: params.get('region') || '',
                style: params.get('style') || '',
                style_tag: params.getAll('style_tag').filter(Boolean),
                image_type: params.getAll('image_type').filter(Boolean),
                operating_status: params.get('operating_status') || 'active',
                confidence: params.get('confidence') || '',
                has_images: params.get('has_images') === '1',
              };
            }

            function writeStateToUrl(state) {
              const params = new URLSearchParams();
              if (state.name) params.set('name', state.name);
              if (state.country) params.set('country', state.country);
              if (state.region) params.set('region', state.region);
              if (state.style) params.set('style', state.style);
              state.style_tag.forEach((v) => params.append('style_tag', v));
              state.image_type.forEach((v) => params.append('image_type', v));
              if (state.operating_status && state.operating_status !== 'active') {
                params.set('operating_status', state.operating_status);
              }
              if (state.confidence) params.set('confidence', state.confidence);
              if (state.has_images) params.set('has_images', '1');
              const query = params.toString();
              const nextUrl = query ? '/database?' + query : '/database';
              window.history.replaceState({}, '', nextUrl);
            }

            function readFormState() {
              return {
                name: fields.name.value.trim(),
                country: fields.country.value.trim(),
                region: fields.region.value.trim(),
                style: fields.style.value.trim(),
                style_tag: Array.from(form.querySelectorAll('input[name="style_tag"]:checked')).map((el) => el.value),
                image_type: Array.from(form.querySelectorAll('input[name="image_type"]:checked')).map((el) => el.value),
                operating_status: fields.operating_status.value.trim() || 'active',
                confidence: fields.confidence.value.trim(),
                has_images: fields.has_images.checked,
              };
            }

            function applyStateToForm(state, taxonomy) {
              fields.name.value = state.name;
              fields.country.innerHTML = '<option value=""></option>' + taxonomy.countries.map((v) => optionHtml(v, state.country)).join('');
              fields.region.innerHTML = '<option value=""></option>' + taxonomy.regions.map((v) => optionHtml(v, state.region)).join('');
              fields.style.value = state.style;
              fields.confidence.innerHTML = '<option value=""></option>' + taxonomy.websiteConfidenceLevels.map((v) => optionHtml(v, state.confidence)).join('');

              const operatingExtras = taxonomy.operatingStatuses
                .filter((v) => v && v !== 'Closed')
                .map((v) => optionHtml(v, state.operating_status))
                .join('');
              fields.operating_status.innerHTML =
                '<option value="active"' + (state.operating_status === 'active' ? ' selected' : '') + '>Active (hide closed)</option>' +
                '<option value="all"' + (state.operating_status === 'all' ? ' selected' : '') + '>All statuses</option>' +
                operatingExtras;

              const styleSet = new Set(state.style_tag);
              const imageSet = new Set(state.image_type);
              styleFacetWrap.innerHTML = taxonomy.styles.map((v) => checkedChip('style_tag', v, styleSet)).join('');
              imageFacetWrap.innerHTML = taxonomy.imageCategories.map((v) => checkedChip('image_type', v, imageSet)).join('');
              fields.has_images.checked = state.has_images;
            }

            function matchState(item, state) {
              const hay = (item.name + ' ' + item.styles.join(' ') + ' ' + item.keyFocus + ' ' + item.whyStudy + ' ' + item.notes).toLowerCase();
              if (state.name && !item.name.toLowerCase().includes(state.name.toLowerCase())) return false;
              if (state.country && item.country !== state.country) return false;
              if (state.region && item.region !== state.region) return false;
              if (state.confidence && item.websiteConfidence !== state.confidence) return false;
              if (state.style && !hay.includes(state.style.toLowerCase())) return false;

              if (state.operating_status === 'active') {
                if (item.operatingStatus === 'Closed') return false;
              } else if (state.operating_status !== 'all' && state.operating_status && item.operatingStatus !== state.operating_status) {
                return false;
              }

              if (state.style_tag.length > 0) {
                const itemStyles = new Set(item.styles);
                for (const tag of state.style_tag) {
                  if (!itemStyles.has(tag)) {
                    return false;
                  }
                }
              }

              if (state.image_type.length > 0) {
                const itemImageTypes = new Set(item.images.map((img) => img.category).filter(Boolean));
                for (const imageType of state.image_type) {
                  if (!itemImageTypes.has(imageType)) {
                    return false;
                  }
                }
              }

              if (state.has_images && (!item.imageCount || item.imageCount < 1)) {
                return false;
              }

              return true;
            }

            function renderRows(items) {
              const rows = items
                .map((item) => {
                  return '<tr>' +
                    '<td><a href="/distillery/' + item.id + '">' + htmlEscape(item.name) + '</a></td>' +
                    '<td>' + htmlEscape(item.country) + '</td>' +
                    '<td>' + htmlEscape(item.region) + '</td>' +
                    '<td>' + htmlEscape(item.operatingStatus) + '</td>' +
                    '<td>' + htmlEscape(item.websiteConfidence) + '</td>' +
                    '<td>' + htmlEscape(item.styles.join(', ')) + '</td>' +
                    '<td>' + String(item.imageCount || 0) + '</td>' +
                  '</tr>';
                })
                .join('');

              resultsBody.innerHTML = rows || '<tr><td colspan="7" class="muted">No distilleries match the current filters.</td></tr>';
              resultsHeading.textContent = 'Results (' + items.length + ')';
            }

            async function init() {
              const [distilleriesResp, taxonomyResp, manifestResp] = await Promise.all([
                fetch('/data-web/distilleries.json'),
                fetch('/data-web/taxonomy.json'),
                fetch('/data-web/dataset-manifest.json').catch(() => null),
              ]);

              if (!distilleriesResp.ok || !taxonomyResp.ok) {
                throw new Error('Unable to load dataset exports. Run scripts/export_json_dataset.py first.');
              }

              const distilleriesPayload = await distilleriesResp.json();
              const taxonomyPayload = await taxonomyResp.json();
              const distilleries = Array.isArray(distilleriesPayload.distilleries) ? distilleriesPayload.distilleries : [];

              const taxonomy = {
                countries: taxonomyPayload.countries || [],
                regions: taxonomyPayload.regions || [],
                styles: taxonomyPayload.styles || [],
                operatingStatuses: taxonomyPayload.operatingStatuses || [],
                websiteConfidenceLevels: taxonomyPayload.websiteConfidenceLevels || [],
                imageCategories: taxonomyPayload.imageCategories || [],
              };

              const initialState = getStateFromUrl();
              applyStateToForm(initialState, taxonomy);

              // Build country → regions map from loaded distilleries data
              const countryToRegions = {};
              distilleries.forEach(function (item) {
                if (item.country) {
                  if (!countryToRegions[item.country]) countryToRegions[item.country] = new Set();
                  if (item.region) countryToRegions[item.country].add(item.region);
                }
              });
              Object.keys(countryToRegions).forEach(function (c) {
                countryToRegions[c] = Array.from(countryToRegions[c]).sort();
              });

              function updateRegionOptions(selectedCountry, selectedRegion) {
                const regions = selectedCountry ? (countryToRegions[selectedCountry] || []) : taxonomy.regions;
                const validRegion = regions.includes(selectedRegion) ? selectedRegion : \'\';
                fields.region.innerHTML = \'<option value=\"\"></option>\' + regions.map((v) => optionHtml(v, validRegion)).join(\'\');
              }

              updateRegionOptions(initialState.country, initialState.region);

              function refreshFromForm() {
                const state = readFormState();
                writeStateToUrl(state);
                const filtered = distilleries.filter((item) => matchState(item, state));
                renderRows(filtered);
              }

              form.addEventListener('submit', function (event) {
                event.preventDefault();
                refreshFromForm();
              });

              form.addEventListener('change', function (event) {
                if (event.target === fields.country) {
                  updateRegionOptions(fields.country.value, '');
                }
                refreshFromForm();
              });

              if (resetFilters) {
                resetFilters.addEventListener('click', function () {
                  applyStateToForm({
                    name: '', country: '', region: '', style: '', style_tag: [], image_type: [], operating_status: 'active', confidence: '', has_images: false,
                  }, taxonomy);
                  updateRegionOptions('', '');
                  refreshFromForm();
                });
              }

              const initialFiltered = distilleries.filter((item) => matchState(item, initialState));
              renderRows(initialFiltered);

              if (manifestResp && manifestResp.ok) {
                const manifest = await manifestResp.json();
                datasetStatus.textContent = 'Dataset version ' + (manifest.schemaVersion || 'unknown') + ' | Records: ' + (manifest.recordCount || distilleries.length);
              } else {
                datasetStatus.textContent = 'Dataset loaded from /data-web/*.json';
              }
            }

            init().catch(function (error) {
              resultsBody.innerHTML = '<tr><td colspan="7">Unable to load JSON dataset. ' + htmlEscape(error.message || 'Unknown error') + '</td></tr>';
            });
          }());
        </script>
        """

        self.send_html(self.page_shell("Whisky Distillery DB", body, "/database"))

    def render_database_sql(self, query_string: str) -> None:
        q = parse_qs(query_string)

        name = q.get("name", [""])[0].strip()
        country = q.get("country", [""])[0].strip()
        region = q.get("region", [""])[0].strip()
        style = q.get("style", [""])[0].strip()
        style_tags = [v.strip() for v in q.get("style_tag", []) if v.strip()]
        image_types = [v.strip() for v in q.get("image_type", []) if v.strip()]
        operating_status = q.get("operating_status", ["active"])[0].strip()
        confidence = q.get("confidence", [""])[0].strip()
        has_images = q.get("has_images", [""])[0].strip()

        clauses = ["1=1"]
        params: list[str] = []

        if name:
            clauses.append("d.name LIKE ?")
            params.append(f"%{name}%")
        if country:
            clauses.append("d.country = ?")
            params.append(country)
        if region:
            clauses.append("d.region = ?")
            params.append(region)
        if operating_status == "active":
            clauses.append("(d.operating_status IS NULL OR d.operating_status <> 'Closed')")
        elif operating_status == "all":
            pass
        elif operating_status:
            clauses.append("d.operating_status = ?")
            params.append(operating_status)
        if confidence:
            clauses.append("d.website_confidence = ?")
            params.append(confidence)
        if style:
            clauses.append(
                "EXISTS (SELECT 1 FROM distillery_styles ds JOIN styles s ON s.id = ds.style_id WHERE ds.distillery_id = d.id AND s.name LIKE ?)"
            )
            params.append(f"%{style}%")
        if style_tags:
            placeholders = ", ".join("?" for _ in style_tags)
            clauses.append(
                f"EXISTS (SELECT 1 FROM distillery_styles ds JOIN styles s ON s.id = ds.style_id WHERE ds.distillery_id = d.id AND s.name IN ({placeholders}))"
            )
            params.extend(style_tags)
        if image_types:
            placeholders = ", ".join("?" for _ in image_types)
            clauses.append(
                f"EXISTS (SELECT 1 FROM images i WHERE i.distillery_id = d.id AND i.category IN ({placeholders}))"
            )
            params.extend(image_types)
        if has_images:
            clauses.append("EXISTS (SELECT 1 FROM images i WHERE i.distillery_id = d.id)")

        where_sql = " AND ".join(clauses)

        with self.db() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    d.id,
                    d.name,
                    d.country,
                    d.region,
                    d.operating_status,
                    d.website_confidence,
                    d.official_site,
                    COALESCE((SELECT COUNT(*) FROM images i WHERE i.distillery_id = d.id), 0) AS image_count,
                    COALESCE((
                        SELECT GROUP_CONCAT(s.name, ', ')
                        FROM distillery_styles ds
                        JOIN styles s ON s.id = ds.style_id
                        WHERE ds.distillery_id = d.id
                    ), '') AS styles
                FROM distilleries d
                WHERE {where_sql}
                ORDER BY d.country, d.region, d.name
                """,
                params,
            ).fetchall()

            operating_values = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT operating_status FROM distilleries WHERE operating_status <> '' ORDER BY operating_status"
                ).fetchall()
            ]
            confidence_values = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT website_confidence FROM distilleries WHERE website_confidence <> '' ORDER BY website_confidence"
                ).fetchall()
            ]
            style_values = [
                r[0]
                for r in conn.execute("SELECT name FROM styles ORDER BY name").fetchall()
            ]
            country_values = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT country FROM distilleries WHERE country <> '' ORDER BY country"
                ).fetchall()
            ]
            region_values = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT region FROM distilleries WHERE region <> '' ORDER BY region"
                ).fetchall()
            ]

        results_html = "".join(
            f"""
            <tr>
              <td><a href=\"/distillery/{row['id']}\">{escape(row['name'])}</a></td>
              <td>{escape(row['country'] or '')}</td>
              <td>{escape(row['region'] or '')}</td>
              <td>{escape(row['operating_status'] or '')}</td>
              <td>{escape(row['website_confidence'] or '')}</td>
              <td>{escape(row['styles'])}</td>
              <td>{row['image_count']}</td>
            </tr>
            """
            for row in rows
        )

        options_operating = (
            f"<option value='active' {'selected' if operating_status == 'active' else ''}>Active (hide closed)</option>"
            f"<option value='all' {'selected' if operating_status == 'all' else ''}>All statuses</option>"
            + "".join(
                f"<option value='{escape(value)}' {'selected' if operating_status == value else ''}>{escape(value)}</option>"
                for value in operating_values
            )
        )
        options_confidence = "".join(
            f"<option {'selected' if confidence == value else ''}>{escape(value)}</option>"
            for value in confidence_values
        )
        options_country = "".join(
            f"<option value='{escape(value)}' {'selected' if country == value else ''}>{escape(value)}</option>"
            for value in country_values
        )
        options_region = "".join(
            f"<option value='{escape(value)}' {'selected' if region == value else ''}>{escape(value)}</option>"
            for value in region_values
        )
        style_chip_options = "".join(
            (
                "<label class=\"chip-check\">"
                f"<input type=\"checkbox\" name=\"style_tag\" value=\"{escape(value)}\" {'checked' if value in style_tags else ''} />"
                f"<span>{escape(value)}</span>"
                "</label>"
            )
            for value in style_values
        )
        image_type_values = ["logo", "bottle", "process", "awards", "general"]
        image_type_options = "".join(
            (
                "<label class=\"chip-check\">"
                f"<input type=\"checkbox\" name=\"image_type\" value=\"{escape(value)}\" {'checked' if value in image_types else ''} />"
                f"<span>{escape(value)}</span>"
                "</label>"
            )
            for value in image_type_values
        )

        body = f"""
        <section class=\"hero\">
          <h1>Whisky Distillery Research Database</h1>
          <p class=\"muted\">Search by name, region, country, style tags, operating status, and confidence. Each distillery page includes collected images such as logos, bottles, and process visuals.</p>
        </section>

        <div class=\"grid grid-2\">
          <aside class=\"panel\">
            <h2>Search</h2>
            <form method=\"get\" action=\"/database\">
              <label>Name</label>
              <input name=\"name\" value=\"{escape(name)}\" />

              <label>Country</label>
              <select name=\"country\">
                <option value=\"\"></option>
                {options_country}
              </select>

              <label>Region</label>
              <select name=\"region\">
                <option value=\"\"></option>
                {options_region}
              </select>

              <label>Whisky Style</label>
              <input name=\"style\" value=\"{escape(style)}\" placeholder=\"peated, single malt, sherry cask...\" />

              <div class=\"filter-group\">
                <h3>Whisky Style Facets</h3>
                {style_chip_options}
              </div>

              <div class=\"filter-group\">
                <h3>Image Type</h3>
                {image_type_options}
              </div>

              <label>Operating Status</label>
              <select name=\"operating_status\">{options_operating}</select>

              <label>Website Confidence</label>
              <select name=\"confidence\">
                <option value=\"\"></option>
                {options_confidence}
              </select>

              <label><input type=\"checkbox\" name=\"has_images\" value=\"1\" {'checked' if has_images else ''} style=\"width:auto;margin-right:8px;\" />Only distilleries with images</label>

              <button type=\"submit\">Search</button>
            </form>
          </aside>

          <section class=\"panel\">
            <h2>Results ({len(rows)})</h2>
            <table class=\"results\">
              <thead>
                <tr>
                  <th>Distillery</th>
                  <th>Country</th>
                  <th>Region</th>
                  <th>Operating</th>
                  <th>Confidence</th>
                  <th>Styles</th>
                  <th>Images</th>
                </tr>
              </thead>
              <tbody>
                {results_html}
              </tbody>
            </table>
          </section>
        </div>
        """

        self.send_html(self.page_shell("Whisky Distillery DB", body, "/database"))

    def render_distillery(self, distillery_id: str) -> None:
        if self.static_mode:
            dataset = self.load_exported_dataset()
            if not dataset:
                self.send_error(500, "Static mode requires exported JSON dataset files in data/web")
                return

            distilleries_payload, _taxonomy_payload = dataset
            distillery_list = distilleries_payload.get("distilleries", [])
            if not isinstance(distillery_list, list):
                self.send_error(500, "Invalid distilleries JSON payload")
                return

            distillery = None
            for item in distillery_list:
                if not isinstance(item, dict):
                    continue
                if str(item.get("id")) == distillery_id or str(item.get("slug")) == distillery_id:
                    distillery = item
                    break

            if not distillery:
                self.send_error(404, "Distillery not found")
                return

            style_chips = "".join(
                f"<span class=\"chip\">{escape(style)}</span>"
                for style in distillery.get("styles", [])
                if isinstance(style, str)
            )

            image_cards = ""
            for image in distillery.get("images", []):
                if not isinstance(image, dict):
                    continue
                image_path = image.get("path", "")
                image_cards += f"""
                <figure>
                  <img src=\"/media/{escape(image_path)}\" alt=\"{escape(image.get('altText') or distillery.get('name', 'Distillery'))}\" loading=\"lazy\" />
                  <figcaption>
                    <strong>{escape(image.get('category') or 'general')}</strong><br />
                    {escape((image.get('altText') or '')[:120])}<br />
                    <a href=\"{escape(image.get('sourceUrl') or '')}\" target=\"_blank\" rel=\"noreferrer\">source</a>
                  </figcaption>
                </figure>
                """

            site_link = ""
            official_site = str(distillery.get("officialSite") or "")
            if official_site.startswith("http"):
                site_link = f"<p><a href=\"{escape(official_site)}\" target=\"_blank\" rel=\"noreferrer\">Official site</a></p>"

            body = f"""
            <section class=\"hero\">
              <p><a href=\"/database\">Back to database</a></p>
              <h1>{escape(str(distillery.get('name') or 'Distillery'))}</h1>
              <p class=\"muted\">{escape(str(distillery.get('country') or ''))} | {escape(str(distillery.get('region') or ''))} | {escape(str(distillery.get('section') or ''))}</p>
              {site_link}
              <div class=\"chips\">{style_chips}</div>
            </section>

            <div class=\"grid\" style=\"grid-template-columns: 1fr;\">
              <section class=\"panel\">
                <h2>Research Record</h2>
                <p><strong>Why study:</strong> {escape(str(distillery.get('whyStudy') or ''))}</p>
                <p><strong>Production/style focus:</strong> {escape(str(distillery.get('keyFocus') or ''))}</p>
                <p><strong>Study status:</strong> {escape(str(distillery.get('studyStatus') or ''))}</p>
                <p><strong>Operating status:</strong> {escape(str(distillery.get('operatingStatus') or ''))}</p>
                <p><strong>Website confidence:</strong> {escape(str(distillery.get('websiteConfidence') or ''))}</p>
                <p><strong>Notes:</strong> {escape(str(distillery.get('notes') or ''))}</p>
              </section>

              <section class=\"panel\">
                <h2>Collected Images ({int(distillery.get('imageCount') or 0)})</h2>
                <div class=\"images\">
                  {image_cards or '<p class="muted">No images collected for this distillery in exported dataset.</p>'}
                </div>
              </section>
            </div>
            """

            self.send_html(self.page_shell(str(distillery.get("name") or "Distillery"), body, ""))
            return

        if not distillery_id.isdigit():
            self.send_error(400, "Invalid distillery id")
            return

        with self.db() as conn:
            distillery = conn.execute(
                "SELECT * FROM distilleries WHERE id = ?",
                (int(distillery_id),),
            ).fetchone()
            if not distillery:
                self.send_error(404, "Distillery not found")
                return

            styles = conn.execute(
                """
                SELECT s.name
                FROM distillery_styles ds
                JOIN styles s ON s.id = ds.style_id
                WHERE ds.distillery_id = ?
                ORDER BY s.name
                """,
                (int(distillery_id),),
            ).fetchall()

            images = conn.execute(
                """
                SELECT local_path, category, alt_text, source_url, score
                FROM images
                WHERE distillery_id = ?
                ORDER BY score DESC, id ASC
                """,
                (int(distillery_id),),
            ).fetchall()

        style_chips = "".join(
            f"<span class=\"chip\">{escape(row['name'])}</span>" for row in styles
        )

        image_cards = "".join(
            f"""
            <figure>
              <img src=\"/media/{escape(row['local_path'])}\" alt=\"{escape(row['alt_text'] or distillery['name'])}\" loading=\"lazy\" />
              <figcaption>
                <strong>{escape(row['category'] or 'general')}</strong><br />
                {escape((row['alt_text'] or '')[:120])}<br />
                <a href=\"{escape(row['source_url'])}\" target=\"_blank\" rel=\"noreferrer\">source</a>
              </figcaption>
            </figure>
            """
            for row in images
        )

        site_link = ""
        if distillery["official_site"].startswith("http"):
            site_link = f"<p><a href=\"{escape(distillery['official_site'])}\" target=\"_blank\" rel=\"noreferrer\">Official site</a></p>"

        body = f"""
        <section class=\"hero\">
          <p><a href=\"/database\">Back to database</a></p>
          <h1>{escape(distillery['name'])}</h1>
          <p class=\"muted\">{escape(distillery['country'] or '')} | {escape(distillery['region'] or '')} | {escape(distillery['section'] or '')}</p>
          {site_link}
          <div class=\"chips\">{style_chips}</div>
        </section>

        <div class=\"grid\" style=\"grid-template-columns: 1fr;\">
          <section class=\"panel\">
            <h2>Research Record</h2>
            <p><strong>Why study:</strong> {escape(distillery['why_study'] or '')}</p>
            <p><strong>Production/style focus:</strong> {escape(distillery['key_focus'] or '')}</p>
            <p><strong>Study status:</strong> {escape(distillery['study_status'] or '')}</p>
            <p><strong>Operating status:</strong> {escape(distillery['operating_status'] or '')}</p>
            <p><strong>Website confidence:</strong> {escape(distillery['website_confidence'] or '')}</p>
            <p><strong>Notes:</strong> {escape(distillery['notes'] or '')}</p>
          </section>

          <section class=\"panel\">
            <h2>Collected Images ({len(images)})</h2>
            <div class=\"images\">
              {image_cards or '<p class="muted">No images collected yet for this distillery. Re-run the crawler with --crawl-images.</p>'}
            </div>
          </section>
        </div>
        """

        self.send_html(self.page_shell(distillery["name"], body, ""))

    def serve_media(self, path: str) -> None:
        rel = unquote(path[len("/media/") :]).strip("/")
        if ".." in rel:
            self.send_error(400, "Invalid path")
            return

        candidate_paths = [self.project_root / rel]
        if not rel.startswith("data/"):
            candidate_paths.append(self.project_root / "data" / rel)

        file_path = next(
            (candidate for candidate in candidate_paths if candidate.exists() and candidate.is_file()),
            None,
        )
        if file_path is None:
            self.send_error(404, "Image not found")
            return

        mime, _ = mimetypes.guess_type(str(file_path))
        payload = file_path.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local whisky distillery research website.")
    parser.add_argument("--db", default="data/distilleries.db", help="Path to SQLite database.")
    parser.add_argument("--web-data", default="data/web", help="Path to exported JSON web dataset directory.")
    parser.add_argument(
        "--static-mode",
        action="store_true",
        help="Run without SQLite lookups for distillery pages by using exported JSON dataset files.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind.")
    args = parser.parse_args()

    handler_class = DistillerySiteHandler
    handler_class.db_path = Path(args.db).resolve()
    handler_class.project_root = Path(".").resolve()
    handler_class.web_data_root = Path(args.web_data).resolve()
    handler_class.static_mode = args.static_mode
    handler_class.phase1_markdown_path = (handler_class.project_root / "PHASE_1_ORIENTATION_FOUNDATIONS_EXPANDED.md").resolve()
    handler_class.phase_pages = {
      "/phase-1": {
        "title": "Orientation and Foundations",
        "source": "PHASE_1_ORIENTATION_FOUNDATIONS_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_1_ORIENTATION_FOUNDATIONS_EXPANDED.md").resolve()),
      },
      "/phase-2": {
        "title": "History",
        "source": "PHASE_2_HISTORY_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_2_HISTORY_EXPANDED.md").resolve()),
      },
      "/phase-3": {
        "title": "Process",
        "source": "PHASE_3_PROCESS_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_3_PROCESS_EXPANDED.md").resolve()),
      },
      "/phase-4": {
        "title": "Regional Identity",
        "source": "PHASE_4_REGIONAL_IDENTITY_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_4_REGIONAL_IDENTITY_EXPANDED.md").resolve()),
      },
      "/phase-5": {
        "title": "Cultural Backgrounds and Social Importance",
        "source": "PHASE_5_CULTURAL_SOCIAL_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_5_CULTURAL_SOCIAL_EXPANDED.md").resolve()),
      },
      "/phase-6": {
        "title": "Distillery Operations, Safety, and Commercial Execution",
        "source": "PHASE_6_OPERATIONS_EXECUTION_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_6_OPERATIONS_EXECUTION_EXPANDED.md").resolve()),
      },
      "/phase-7": {
        "title": "Advanced Brand and Region Analysis",
        "source": "PHASE_7_ADVANCED_BRAND_REGION_ANALYSIS_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_7_ADVANCED_BRAND_REGION_ANALYSIS_EXPANDED.md").resolve()),
      },
    }
    handler_class.quiz_markdown_paths = [Path(item["markdown_path"]) for item in handler_class.phase_pages.values()]

    server = HTTPServer((args.host, args.port), handler_class)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "db": str(handler_class.db_path)}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
