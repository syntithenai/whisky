#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mimetypes
from pathlib import Path
import re
import sqlite3
from typing import TypedDict
from urllib.parse import parse_qs, unquote, urlparse


WHISKY_GLOSSARY: dict[str, str] = {
  "ABV": "Alcohol by volume, the percentage of alcohol in the liquid.",
  "Age statement": "A label declaration indicating the age of the youngest whisky in the bottle.",
  "Alcohol yield": "The amount of alcohol obtained from a given quantity of grain or wash.",
  "Angel's share": "The portion of spirit lost to evaporation during maturation.",
  "Aqua vitae": "Latin for 'water of life,' an early term associated with distilled spirits.",
  "Backset": "Stillage from a previous distillation added to a new mash in some American whiskey production.",
  "Barrel": "A common cask type, especially the American standard barrel.",
  "Batch": "A quantity of whisky prepared together for bottling.",
  "Blended grain": "A blend of grain whiskies from more than one distillery.",
  "Blended malt": "A blend of malt whiskies from more than one distillery.",
  "Blended whisky": "A whisky combining different whiskies, often malt and grain components.",
  "Bottled-in-bond": "An American designation meeting specific legal requirements for age, proof, season, and supervision.",
  "Bourbon": "An American whiskey made from at least 51% corn and matured in new charred oak containers.",
  "Cask": "A wooden vessel used for maturation.",
  "Cask finish": "A period of secondary maturation in a different cask type after initial aging.",
  "Cask strength": "Bottled at or near the strength in the cask, with little or no dilution.",
  "Char": "The carbonized layer created by exposing the inside of a barrel to flame.",
  "Char level": "A numbered measure of how heavily a cask interior has been charred, often affecting extraction and flavor profile.",
  "Chill filtration": "A process that removes certain compounds to reduce haze at low temperatures.",
  "Column still": "A continuous still used widely in grain whisky and American whiskey production.",
  "Congeners": "Chemical compounds other than ethanol that contribute aroma and flavor.",
  "Cooper": "A craftsperson who makes or repairs casks.",
  "Copper contact": "Interaction between spirit vapor or liquid and copper surfaces, often affecting sulfur compounds and spirit style.",
  "Distillate": "The spirit produced by distillation.",
  "Distillation": "Separation and concentration of alcohol and flavor-active compounds by heating and condensation.",
  "Distillery character": "The recurring style associated with a distillery's process and equipment.",
  "Dunnage warehouse": "A traditional low warehouse with earthen floors and casks stacked relatively low.",
  "Ester": "A class of compounds often associated with fruity aromas.",
  "Excise": "Tax imposed on goods such as alcohol.",
  "Ex-bourbon cask": "A cask previously used to age bourbon, very common in Scotch maturation.",
  "Feints": "Later-running distillation fractions often associated with tails and re-distilled later.",
  "Fermentation": "The conversion of sugars into alcohol and flavor compounds by yeast.",
  "Finish": "The aftertaste and lingering sensory impression after swallowing or spitting.",
  "First-fill": "A cask being used for whisky maturation for the first time after its previous contents.",
  "Floor malting": "Traditional malting by spreading grain across floors and turning it manually.",
  "Grain whisky": "Whisky made from grains other than only malted barley, often produced on column stills.",
  "Grist": "Milled malt prepared for mashing.",
  "Foreshots": "Early distillation fraction containing more volatile compounds.",
  "Heart": "The desired middle cut of a distillation run, collected for maturation.",
  "Hogshead": "A cask size commonly used in Scotch maturation, often made from rebuilt bourbon barrels.",
  "Independent bottler": "A company that bottles whisky from distilleries it may not own.",
  "Islay": "A Scottish island region famous for several influential peated whiskies.",
  "Japanese whisky": "Whisky produced in Japan according to evolving industry standards and expectations.",
  "Kilning": "Drying germinated grain to stop malting and shape flavor.",
  "Lactic notes": "Creamy, yogurt-like, or tangy notes associated with some fermentations.",
  "Lauter": "To separate sweet wort from grain solids.",
  "Low wines": "The product of the first distillation in many pot still systems.",
  "Lyne arm": "The pipe carrying vapor from the still neck to the condenser.",
  "Malt": "Grain, usually barley, that has been germinated and dried.",
  "Malt whisky": "Whisky made from malted barley, especially in Scotch terminology.",
  "Mash bill": "The recipe of grains used in an American whiskey mash.",
  "Mash tun": "Vessel in which milled grain and hot water are mixed.",
  "Maturation": "The process of aging spirit in wood.",
  "New make": "Freshly distilled spirit before aging.",
  "Mouthfeel": "The textural impression of a whisky in the mouth.",
  "NAS": "Non-age-statement whisky, bottled without a declared age.",
  "New charred oak": "Fresh oak container charred on the inside, required for bourbon maturation.",
  "Non-chill-filtered": "Bottled without chill filtration, typically retaining more fatty acids and texture but with possible haze at low temperatures.",
  "Nose": "The aroma perceived from a whisky before tasting.",
  "Oak lactones": "Compounds from oak contributing woody, coconut-like, or sweet notes.",
  "Oxidation": "Chemical reactions involving oxygen that can alter spirit during maturation.",
  "Palate": "The flavors and textures perceived while tasting.",
  "Peat": "Partially decayed vegetation used as a fuel source in some malting processes.",
  "Phenols": "Compounds associated with smoke, medicinal notes, tar, and related aromas in peated whisky.",
  "Pot still": "A batch still associated with many malt and pot still whiskey traditions.",
  "Proof": "A measure of alcohol strength, especially in American labeling.",
  "Puncheon": "A large cask type used for maturation.",
  "Refill cask": "A cask that has already been used for whisky maturation one or more times.",
  "Reflux": "Condensation and re-vaporization inside the still, often affecting spirit lightness.",
  "Ricked warehouse": "A multi-level warehouse used widely in American whiskey aging.",
  "Rye whiskey": "Whiskey made with a legally defined rye content, especially in the United States.",
  "Single barrel": "Whisky bottled from one individual barrel or cask.",
  "Single cask": "Whisky bottled from one individual cask.",
  "Single grain": "Grain whisky produced at one distillery.",
  "Single malt": "Malt whisky produced at one distillery.",
  "Single pot still": "Irish whiskey made at one distillery from malted and unmalted barley in pot stills.",
  "Small batch": "A loosely defined term suggesting limited batch blending.",
  "Spirit safe": "Locked glass-fronted box through which a distiller monitors spirit flow and cuts.",
  "Straight whiskey": "An American legal designation involving aging and other requirements.",
  "Sulfur notes": "Aromas reminiscent of struck match, rubber, cabbage, or meat stock depending on context and intensity.",
  "Tannin": "Wood-derived compounds contributing dryness, structure, or bitterness.",
  "Terroir": "A contested concept in whisky, usually referring to place-based agricultural influence on character.",
  "Triple distillation": "Distilling spirit three times rather than twice, common in some traditions but not universal.",
  "Unpeated": "Made without significant peat smoke influence in malting.",
  "Vatting": "Combining multiple casks together, often before bottling.",
  "Virgin oak": "An oak cask not previously used to mature another beverage.",
  "Warehouse aging": "The maturation of casks under specific storage conditions over time.",
  "Wash": "Fermented liquid ready for distillation.",
  "Washback": "Vessel used for fermentation of the wort.",
  "Wort": "Sugary liquid extracted from the mash before fermentation.",
}


class CrawlSummary(TypedDict):
  page_count: int
  captured_count: int
  earliest_capture: str
  latest_capture: str
  total_words: int
  avg_words: float
  total_keywords: int
  keywords_per_page: float
  keyword_density: float
  top_keywords: list[tuple[str, int]]

class DistillerySiteHandler(BaseHTTPRequestHandler):
    db_path: Path
    project_root: Path
    web_data_root: Path
    static_mode: bool
    base_path: str
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

        if parsed.path == "/resources":
          self.render_resources()
          return

        if parsed.path.startswith("/resources/"):
            rest = parsed.path[len("/resources/"):]
            parts = [p for p in rest.split("/") if p]
            if len(parts) == 1:
                self.render_resource_detail(parts[0])
                return
            if len(parts) == 3 and parts[1] == "pages":
                self.render_resource_page_raw(parts[0], parts[2])
                return

        if parsed.path == "/privacy":
            self.render_privacy()
            return

        if parsed.path == "/glossary":
            self.render_glossary()
            return

        if parsed.path == "/glossary/data":
            self.render_glossary_data()
            return

        if parsed.path.startswith("/distillery/"):
            distillery_id = parsed.path.split("/")[-1]
            self.render_distillery(distillery_id)
            return

        if parsed.path == "/products":
            self.render_products()
            return

        if parsed.path.startswith("/products/"):
            product_slug = parsed.path[len("/products/"):]
            if product_slug and "/" not in product_slug:
                self.render_product_detail(product_slug)
                return

        self.send_error(404, "Not found")

    def render_resources(self) -> None:
        dataset = self.load_exported_resources_dataset()
        if not dataset:
            self.send_error(500, "Resources export files are missing. Run scripts/export_resources_json.py.")
            return
        self.render_resources_json_app()

    def load_exported_resources_dataset(self) -> tuple[dict[str, object], dict[str, object]] | None:
        resources_path = self.web_data_root / "resources.json"
        taxonomy_path = self.web_data_root / "resources-taxonomy.json"
        if not resources_path.exists() or not taxonomy_path.exists():
            return None

        try:
            resources_payload = json.loads(resources_path.read_text(encoding="utf-8"))
            taxonomy_payload = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(resources_payload, dict) or not isinstance(taxonomy_payload, dict):
            return None

        return resources_payload, taxonomy_payload

    def render_resources_json_app(self) -> None:
        body = """
        <section class=\"hero\">
          <h1>Whisky Education Resources</h1>
          <p class=\"muted\">Filter curated sources by category, focus area, audience, region, cost, and confidence.</p>
        </section>

        <div class=\"grid grid-2\">
          <aside class=\"panel\">
            <h2>Filters</h2>
            <form id=\"resourcesFilterForm\">
              <div class=\"quiz-actions\" style=\"margin-bottom:12px;\">
                <button type=\"submit\">Search</button>
                <button id=\"resetResourceFilters\" type=\"button\" class=\"button-secondary\">Reset</button>
              </div>

              <label>Search</label>
              <input id=\"rQuery\" name=\"q\" placeholder=\"name, notes, tags...\" />

              <label>Category</label>
              <select id=\"rCategory\" name=\"category\"><option value=\"\"></option></select>

              <label>Focus Area</label>
              <select id=\"rFocus\" name=\"focus\"><option value=\"\"></option></select>

              <label>Audience</label>
              <select id=\"rAudience\" name=\"audience\"><option value=\"\"></option></select>

              <label>Region Scope</label>
              <select id=\"rRegion\" name=\"region\"><option value=\"\"></option></select>

              <label>Cost</label>
              <select id=\"rCost\" name=\"cost\"><option value=\"\"></option></select>

              <label>Small Distillery Relevance</label>
              <select id=\"rRelevance\" name=\"relevance\"><option value=\"\"></option></select>

              <label>Source Confidence</label>
              <select id=\"rConfidence\" name=\"confidence\"><option value=\"\"></option></select>

              <label>Tag</label>
              <select id=\"rTag\" name=\"tag\"><option value=\"\"></option></select>
            </form>
          </aside>

          <section class=\"panel\">
            <h2 id=\"resourcesHeading\">Resources</h2>
            <table class=\"results\">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Category</th>
                  <th>Focus</th>
                  <th>Region</th>
                  <th>Audience</th>
                  <th>Cost</th>
                  <th>Relevance</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody id=\"resourcesBody\"></tbody>
            </table>
            <p id=\"resourcesStatus\" class=\"muted\" style=\"margin-top:12px;\"></p>
          </section>
        </div>

        <script>
          (function () {
            const form = document.getElementById('resourcesFilterForm');
            const resultsBody = document.getElementById('resourcesBody');
            const heading = document.getElementById('resourcesHeading');
            const status = document.getElementById('resourcesStatus');
            const resetBtn = document.getElementById('resetResourceFilters');

            const fields = {
              q: document.getElementById('rQuery'),
              category: document.getElementById('rCategory'),
              focus: document.getElementById('rFocus'),
              audience: document.getElementById('rAudience'),
              region: document.getElementById('rRegion'),
              cost: document.getElementById('rCost'),
              relevance: document.getElementById('rRelevance'),
              confidence: document.getElementById('rConfidence'),
              tag: document.getElementById('rTag'),
            };

            if (!form || !resultsBody || !heading || !status) {
              return;
            }

            function htmlEscape(text) {
              return String(text || '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;');
            }

            function optionHtml(value, selectedValue) {
              return '<option value="' + htmlEscape(value) + '"' + (value === selectedValue ? ' selected' : '') + '>' + htmlEscape(value) + '</option>';
            }

            function getStateFromUrl() {
              const params = new URLSearchParams(window.location.search);
              return {
                q: params.get('q') || '',
                category: params.get('category') || '',
                focus: params.get('focus') || '',
                audience: params.get('audience') || '',
                region: params.get('region') || '',
                cost: params.get('cost') || '',
                relevance: params.get('relevance') || '',
                confidence: params.get('confidence') || '',
                tag: params.get('tag') || '',
              };
            }

            function writeStateToUrl(state) {
              const params = new URLSearchParams();
              Object.keys(state).forEach((key) => {
                if (state[key]) {
                  params.set(key, state[key]);
                }
              });
              const query = params.toString();
              const nextUrl = query ? whiskyPath('/resources') + '?' + query : whiskyPath('/resources');
              window.history.replaceState({}, '', nextUrl);
            }

            function readFormState() {
              return {
                q: fields.q.value.trim(),
                category: fields.category.value.trim(),
                focus: fields.focus.value.trim(),
                audience: fields.audience.value.trim(),
                region: fields.region.value.trim(),
                cost: fields.cost.value.trim(),
                relevance: fields.relevance.value.trim(),
                confidence: fields.confidence.value.trim(),
                tag: fields.tag.value.trim(),
              };
            }

            function applyStateToForm(state, taxonomy) {
              fields.q.value = state.q;
              fields.category.innerHTML = '<option value=""></option>' + (taxonomy.categories || []).map((v) => optionHtml(v, state.category)).join('');
              fields.focus.innerHTML = '<option value=""></option>' + (taxonomy.focusAreas || []).map((v) => optionHtml(v, state.focus)).join('');
              fields.audience.innerHTML = '<option value=""></option>' + (taxonomy.audiences || []).map((v) => optionHtml(v, state.audience)).join('');
              fields.region.innerHTML = '<option value=""></option>' + (taxonomy.regionScopes || []).map((v) => optionHtml(v, state.region)).join('');
              fields.cost.innerHTML = '<option value=""></option>' + (taxonomy.costs || []).map((v) => optionHtml(v, state.cost)).join('');
              fields.relevance.innerHTML = '<option value=""></option>' + (taxonomy.relevanceLevels || []).map((v) => optionHtml(v, state.relevance)).join('');
              fields.confidence.innerHTML = '<option value=""></option>' + (taxonomy.sourceConfidenceLevels || []).map((v) => optionHtml(v, state.confidence)).join('');
              fields.tag.innerHTML = '<option value=""></option>' + (taxonomy.tags || []).map((v) => optionHtml(v, state.tag)).join('');
            }

            function matchesState(item, state) {
              if (state.category && item.category !== state.category) return false;
              if (state.focus && item.focusArea !== state.focus) return false;
              if (state.audience && item.audience !== state.audience) return false;
              if (state.region && item.regionScope !== state.region) return false;
              if (state.cost && item.cost !== state.cost) return false;
              if (state.relevance && item.smallDistilleryRelevance !== state.relevance) return false;
              if (state.confidence && item.sourceConfidence !== state.confidence) return false;
              if (state.tag) {
                const tags = Array.isArray(item.tags) ? item.tags : [];
                if (!tags.includes(state.tag)) return false;
              }

              if (state.q) {
                const haystack = [
                  item.name,
                  item.notes,
                  item.category,
                  item.focusArea,
                  item.regionScope,
                  item.audience,
                  (Array.isArray(item.tags) ? item.tags.join(' ') : ''),
                ].join(' ').toLowerCase();
                if (!haystack.includes(state.q.toLowerCase())) return false;
              }

              return true;
            }

            function renderRows(items) {
              const rows = items.map((item) => {
                const notes = item.notes ? '<div class="muted" style="max-width:480px;">' + htmlEscape(item.notes) + '</div>' : '';
                const detailHref = item.slug ? whiskyPath('/resources/' + encodeURIComponent(item.slug)) : '';
                const detailLink = item.slug ? '<a href="' + detailHref + '">' + htmlEscape(item.name || '') + '</a>' : htmlEscape(item.name || '');
                const extLink = item.url ? ' <a href="' + htmlEscape(item.url) + '" target="_blank" rel="noreferrer" title="Visit site" style="font-size:11px;color:var(--muted);">&#8599;</a>' : '';
                return '<tr>' +
                  '<td>' + detailLink + extLink + notes + '</td>' +
                  '<td>' + htmlEscape(item.category || '') + '</td>' +
                  '<td>' + htmlEscape(item.focusArea || '') + '</td>' +
                  '<td>' + htmlEscape(item.regionScope || '') + '</td>' +
                  '<td>' + htmlEscape(item.audience || '') + '</td>' +
                  '<td>' + htmlEscape(item.cost || '') + '</td>' +
                  '<td>' + htmlEscape(item.smallDistilleryRelevance || '') + '</td>' +
                  '<td>' + htmlEscape(item.sourceConfidence || '') + '</td>' +
                '</tr>';
              }).join('');

              resultsBody.innerHTML = rows || '<tr><td colspan="8" class="muted">No resources match the current filters.</td></tr>';
              heading.textContent = 'Resources (' + items.length + ')';
            }

            async function init() {
              const [resourcesResp, taxonomyResp, manifestResp] = await Promise.all([
                fetch(whiskyPath('/data-web/resources.json')),
                fetch(whiskyPath('/data-web/resources-taxonomy.json')),
                fetch(whiskyPath('/data-web/resources-manifest.json')).catch(() => null),
              ]);

              if (!resourcesResp.ok || !taxonomyResp.ok) {
                throw new Error('Unable to load resources dataset exports.');
              }

              const resourcesPayload = await resourcesResp.json();
              const taxonomyPayload = await taxonomyResp.json();
              const resources = Array.isArray(resourcesPayload.resources) ? resourcesPayload.resources : [];
              const initialState = getStateFromUrl();
              applyStateToForm(initialState, taxonomyPayload || {});

              function refresh() {
                const state = readFormState();
                writeStateToUrl(state);
                renderRows(resources.filter((item) => matchesState(item, state)));
              }

              form.addEventListener('submit', function (event) {
                event.preventDefault();
                refresh();
              });

              form.addEventListener('change', refresh);

              if (resetBtn) {
                resetBtn.addEventListener('click', function () {
                  applyStateToForm({
                    q: '', category: '', focus: '', audience: '', region: '', cost: '', relevance: '', confidence: '', tag: '',
                  }, taxonomyPayload || {});
                  refresh();
                });
              }

              renderRows(resources.filter((item) => matchesState(item, initialState)));

              if (manifestResp && manifestResp.ok) {
                const manifest = await manifestResp.json();
                status.textContent = 'Resources version ' + (manifest.schemaVersion || 'unknown') + ' | Records: ' + (manifest.recordCount || resources.length);
              } else {
                status.textContent = 'Resources loaded from ' + whiskyPath('/data-web/resources*.json');
              }
            }

            init().catch(function (error) {
              resultsBody.innerHTML = '<tr><td colspan="8">Unable to load resources. ' + htmlEscape(error.message || 'Unknown error') + '</td></tr>';
            });
          }());
        </script>
        """

        self.send_html(self.page_shell("Whisky Resources", body, "/resources"))

    @staticmethod
    def _page_label(stem: str) -> str:
        """Convert a file stem like 'discover-scotch-how-its-made' to 'Discover Scotch How Its Made'."""
        return " ".join(w.capitalize() for w in stem.replace("-", " ").replace("_", " ").split())

    def _summarize_crawl_pages(self, pages: list[Path]) -> CrawlSummary:
        keyword_counter: Counter[str] = Counter()
        captured_datetimes: list[datetime] = []
        captured_count = 0
        total_keywords = 0
        total_words = 0

        for page in pages:
            try:
                text = page.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            total_words += len(re.findall(r"[A-Za-z0-9']+", text))

            captured_match = re.search(r"^\s*(?:-\s*)?Captured:\s*(.+)$", text, re.MULTILINE)
            if captured_match:
                captured_count += 1
                raw_dt = captured_match.group(1).strip()
                try:
                    captured_datetimes.append(datetime.fromisoformat(raw_dt.replace("Z", "+00:00")))
                except ValueError:
                    pass

            keywords_match = re.search(r"^\s*(?:-\s*)?Keywords:\s*(.+)$", text, re.MULTILINE)
            if keywords_match:
                keywords = [kw.strip().lower() for kw in keywords_match.group(1).split(",") if kw.strip()]
                total_keywords += len(keywords)
                keyword_counter.update(keywords)

        page_count = len(pages)
        avg_words = (total_words / page_count) if page_count else 0.0
        keywords_per_page = (total_keywords / page_count) if page_count else 0.0
        keyword_density = (total_keywords * 1000.0 / total_words) if total_words else 0.0

        earliest_capture = ""
        latest_capture = ""
        if captured_datetimes:
            earliest_capture = min(captured_datetimes).strftime("%Y-%m-%d")
            latest_capture = max(captured_datetimes).strftime("%Y-%m-%d")

        return {
            "page_count": page_count,
            "captured_count": captured_count,
            "earliest_capture": earliest_capture,
            "latest_capture": latest_capture,
            "total_words": total_words,
            "avg_words": avg_words,
            "total_keywords": total_keywords,
            "keywords_per_page": keywords_per_page,
            "keyword_density": keyword_density,
            "top_keywords": keyword_counter.most_common(12),
        }

    def render_resource_detail(self, slug: str) -> None:
        resources_path = self.web_data_root / "resources.json"
        if not resources_path.exists():
            self.send_error(404, "Resources dataset not found")
            return
        try:
            resources_payload = json.loads(resources_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.send_error(500, "Failed to load resources dataset")
            return

        resource = next((r for r in resources_payload.get("resources", []) if r.get("slug") == slug), None)
        if resource is None:
            self.send_error(404, f"Resource '{escape(slug)}' not found")
            return

        crawl_dir = self.project_root / "data" / "crawl_markdown" / f"resource-{slug}"
        pages: list[Path] = []
        if crawl_dir.exists() and crawl_dir.is_dir():
            pages = sorted(
                [f for f in crawl_dir.iterdir() if f.is_file() and f.suffix == ".md"],
                key=lambda f: (0 if f.stem == "home" else 1, f.name),
            )
        crawl_summary = self._summarize_crawl_pages(pages)

        name = escape(str(resource.get("name") or slug))
        url = escape(str(resource.get("url") or ""))
        category = escape(str(resource.get("category") or ""))
        focus = escape(str(resource.get("focusArea") or ""))
        audience = escape(str(resource.get("audience") or ""))
        region = escape(str(resource.get("regionScope") or ""))
        cost = escape(str(resource.get("cost") or ""))
        relevance = escape(str(resource.get("smallDistilleryRelevance") or ""))
        confidence = escape(str(resource.get("sourceConfidence") or ""))
        notes = escape(str(resource.get("notes") or ""))
        tags = resource.get("tags") or []

        meta_rows = ""
        for label, value in [
            ("Category", category),
            ("Focus Area", focus),
            ("Audience", audience),
            ("Region", region),
            ("Cost", cost),
            ("Small Distillery Relevance", relevance),
            ("Source Confidence", confidence),
        ]:
            if value:
                meta_rows += (
                    f'<div class="record-row">'
                    f'<p class="record-label">{label}</p>'
                    f'<p class="record-value">{value}</p>'
                    f'</div>'
                )
        if tags:
            chips = "".join(f'<li>{escape(str(t))}</li>' for t in tags)
            meta_rows += (
                f'<div class="record-row">'
                f'<p class="record-label">Tags</p>'
                f'<p class="record-value"><ul class="note-chip-list">{chips}</ul></p>'
                f'</div>'
            )
        if notes:
            meta_rows += (
                f'<div class="record-row">'
                f'<p class="record-label">Notes</p>'
                f'<p class="record-value">{notes}</p>'
                f'</div>'
            )

        crawl_rows = ""
        if pages:
          crawl_rows += (
            f'<div class="record-row">'
            f'<p class="record-label">Pages Crawled</p>'
            f'<p class="record-value">{int(crawl_summary["page_count"])}</p>'
            f'</div>'
          )
          crawl_rows += (
            f'<div class="record-row">'
            f'<p class="record-label">Capture Window</p>'
            f'<p class="record-value">'
            f'{escape(str(crawl_summary["earliest_capture"] or "Unknown"))} to {escape(str(crawl_summary["latest_capture"] or "Unknown"))}'
            f' ({int(crawl_summary["captured_count"])} pages with capture timestamp)'
            f'</p>'
            f'</div>'
          )
          crawl_rows += (
            f'<div class="record-row">'
            f'<p class="record-label">Keyword Density</p>'
            f'<p class="record-value">'
            f'{float(crawl_summary["keywords_per_page"]):.1f} keywords per page '
            f'({float(crawl_summary["keyword_density"]):.2f} per 1k words)'
            f'</p>'
            f'</div>'
          )
          crawl_rows += (
            f'<div class="record-row">'
            f'<p class="record-label">Word Volume</p>'
            f'<p class="record-value">'
            f'{int(crawl_summary["total_words"]):,} words analyzed '
            f'({float(crawl_summary["avg_words"]):.0f} avg per page)'
            f'</p>'
            f'</div>'
          )
          top_keywords = crawl_summary.get("top_keywords") or []
          if top_keywords:
            chips = "".join(
              f'<li>{escape(keyword)} ({count})</li>'
              for keyword, count in top_keywords
            )
            crawl_rows += (
              f'<div class="record-row">'
              f'<p class="record-label">Top Crawl Keywords</p>'
              f'<p class="record-value"><ul class="note-chip-list">{chips}</ul></p>'
              f'</div>'
            )

        crawl_summary_panel = ""
        if crawl_rows:
          crawl_summary_panel = (
            '<div class="panel" style="margin-top:18px;">'
            '<h2 style="margin-top:0;">Crawl Summary</h2>'
            f'<div class="record-list">{crawl_rows}</div>'
            '</div>'
          )

        tab_btns = ""
        tab_section = ""
        if pages:
            for i, page in enumerate(pages):
                label = self._page_label(page.stem)
                active_cls = " res-tab-active" if i == 0 else ""
                tab_btns += (
                    f'<button class="res-tab{active_cls}" '
                    f'data-page="{escape(page.name)}" '
                    f'role="tab" aria-selected="{"true" if i == 0 else "false"}">'
                    f'{escape(label)}</button>'
                )
            slug_js = json.dumps(slug)
            tab_section = f"""
<div class="panel" style="margin-top:18px;">
  <h2 style="margin-top:0;">Crawled Pages ({len(pages)})</h2>
  <style>
    .res-tab-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }}
    .res-tab {{
      border: 1px solid #cdb79f;
      background: #f6ecdb;
      color: #5d4a37;
      border-radius: 999px;
      padding: 5px 12px;
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
    }}
    .res-tab:hover {{ background: #ecdabb; }}
    .res-tab.res-tab-active {{
      background: #a3572a;
      color: #fff;
      border-color: #a3572a;
    }}
    .res-tab-content {{
      min-height: 120px;
    }}
    .res-tab-content.loading::after {{
      content: 'Loading…';
      color: var(--muted);
      font-size: 13px;
    }}
  </style>
  <div class="res-tab-list" role="tablist" id="resTabList">{tab_btns}</div>
  <div class="res-tab-content markdown-panel" id="resTabContent"></div>
</div>
<script>
  (function () {{
    const slug = {slug_js};
    const tabList = document.getElementById('resTabList');
    const content = document.getElementById('resTabContent');
    if (!tabList || !content) return;
    const tabs = Array.from(tabList.querySelectorAll('.res-tab'));
    const cache = {{}};

    async function loadTab(filename) {{
      if (!cache[filename]) {{
        content.classList.add('loading');
        content.innerHTML = '';
        try {{
          const resp = await fetch(whiskyPath('/resources/' + encodeURIComponent(slug) + '/pages/' + encodeURIComponent(filename)));
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          cache[filename] = await resp.text();
        }} catch (err) {{
          cache[filename] = 'Unable to load page: ' + (err.message || 'unknown error');
        }}
        content.classList.remove('loading');
      }}
      content.innerHTML = markdownToHtml(cache[filename]);
    }}

    tabs.forEach(function (tab) {{
      tab.addEventListener('click', function () {{
        tabs.forEach(function (t) {{
          t.classList.remove('res-tab-active');
          t.setAttribute('aria-selected', 'false');
        }});
        tab.classList.add('res-tab-active');
        tab.setAttribute('aria-selected', 'true');
        loadTab(tab.dataset.page);
      }});
    }});

    if (tabs.length > 0) {{
      loadTab(tabs[0].dataset.page);
    }}
  }}());
</script>"""
        else:
            tab_section = '<p class="muted" style="margin-top:18px;">No crawl data available for this resource.</p>'

        ext_link = f'<a href="{url}" target="_blank" rel="noreferrer" style="display:inline-block;margin-top:10px;color:#7f3318;">Visit Site &#8599;</a>' if url else ""
        subtitle_parts = [p for p in [category, focus, region] if p]
        subtitle = " &middot; ".join(subtitle_parts)

        body = f"""
<nav style="margin-bottom:14px;font-size:13px;">
  <a href="{self.app_href('/resources')}">&larr; All Resources</a>
</nav>
<section class="hero">
  <h1 style="margin:0 0 6px 0;">{name}</h1>
  {f'<p class="muted" style="margin:0 0 8px 0;">{subtitle}</p>' if subtitle else ''}
  {ext_link}
</section>
<div class="panel" style="margin-top:18px;">
  <h2 style="margin-top:0;">Resource Details</h2>
  <div class="record-list">{meta_rows}</div>
</div>
{crawl_summary_panel}
{tab_section}
"""
        self.send_html(self.page_shell(f"{name} — Whisky Resources", body, "/resources"))

    def render_resource_page_raw(self, slug: str, filename: str) -> None:
        # Validate filename to prevent path traversal
        if "/" in filename or "\\" in filename or not filename.endswith(".md"):
            self.send_error(400, "Invalid page filename")
            return
        crawl_dir = self.project_root / "data" / "crawl_markdown" / f"resource-{slug}"
        file_path = crawl_dir / filename
        # Ensure resolved path is within the crawl dir
        try:
            file_path = file_path.resolve()
            crawl_dir_resolved = crawl_dir.resolve()
            file_path.relative_to(crawl_dir_resolved)
        except (ValueError, OSError):
            self.send_error(400, "Invalid path")
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "Page not found")
            return
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

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
          link_map[normalized] = self.app_href(f"/distillery/{row['id']}")

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

    def app_href(self, path: str) -> str:
      normalized_path = path if path.startswith("/") else f"/{path}"
      base_path = self.base_path.rstrip("/")
      if not base_path:
        return normalized_path
      return f"{base_path}{normalized_path}"

    def nav_link(self, href: str, label: str, current_path: str) -> str:
        cls = "top-link active" if href == current_path else "top-link"
        return f"<a class=\"{cls}\" href=\"{self.app_href(href)}\">{escape(label)}</a>"

    def site_footer(self) -> str:
      privacy_href = self.app_href("/privacy")
      return f"""
      <footer class="site-footer">
        <p class="site-footer-copy">Copyleft Steve Ryan &lt;<a href="mailto:syntithenai@gmail.com">syntithenai@gmail.com</a>&gt; · <a href="https://github.com/syntithenai/whisky" target="_blank" rel="noreferrer">Github</a> · <a href="{privacy_href}">Privacy Policy</a></p>
      </footer>
      """

    def nav_lessons_dropdown(self, current_path: str) -> str:
      phase_entries = sorted(
        self.phase_pages.items(),
        key=lambda item: int(item[0].split("-")[-1]),
      )
      phase_links = "".join(
        f"<a class=\"top-dropdown-item\" href=\"{escape(self.app_href(path))}\">{escape(page['title'])}</a>"
        for path, page in phase_entries
      )
      active = current_path in {"/whisky-lessons", "/the-whisky-course"} or current_path in self.phase_pages
      trigger_cls = "top-link active" if active else "top-link"
      return (
        "<div class=\"top-dropdown\">"
        f"<a class=\"{trigger_cls}\" href=\"{self.app_href('/whisky-lessons')}\">Whisky Lessons</a>"
        "<div class=\"top-dropdown-menu\">"
        f"{phase_links}"
        "</div>"
        "</div>"
      )

    def nav_playlist_control(self) -> str:
      return (
        "<div class=\"playlist-control\" id=\"playlistControl\">"
        "<button id=\"playlistPlayToggle\" class=\"playlist-main-btn\" "
        "data-state=\"paused\" title=\"Play whisky playlist\" aria-label=\"Play whisky playlist\">"
        "<span class=\"playlist-main-icon\" aria-hidden=\"true\">&#9654;</span>"
        "</button>"
        "<button id=\"playlistDropdownToggle\" class=\"playlist-arrow-btn\" "
        "aria-label=\"Show whisky song list\" aria-expanded=\"false\" aria-controls=\"playlistDropdown\">"
        "&#9660;"
        "</button>"
        "<div id=\"playlistDropdown\" class=\"playlist-dropdown\" hidden>"
        "<div class=\"playlist-dropdown-top\">"
        "<div class=\"playlist-now-playing\" id=\"playlistNowPlaying\">Whisky Playlist</div>"
        "<div class=\"playlist-skip-controls\">"
        "<button id=\"playlistPrevBtn\" class=\"playlist-skip-btn\" type=\"button\" aria-label=\"Previous song\" title=\"Previous song\">&#9664;</button>"
        "<button id=\"playlistNextBtn\" class=\"playlist-skip-btn\" type=\"button\" aria-label=\"Next song\" title=\"Next song\">&#9654;</button>"
        "</div>"
        "</div>"
        "<div class=\"playlist-seek-row\">"
        "<span class=\"seek-label\" id=\"seekCurrentTime\">0:00</span>"
        "<input type=\"range\" id=\"playlistSeek\" min=\"0\" max=\"100\" value=\"0\" step=\"1\" "
        "aria-label=\"Song position\" class=\"playlist-seek\">"
        "<span class=\"seek-label\" id=\"seekDuration\">0:00</span>"
        "</div>"
        "<div id=\"playlistSongList\" class=\"playlist-song-list\" role=\"listbox\" aria-label=\"Whisky song list\"></div>"
        "</div>"
        "</div>"
      )

    def page_shell(self, title: str, body: str, current_path: str) -> str:
        base_path_js = json.dumps(self.base_path.rstrip("/"))
        topbar_image = escape(self.app_href("/media/data/images_549173890-1920w.webp"))
        nav = "".join(
            [
                self.nav_link("/", "Home", current_path),
          self.nav_lessons_dropdown(current_path),
          self.nav_link("/quizzes", "Quizzes", current_path),
            self.nav_link("/resources", "Resources", current_path),
                self.nav_link("/glossary", "Glossary", current_path),
                self.nav_link("/database", "Distilleries", current_path),
                self.nav_link("/products", "Products", current_path),
                self.nav_playlist_control(),
            ]
        )
        footer = self.site_footer()

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
      background:
        linear-gradient(rgba(23, 12, 7, 0.72), rgba(23, 12, 7, 0.72)),
        url('{topbar_image}') center/cover;
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
    .site-footer {{
      margin: 28px auto 0;
      padding: 22px 20px 28px;
      max-width: 1200px;
      border-top: 1px solid #b99874;
      background: rgba(255, 249, 239, 0.94);
    }}
    .site-footer-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 18px;
      margin-bottom: 14px;
    }}
    .footer-block h2 {{
      margin: 0 0 10px 0;
      font-size: 16px;
    }}
    .footer-block p {{
      margin: 0 0 8px 0;
      line-height: 1.5;
    }}
    .site-footer-copy {{
      margin: 0;
      padding-top: 12px;
      border-top: 1px solid #d4bf9f;
      color: var(--muted);
      font-size: 13px;
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
    .record-list {{ display: grid; gap: 12px; }}
    .record-row {{
      display: grid;
      grid-template-columns: minmax(150px, 220px) 1fr;
      gap: 10px 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(212, 191, 159, 0.7);
    }}
    .record-row:last-child {{ padding-bottom: 0; border-bottom: 0; }}
    .record-label {{
      margin: 0;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .record-value {{ margin: 0; line-height: 1.6; }}
    .research-notes {{
      display: grid;
      gap: 10px;
      margin-top: 12px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.48);
      border: 1px solid rgba(212, 191, 159, 0.8);
      border-radius: 10px;
    }}
    .research-note {{
      display: grid;
      grid-template-columns: minmax(130px, 210px) 1fr;
      gap: 8px 14px;
      align-items: start;
    }}
    .research-note-label {{ margin: 0; color: #5b4638; font-size: 12px; font-weight: 700; }}
    .research-note-value {{ margin: 0; line-height: 1.55; word-break: break-word; }}
    .note-list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }}
    .note-list li {{ margin: 0; }}
    .note-chip-list {{ list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }}
    .note-chip-list li {{
      margin: 0;
      padding: 4px 9px;
      border-radius: 999px;
      border: 1px solid #d3b897;
      background: #f3e6d1;
      font-size: 12px;
    }}
    .note-raw {{ white-space: pre-wrap; }}
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
      .record-row,
      .research-note {{ grid-template-columns: 1fr; }}
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
    /* --- Whisky Playlist Player --- */
    .playlist-control {{
      position: relative;
      display: inline-flex;
      align-items: center;
      margin-left: 8px;
    }}
    .playlist-main-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border: 1px solid #82604e;
      border-radius: 8px 0 0 8px;
      background: transparent;
      color: var(--topInk);
      cursor: pointer;
      font-size: 15px;
      padding: 0;
    }}
    .playlist-main-btn:hover {{ background: var(--topHover); }}
    .playlist-arrow-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      height: 36px;
      border: 1px solid #82604e;
      border-left: none;
      border-radius: 0 8px 8px 0;
      background: transparent;
      color: var(--topInk);
      cursor: pointer;
      font-size: 10px;
      padding: 0;
    }}
    .playlist-arrow-btn:hover {{ background: var(--topHover); }}
    .playlist-dropdown {{
      position: absolute;
      top: calc(100% + 8px);
      right: 0;
      min-width: 300px;
      max-width: 340px;
      background: #2f1d14;
      border: 1px solid #5a3a2b;
      border-radius: 12px;
      padding: 12px;
      z-index: 100;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      color: var(--topInk);
    }}
    .playlist-now-playing {{
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 10px;
      color: #f8c67e;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .playlist-dropdown-top {{
      display: flex;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .playlist-dropdown-top .playlist-now-playing {{
      margin-bottom: 0;
      flex: 1;
      min-width: 0;
    }}
    .playlist-skip-controls {{
      display: inline-flex;
      gap: 6px;
      margin-left: auto;
      flex-shrink: 0;
    }}
    .playlist-skip-btn {{
      width: 28px;
      height: 24px;
      border: 1px solid #82604e;
      border-radius: 6px;
      background: transparent;
      color: var(--topInk);
      cursor: pointer;
      font-size: 10px;
      line-height: 1;
      padding: 0;
    }}
    .playlist-skip-btn:hover {{ background: var(--topHover); }}
    .playlist-seek-row {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 10px;
    }}
    .playlist-seek {{ flex: 1; height: 4px; accent-color: #c26935; cursor: pointer; }}
    .seek-label {{ font-size: 11px; color: #c8a87e; min-width: 28px; text-align: center; }}
    .playlist-song-list {{ max-height: 220px; overflow-y: auto; margin-bottom: 8px; }}
    .playlist-song-item {{
      display: flex;
      align-items: baseline;
      gap: 6px;
      padding: 6px 8px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      color: var(--topInk);
      border: 1px solid transparent;
      background: none;
      width: 100%;
      text-align: left;
    }}
    .playlist-song-item:hover {{ background: rgba(255, 255, 255, 0.08); }}
    .playlist-song-item.active {{
      background: rgba(194, 105, 53, 0.25);
      border-color: #c26935;
      font-weight: 700;
    }}
    .playlist-song-num {{ color: #9a7a5a; min-width: 18px; font-size: 11px; flex-shrink: 0; }}
    .playlist-song-title {{ flex: 1; }}
    .playlist-song-culture {{ font-size: 11px; color: #9a7a5a; flex-shrink: 0; }}
    .playlist-yt-link {{
      display: block;
      font-size: 12px;
      color: #f8c67e;
      text-align: center;
      margin-top: 6px;
      text-decoration: none;
    }}
    .playlist-yt-link:hover {{ text-decoration: underline; }}
    #ytMiniPlayer {{
      position: fixed;
      bottom: 16px;
      right: 16px;
      width: 240px;
      height: 135px;
      z-index: 200;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45);
      display: none;
      background: #000;
    }}
    #ytMiniPlayer.visible {{ display: block; }}
    #ytMiniPlayer #ytPlayerHost {{ width: 100%; height: 100%; }}
    #ytMiniClose {{
      position: absolute;
      top: 4px;
      right: 4px;
      width: 24px;
      height: 24px;
      border: none;
      border-radius: 50%;
      background: rgba(0, 0, 0, 0.65);
      color: #fff;
      font-size: 12px;
      cursor: pointer;
      z-index: 201;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    #ytMiniClose:hover {{ background: rgba(170, 50, 15, 0.9); }}
    /* --- Glossary --- */
    .gloss-term {{
      border-bottom: 1px dotted #8f3f22;
      color: inherit;
      cursor: pointer;
      white-space: nowrap;
    }}
    .gloss-term:hover, .gloss-term:focus {{
      background: #faebd6;
      border-radius: 3px;
      outline: none;
    }}
    #glossDialog {{
      position: fixed;
      inset: 0;
      z-index: 500;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(30, 15, 5, 0.5);
      padding: 16px;
    }}
    #glossDialog[hidden] {{ display: none; }}
    #glossDialogInner {{
      background: #fff9ef;
      border: 1px solid #c8a07a;
      border-radius: 14px;
      padding: 22px 24px;
      max-width: 480px;
      width: 100%;
      position: relative;
      box-shadow: 0 12px 32px rgba(0,0,0,0.25);
    }}
    #glossDialogTerm {{
      margin: 0 0 10px 0;
      font-size: 20px;
      color: #2d180f;
    }}
    #glossDialogDef {{
      margin: 0 0 14px 0;
      line-height: 1.6;
      color: #3a2217;
    }}
    #glossDialogClose {{
      position: absolute;
      top: 10px;
      right: 12px;
      background: transparent;
      border: none;
      font-size: 18px;
      color: #6b4c37;
      cursor: pointer;
      line-height: 1;
      padding: 4px 6px;
      border-radius: 6px;
    }}
    #glossDialogClose:hover {{ background: #f0dfc5; }}
    #glossHoverCard {{
      position: fixed;
      z-index: 490;
      max-width: 360px;
      width: min(360px, calc(100vw - 20px));
      background: #fff9ef;
      border: 1px solid #c8a07a;
      border-radius: 10px;
      padding: 12px 14px;
      box-shadow: 0 10px 26px rgba(0,0,0,0.22);
      pointer-events: none;
    }}
    #glossHoverCard[hidden] {{ display: none; }}
    #glossHoverTerm {{
      margin: 0 0 4px 0;
      font-size: 16px;
      color: #2d180f;
    }}
    #glossHoverDef {{
      margin: 0;
      line-height: 1.5;
      color: #3a2217;
      font-size: 14px;
    }}
    .gloss-letter-nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 14px;
      padding: 10px 14px;
    }}
    .gloss-letter-link {{
      min-width: 28px;
      text-align: center;
      padding: 4px 8px;
      background: #f0e3cc;
      border: 1px solid #d4bf9f;
      border-radius: 6px;
      text-decoration: none;
      font-weight: 700;
      font-size: 14px;
      color: #5a2815;
    }}
    .gloss-letter-link:hover {{ background: #e0cba8; }}
    .gloss-body {{ columns: 2; column-gap: 28px; }}
    .gloss-section {{ break-inside: avoid; margin-bottom: 18px; }}
    .gloss-section h2 {{ font-size: 22px; margin: 0 0 8px 0; color: #2d180f; scroll-margin-top: 84px; }}
    .gloss-dl {{ margin: 0; }}
    .gloss-dl dt {{ font-weight: 700; margin-top: 8px; color: #3a2217; }}
    .gloss-dl dd {{ margin: 2px 0 6px 0; color: #685648; font-size: 14px; line-height: 1.5; }}
    @media (max-width: 700px) {{ .gloss-body {{ columns: 1; }} }}
  </style>
</head>
<body>
  <header class=\"topbar\">
    <div class=\"topbar-inner\">
      <h1 class=\"brand\">Whisky Study Guide</h1>
      <button id=\"menuToggle\" class=\"menu-toggle\" aria-expanded=\"false\" aria-controls=\"topLinks\">Menu</button>
      <nav id=\"topLinks\" class=\"top-links\">{nav}</nav>
    </div>
  </header>
  <div id=\"ytMiniPlayer\"><div id=\"ytPlayerHost\"></div><button id=\"ytMiniClose\" type=\"button\" aria-label=\"Close mini player\">&#10005;</button></div>
  <div id=\"glossDialog\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"glossDialogTerm\" hidden>
    <div id=\"glossDialogInner\">
      <button id=\"glossDialogClose\" type=\"button\" aria-label=\"Close definition\">&#10005;</button>
      <h3 id=\"glossDialogTerm\"></h3>
      <p id=\"glossDialogDef\"></p>
    </div>
  </div>
  <div id=\"glossHoverCard\" aria-hidden=\"true\" hidden>
    <h4 id=\"glossHoverTerm\"></h4>
    <p id=\"glossHoverDef\"></p>
  </div>
  <script>
    const _WHISKY_BASE = {base_path_js};
    function whiskyPath(path) {{
      const raw = String(path || '/');
      const normalized = raw === '/' ? '/' : raw.replace(/^\\/+/, '/');
      return _WHISKY_BASE ? _WHISKY_BASE + normalized : normalized;
    }}
    window._WHISKY_BASE = _WHISKY_BASE;
    window.whiskyPath = whiskyPath;
  </script>
  <div class=\"wrap\">{body}</div>
  {footer}
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
        navigator.serviceWorker.register(whiskyPath('/sw.js')).catch(() => {{
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
        const finalSrc = cleaned.startsWith('/') ? whiskyPath(cleaned) : cleaned;
        return '<img src="' + finalSrc + '" alt="' + escapeHtml(alt) + '" loading="lazy" />';
      }});
        out = out.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, (_m, label, href) => {{
          const isExternal = href.startsWith('http://') || href.startsWith('https://');
          const attrs = isExternal ? ' target="_blank" rel="noreferrer"' : '';
          const finalHref = !isExternal && href.startsWith('/') ? whiskyPath(href) : href;
          return '<a href="' + finalHref + '"' + attrs + '>' + label + '</a>';
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

    function scrollToCurrentHash(smooth) {{
      if (!window.location.hash || window.location.hash.length < 2) {{
        return false;
      }}
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (!id) {{
        return false;
      }}
      const target = document.getElementById(id);
      if (!target) {{
        return false;
      }}
      target.scrollIntoView({{ behavior: smooth ? 'smooth' : 'auto', block: 'start' }});
      return true;
    }}

    function stabilizeHashScroll() {{
      if (!window.location.hash) {{
        return;
      }}
      const didScroll = scrollToCurrentHash(false);
      if (!didScroll) {{
        return;
      }}
      requestAnimationFrame(() => requestAnimationFrame(() => scrollToCurrentHash(false)));
      window.setTimeout(() => scrollToCurrentHash(false), 220);
      window.setTimeout(() => scrollToCurrentHash(false), 700);
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
        const response = await fetch(whiskyPath('/quizzes/data'));
        if (!response.ok) {{
          throw new Error('Quiz data unavailable');
        }}
        const payload = await response.json();
        const allQuizzes = payload.quizzes || [];
        const phaseQuizzes = allQuizzes.filter((quiz) => quiz.pagePath === pagePath);
        const progress = loadQuizProgress();
        const quizNavBtn = document.getElementById('quizNavBtn');
        if (quizNavBtn) {{
          if (phaseQuizzes.length) {{
            quizNavBtn.setAttribute('href', '#quiz-' + phaseQuizzes[0].id);
          }} else {{
            quizNavBtn.setAttribute('href', '#phaseQuizPanel');
          }}
        }}

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

          if (!img.complete) {{
            img.addEventListener('load', () => {{
              scrollToCurrentHash(false);
            }}, {{ once: true }});
          }}
        }});

        buildTopicIndex(contentEl, indexEl);
        await renderPhaseQuizPanel(pagePath);
        stabilizeHashScroll();
        applyGlossaryTerms();
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

    // =====================================================
    // Whisky Playlist Player
    // =====================================================
    const whiskyPlaylist = [
      {{ title: "The Barnyards of Delgaty", artist: "Noel McLoughlin", culture: "Scottish Bothy Ballad", videoId: "Ox9_NkwIt6A" }},
      {{ title: "Auld Lang Syne", artist: "Eddi Reader", culture: "Scottish Burns", videoId: "pTSWtHf_ZMY" }},
      {{ title: "Willie Brew'd A Peck O' Maut", artist: "Tony Cuffe & Rod Paterson", culture: "Scottish Burns", videoId: "TkQe__QWWxI" }},
      {{ title: "Whiskey in the Jar", artist: "The Dubliners", culture: "Irish Folk", videoId: "Hwb8C2TijYE" }},
      {{ title: "Whiskey in the Jar", artist: "Thin Lizzy", culture: "Irish Rock", videoId: "6WDSY8Kaf6o" }},
      {{ title: "Whiskey in the Jar", artist: "Metallica", culture: "Metal", videoId: "wsrvmNtWU4E" }},
      {{ title: "Whiskey You're the Devil", artist: "The Irish Rovers", culture: "Irish-Canadian", videoId: "V-rilQwuD2Q" }},
      {{ title: "Streams of Whiskey", artist: "The Pogues", culture: "Irish Punk", videoId: "mPpGp_J3z2A" }},
      {{ title: "Scotch and Soda", artist: "The Kingston Trio", culture: "American Folk", videoId: "TqGGAJ2D_bY" }},
      {{ title: "Rye Whiskey", artist: "Punch Brothers", culture: "American Appalachian (Bluegrass)", videoId: "braQeLkJUvE" }},
      {{ title: "Moonshine Whiskey", artist: "Van Morrison", culture: "Blues Rock", videoId: "MNcohKa_p68" }},
      {{ title: "Moonshiner", artist: "Bob Dylan", culture: "American Appalachian Folk", videoId: "pxr22ih0r9A" }},
      {{ title: "Copper Kettle", artist: "Joan Baez", culture: "American Appalachian", videoId: "glMQXjy46J8" }},
      {{ title: "One Bourbon, One Scotch, One Beer", artist: "George Thorogood & The Destroyers", culture: "Blues Rock", videoId: "IyLnRB04QF8" }},
      {{ title: "One Bourbon, One Scotch, One Beer", artist: "John Lee Hooker", culture: "Blues", videoId: "z4A6o-yf-ao" }},
      {{ title: "One Scotch, One Bourbon, One Beer", artist: "Amos Milburn", culture: "R&B", videoId: "RZrP18m0lFo" }},
      {{ title: "Whiskey Drinkin' Woman", artist: "Nazareth", culture: "Hard Rock", videoId: "fNazfh-LXnU" }},
      {{ title: "Whiskey Rock-A-Roller", artist: "Lynyrd Skynyrd", culture: "Southern Rock", videoId: "s_MHBXu8roY" }},
      {{ title: "Whiskey Train", artist: "Procol Harum", culture: "Classic Rock", videoId: "NZoN0-OyqQQ" }},
      {{ title: "Whiskey River", artist: "Willie Nelson", culture: "American Country", videoId: "RSTDgc7dbyc" }},
      {{ title: "Tennessee Whiskey", artist: "Chris Stapleton", culture: "American Country", videoId: "4zAThXFOy2c" }},
      {{ title: "Whiskey Lullaby", artist: "Brad Paisley ft. Alison Krauss", culture: "American Country", videoId: "IZbN_nmxAGk" }},
      {{ title: "Whiskey Glasses", artist: "Morgan Wallen", culture: "Modern Country", videoId: "FjBp30kjzTc" }},
      {{ title: "Whiskey Under the Bridge", artist: "Brooks & Dunn", culture: "Country", videoId: "_Dlbur7Gzvw" }},
      {{ title: "Alabama Song (Whisky Bar)", artist: "The Doors", culture: "Psychedelic Rock", videoId: "nbtEkZIvMAg" }},
    ];

    let currentSongIndex = 0;
    let ytPlayer = null;
    let ytReady = false;
    let ytLoading = false;
    let pendingAutoplay = false;
    let resumeAfterReady = false;
    let restoreTimeAfterReady = 0;
    let playbackActive = false;
    let seekTimer = null;

    const playlistControl = document.getElementById('playlistControl');
    const playlistPlayToggle = document.getElementById('playlistPlayToggle');
    const playlistDropdownToggle = document.getElementById('playlistDropdownToggle');
    const playlistDropdown = document.getElementById('playlistDropdown');
    const playlistNowPlaying = document.getElementById('playlistNowPlaying');
    const playlistPrevBtn = document.getElementById('playlistPrevBtn');
    const playlistNextBtn = document.getElementById('playlistNextBtn');
    const playlistSeek = document.getElementById('playlistSeek');
    const seekCurrentTime = document.getElementById('seekCurrentTime');
    const seekDuration = document.getElementById('seekDuration');
    const playlistSongList = document.getElementById('playlistSongList');

    // --- State persistence ---
    const WHISKY_STORAGE_KEY = 'whiskyPlaylistStateV1';
    function savePlaylistState(state) {{
      try {{ localStorage.setItem(WHISKY_STORAGE_KEY, JSON.stringify(state)); }} catch (_) {{}}
    }}
    function loadPlaylistState() {{
      try {{ return JSON.parse(localStorage.getItem(WHISKY_STORAGE_KEY) || 'null'); }} catch (_) {{ return null; }}
    }}

    // --- Restore from stored state ---
    const storedPlaylistState = loadPlaylistState();
    if (storedPlaylistState) {{
      currentSongIndex = Math.min(Math.max(0, storedPlaylistState.songIndex || 0), whiskyPlaylist.length - 1);
      restoreTimeAfterReady = storedPlaylistState.currentTime || 0;
      if (storedPlaylistState.shouldPlay) {{
        pendingAutoplay = true;
        resumeAfterReady = true;
      }}
    }}

    // --- UI helpers ---
    function formatTime(seconds) {{
      const s = Math.floor(seconds || 0);
      return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    }}

    function updateNowPlayingLabel() {{
      if (!whiskyPlaylist.length) {{
        if (playlistNowPlaying) playlistNowPlaying.textContent = 'Whisky Playlist (0/0)';
        return;
      }}
      const song = whiskyPlaylist[currentSongIndex];
      if (playlistNowPlaying) {{
        playlistNowPlaying.textContent = playbackActive
          ? song.artist + ' \u2013 ' + song.title
          : 'Whisky Playlist (' + (currentSongIndex + 1) + '/' + whiskyPlaylist.length + ')';
      }}
    }}

    function updateSongButtons() {{
      document.querySelectorAll('.playlist-song-item').forEach((btn, i) => {{
        btn.classList.toggle('active', i === currentSongIndex);
      }});
    }}

    function setPlayButtonLabel(isPlaying) {{
      if (!playlistPlayToggle) return;
      playbackActive = isPlaying;
      playlistPlayToggle.dataset.state = isPlaying ? 'playing' : 'paused';
      playlistPlayToggle.title = isPlaying ? 'Pause whisky playlist' : 'Play whisky playlist';
      playlistPlayToggle.setAttribute('aria-label', isPlaying ? 'Pause whisky playlist' : 'Play whisky playlist');
      playlistPlayToggle.innerHTML = isPlaying
        ? '<span class="playlist-main-icon" aria-hidden="true">&#9646;&#9646;</span>'
        : '<span class="playlist-main-icon" aria-hidden="true">&#9654;</span>';
      const miniPlayer = document.getElementById('ytMiniPlayer');
      if (miniPlayer) miniPlayer.classList.toggle('visible', isPlaying);
    }}

    function playCurrentSong(autoplay = true) {{
      if (!whiskyPlaylist.length) {{
        setPlayButtonLabel(false);
        updateNowPlayingLabel();
        return;
      }}
      restoreTimeAfterReady = 0;
      updateNowPlayingLabel();
      updateSongButtons();

      if (ytReady && ytPlayer) {{
        if (autoplay) {{
          setPlayButtonLabel(true);
          ytPlayer.loadVideoById(whiskyPlaylist[currentSongIndex].videoId);
        }} else {{
          setPlayButtonLabel(false);
          ytPlayer.cueVideoById({{ videoId: whiskyPlaylist[currentSongIndex].videoId, startSeconds: 0 }});
        }}
      }} else {{
        pendingAutoplay = autoplay;
        resumeAfterReady = autoplay;
        setPlayButtonLabel(autoplay);
      }}
    }}

    function stepSong(direction) {{
      const total = whiskyPlaylist.length;
      if (!total) return;
      currentSongIndex = (currentSongIndex + direction + total) % total;
      playCurrentSong(true);
      savePlaylistState({{ songIndex: currentSongIndex, currentTime: 0, shouldPlay: true }});
    }}

    function renderPlaylistSongs() {{
      if (!playlistSongList) return;
      playlistSongList.innerHTML = '';
      if (!whiskyPlaylist.length) {{
        const emptyEl = document.createElement('div');
        emptyEl.className = 'muted';
        emptyEl.textContent = 'No playable songs available right now.';
        playlistSongList.appendChild(emptyEl);
        return;
      }}
      whiskyPlaylist.forEach((song, i) => {{
        const btn = document.createElement('button');
        btn.className = 'playlist-song-item' + (i === currentSongIndex ? ' active' : '');
        btn.type = 'button';
        btn.dataset.index = String(i);
        btn.innerHTML =
          '<span class="playlist-song-num">' + (i + 1) + '</span>' +
          '<span class="playlist-song-title">' + escapeHtml(song.title) +
          ' <span style="font-weight:400;color:#c8a87e">' + escapeHtml(song.artist) + '</span></span>' +
          '<span class="playlist-song-culture">' + escapeHtml(song.culture) + '</span>';
        btn.addEventListener('click', () => {{
          currentSongIndex = i;
          playCurrentSong(true);
        }});
        playlistSongList.appendChild(btn);
      }});
    }}

    // --- Seek handling ---
    function startSeekPoller() {{
      if (seekTimer) return;
      seekTimer = setInterval(() => {{
        if (!ytReady || !ytPlayer) return;
        const state = ytPlayer.getPlayerState();
        if (state !== YT.PlayerState.PLAYING && state !== YT.PlayerState.PAUSED) return;
        const cur = ytPlayer.getCurrentTime();
        const dur = ytPlayer.getDuration();
        if (dur > 0) {{
          if (playlistSeek) {{ playlistSeek.max = String(Math.floor(dur)); playlistSeek.value = String(Math.floor(cur)); }}
          if (seekCurrentTime) seekCurrentTime.textContent = formatTime(cur);
          if (seekDuration) seekDuration.textContent = formatTime(dur);
        }}
      }}, 1000);
    }}

    if (playlistSeek) {{
      playlistSeek.addEventListener('input', () => {{
        if (ytReady && ytPlayer) ytPlayer.seekTo(Number(playlistSeek.value), true);
      }});
    }}

    // --- YouTube IFrame API ---
    function ensureYouTubePlayer() {{
      if (ytReady || ytLoading) return;
      ytLoading = true;
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      document.head.appendChild(tag);
    }}

    window.onYouTubeIframeAPIReady = () => {{
      ytPlayer = new YT.Player('ytPlayerHost', {{
        width: '240',
        height: '135',
        videoId: whiskyPlaylist[currentSongIndex].videoId,
        playerVars: {{ playsinline: 1, rel: 0, modestbranding: 1, origin: window.location.origin }},
        events: {{
          onReady: () => {{
            ytReady = true;
            ytLoading = false;
            ytPlayer.cueVideoById({{ videoId: whiskyPlaylist[currentSongIndex].videoId, startSeconds: restoreTimeAfterReady }});
            if (pendingAutoplay || resumeAfterReady) {{
              pendingAutoplay = false;
              resumeAfterReady = false;
              ytPlayer.playVideo();
            }}
            updateNowPlayingLabel();
          }},
          onStateChange: (event) => {{
            if (event.data === YT.PlayerState.PLAYING) {{
              setPlayButtonLabel(true);
              updateNowPlayingLabel();
              startSeekPoller();
              savePlaylistState({{ songIndex: currentSongIndex, currentTime: ytPlayer.getCurrentTime(), shouldPlay: true }});
            }}
            if (event.data === YT.PlayerState.PAUSED) {{
              setPlayButtonLabel(false);
              updateNowPlayingLabel();
              savePlaylistState({{ songIndex: currentSongIndex, currentTime: ytPlayer.getCurrentTime(), shouldPlay: false }});
            }}
            if (event.data === YT.PlayerState.ENDED) {{
              // Wrap to the beginning when the current song is the last track.
              stepSong(1);
            }}
          }},
          onError: (event) => {{
            if ([2, 5, 100, 101, 150].includes(event.data)) {{
              stepSong(1);
            }}
          }},
        }},
      }});
    }};

    // --- Play/Pause toggle ---
    function togglePlaylistPlayback() {{
      if (!whiskyPlaylist.length) return;
      if (!ytReady || !ytPlayer) {{
        pendingAutoplay = true;
        resumeAfterReady = true;
        return;
      }}
      const state = ytPlayer.getPlayerState();
      if (state === YT.PlayerState.PLAYING) {{
        ytPlayer.pauseVideo();
      }} else if (state === YT.PlayerState.PAUSED) {{
        ytPlayer.playVideo();
      }} else {{
        ytPlayer.loadVideoById({{ videoId: whiskyPlaylist[currentSongIndex].videoId, startSeconds: restoreTimeAfterReady }});
      }}
    }}

    if (playlistPlayToggle) {{
      playlistPlayToggle.addEventListener('click', togglePlaylistPlayback);
    }}

    if (playlistPrevBtn) {{
      playlistPrevBtn.addEventListener('click', () => stepSong(-1));
    }}

    if (playlistNextBtn) {{
      playlistNextBtn.addEventListener('click', () => stepSong(1));
    }}

    // --- Dropdown toggle ---
    if (playlistDropdownToggle && playlistDropdown) {{
      playlistDropdownToggle.addEventListener('click', (e) => {{
        e.stopPropagation();
        const isHidden = playlistDropdown.hasAttribute('hidden');
        if (isHidden) {{
          playlistDropdown.removeAttribute('hidden');
          playlistDropdownToggle.setAttribute('aria-expanded', 'true');
        }} else {{
          playlistDropdown.setAttribute('hidden', '');
          playlistDropdownToggle.setAttribute('aria-expanded', 'false');
        }}
      }});
    }}

    document.addEventListener('click', (e) => {{
      if (playlistControl && !playlistControl.contains(e.target)) {{
        if (playlistDropdown) playlistDropdown.setAttribute('hidden', '');
        if (playlistDropdownToggle) playlistDropdownToggle.setAttribute('aria-expanded', 'false');
      }}
    }});

    // --- Mini-player close ---
    const ytMiniCloseBtn = document.getElementById('ytMiniClose');
    if (ytMiniCloseBtn) {{
      ytMiniCloseBtn.addEventListener('click', () => {{
        if (ytReady && ytPlayer) ytPlayer.pauseVideo();
        setPlayButtonLabel(false);
        savePlaylistState({{
          songIndex: currentSongIndex,
          currentTime: ytReady && ytPlayer ? ytPlayer.getCurrentTime() : restoreTimeAfterReady,
          shouldPlay: false,
        }});
        updateNowPlayingLabel();
      }});
    }}

    // --- Save state on page leave ---
    window.addEventListener('pagehide', () => {{
      savePlaylistState({{
        songIndex: currentSongIndex,
        currentTime: ytReady && ytPlayer ? ytPlayer.getCurrentTime() : restoreTimeAfterReady,
        shouldPlay: playbackActive,
      }});
    }});

    function initializeDynamicPageContent() {{
      renderMarkdownPage();
      renderCoursePage();
      applyGlossaryTerms();
    }}

    // =====================================================
    // Glossary term annotation and dialog
    // =====================================================
    let _glossaryData = null;

    async function fetchGlossaryData() {{
      if (_glossaryData) return _glossaryData;
      try {{
        const resp = await fetch(whiskyPath('/glossary/data'));
        if (resp.ok) {{
          _glossaryData = await resp.json();
        }}
      }} catch (_) {{}}
      return _glossaryData;
    }}

    function annotateGlossaryTerms(containerEl, glossary) {{
      if (!glossary || !containerEl) return;
      const terms = Object.keys(glossary).sort((a, b) => b.length - a.length);
      if (!terms.length) return;

      // Skip containers that are glossary pages themselves
      if (containerEl.classList.contains('gloss-body')) return;

      const escapedTerms = terms.map(t =>
        t.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&')
      );
      const regex = new RegExp('(?<![\\\\w-])(' + escapedTerms.join('|') + ')(?![\\\\w-])', 'gi');

      const walker = document.createTreeWalker(
        containerEl,
        NodeFilter.SHOW_TEXT,
        {{
          acceptNode(node) {{
            const parent = node.parentElement;
            if (!parent) return NodeFilter.FILTER_REJECT;
            const tag = parent.tagName.toLowerCase();
            if (['h1','h2','h3','h4','h5','h6','a','code','pre','script','style'].includes(tag)) {{
              return NodeFilter.FILTER_REJECT;
            }}
            if (parent.closest('.gloss-term, .gloss-dl, [data-no-gloss]')) {{
              return NodeFilter.FILTER_REJECT;
            }}
            return NodeFilter.FILTER_ACCEPT;
          }}
        }}
      );

      const textNodes = [];
      let n;
      while ((n = walker.nextNode())) textNodes.push(n);

      // Track which terms have been annotated to avoid duplicate spans in same container
      const annotated = new Set();

      for (const textNode of textNodes) {{
        const text = textNode.nodeValue || '';
        if (!regex.test(text)) {{ regex.lastIndex = 0; continue; }}
        regex.lastIndex = 0;

        const frag = document.createDocumentFragment();
        let lastIndex = 0;
        let m;
        while ((m = regex.exec(text)) !== null) {{
          const matchedText = m[1];
          const canonicalTerm = terms.find(t => t.toLowerCase() === matchedText.toLowerCase()) || matchedText;
          // Only annotate first occurrence of each term per container
          if (annotated.has(canonicalTerm.toLowerCase())) continue;
          annotated.add(canonicalTerm.toLowerCase());

          if (m.index > lastIndex) {{
            frag.appendChild(document.createTextNode(text.slice(lastIndex, m.index)));
          }}
          const span = document.createElement('span');
          span.className = 'gloss-term';
          span.setAttribute('data-gloss-term', canonicalTerm);
          span.setAttribute('tabindex', '0');
          span.setAttribute('role', 'button');
          span.setAttribute('aria-label', 'Definition of ' + canonicalTerm);
          span.textContent = matchedText;
          frag.appendChild(span);
          lastIndex = m.index + m[0].length;
        }}
        if (lastIndex < text.length) {{
          frag.appendChild(document.createTextNode(text.slice(lastIndex)));
        }}
        if (lastIndex > 0 && textNode.parentNode) {{
          textNode.parentNode.replaceChild(frag, textNode);
        }}
        regex.lastIndex = 0;
      }}
    }}

    async function applyGlossaryTerms() {{
      const glossary = await fetchGlossaryData();
      if (!glossary) return;
      const panels = document.querySelectorAll('.markdown-panel, .course-phase-content');
      panels.forEach(panel => annotateGlossaryTerms(panel, glossary));
    }}

    // Glossary dialog
    (function () {{
      const dialog = document.getElementById('glossDialog');
      const termEl = document.getElementById('glossDialogTerm');
      const defEl = document.getElementById('glossDialogDef');
      const closeBtn = document.getElementById('glossDialogClose');
      const hoverCard = document.getElementById('glossHoverCard');
      const hoverTermEl = document.getElementById('glossHoverTerm');
      const hoverDefEl = document.getElementById('glossHoverDef');
      if (!dialog || !termEl || !defEl || !hoverCard || !hoverTermEl || !hoverDefEl) return;
      const isDesktopHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
      let closeTimer = null;
      let hoverOpenTimer = null;
      let hoverCloseTimer = null;
      let hoverAnchor = null;

      function openGlossDialog(term, definition, options) {{
        const opts = options || {{}};
        closeHoverCard();
        termEl.textContent = term;
        defEl.textContent = definition;
        dialog.removeAttribute('hidden');
        if (opts.focusClose && closeBtn) {{
          closeBtn.focus();
        }}
      }}

      function closeGlossDialog() {{
        if (closeTimer) {{
          window.clearTimeout(closeTimer);
          closeTimer = null;
        }}
        dialog.setAttribute('hidden', '');
      }}

      function scheduleCloseGlossDialog(delayMs) {{
        if (closeTimer) {{
          window.clearTimeout(closeTimer);
        }}
        closeTimer = window.setTimeout(closeGlossDialog, delayMs);
      }}

      function cancelCloseGlossDialog() {{
        if (closeTimer) {{
          window.clearTimeout(closeTimer);
          closeTimer = null;
        }}
      }}

      function positionHoverCard(anchorEl) {{
        const rect = anchorEl.getBoundingClientRect();
        const margin = 10;
        const cardRect = hoverCard.getBoundingClientRect();
        const viewportW = window.innerWidth;
        const viewportH = window.innerHeight;
        let left = rect.left;
        let top = rect.bottom + 8;

        if (left + cardRect.width + margin > viewportW) {{
          left = viewportW - cardRect.width - margin;
        }}
        if (left < margin) {{
          left = margin;
        }}
        if (top + cardRect.height + margin > viewportH) {{
          top = rect.top - cardRect.height - 8;
        }}
        if (top < margin) {{
          top = margin;
        }}

        hoverCard.style.left = left + 'px';
        hoverCard.style.top = top + 'px';
      }}

      function openHoverCard(termName, anchorEl) {{
        hoverAnchor = anchorEl;
        fetchGlossaryData().then(function (glossary) {{
          if (!glossary || hoverAnchor !== anchorEl) return;
          const definition = glossary[termName];
          if (!definition) return;
          hoverTermEl.textContent = termName;
          hoverDefEl.textContent = definition;
          hoverCard.removeAttribute('hidden');
          positionHoverCard(anchorEl);
        }});
      }}

      function closeHoverCard() {{
        hoverAnchor = null;
        hoverCard.setAttribute('hidden', '');
      }}

      function scheduleHoverOpen(termName, anchorEl, delayMs) {{
        if (hoverOpenTimer) {{
          window.clearTimeout(hoverOpenTimer);
        }}
        hoverOpenTimer = window.setTimeout(function () {{
          hoverOpenTimer = null;
          openHoverCard(termName, anchorEl);
        }}, delayMs);
      }}

      function scheduleHoverClose(delayMs) {{
        if (hoverCloseTimer) {{
          window.clearTimeout(hoverCloseTimer);
        }}
        hoverCloseTimer = window.setTimeout(function () {{
          hoverCloseTimer = null;
          closeHoverCard();
        }}, delayMs);
      }}

      function cancelHoverTimers() {{
        if (hoverOpenTimer) {{
          window.clearTimeout(hoverOpenTimer);
          hoverOpenTimer = null;
        }}
        if (hoverCloseTimer) {{
          window.clearTimeout(hoverCloseTimer);
          hoverCloseTimer = null;
        }}
      }}

      function closestGlossTerm(node) {{
        return node && node.closest ? node.closest('.gloss-term') : null;
      }}

      function onViewportChange() {{
        if (hoverAnchor && !hoverCard.hasAttribute('hidden')) {{
          positionHoverCard(hoverAnchor);
          return;
        }}
        closeHoverCard();
      }}

      window.addEventListener('resize', onViewportChange);
      window.addEventListener('scroll', onViewportChange, true);

      closeBtn && closeBtn.addEventListener('click', closeGlossDialog);
      dialog.addEventListener('click', function (e) {{
        if (e.target === dialog) closeGlossDialog();
      }});
      document.addEventListener('keydown', function (e) {{
        if (e.key === 'Escape') {{
          if (!dialog.hasAttribute('hidden')) closeGlossDialog();
          closeHoverCard();
        }}
      }});

      document.addEventListener('click', function (e) {{
        const target = closestGlossTerm(e.target);
        if (!target) return;
        cancelHoverTimers();
        closeHoverCard();
        const termName = target.getAttribute('data-gloss-term');
        if (!termName) return;
        fetchGlossaryData().then(function (glossary) {{
          if (!glossary) return;
          const definition = glossary[termName];
          if (definition) openGlossDialog(termName, definition, {{ focusClose: true, triggerMode: 'click' }});
        }});
      }});

      if (isDesktopHover) {{
        document.addEventListener('mouseover', function (e) {{
          const target = closestGlossTerm(e.target);
          if (!target) return;
          const termName = target.getAttribute('data-gloss-term');
          if (!termName) return;
          cancelHoverTimers();
          if (hoverAnchor === target && !hoverCard.hasAttribute('hidden')) {{
            return;
          }}
          scheduleHoverOpen(termName, target, 90);
        }});

        document.addEventListener('mouseout', function (e) {{
          const target = closestGlossTerm(e.target);
          if (!target) return;
          const relatedTerm = closestGlossTerm(e.relatedTarget);
          if (relatedTerm === target) {{
            return;
          }}
          cancelHoverTimers();
          scheduleHoverClose(70);
        }});
      }}

      document.addEventListener('focusin', function (e) {{
        const target = closestGlossTerm(e.target);
        if (!target) return;
        cancelHoverTimers();
        closeHoverCard();
        const termName = target.getAttribute('data-gloss-term');
        if (!termName) return;
        fetchGlossaryData().then(function (glossary) {{
          if (!glossary) return;
          const definition = glossary[termName];
          if (definition) openGlossDialog(termName, definition, {{ focusClose: false, triggerMode: 'focus' }});
        }});
      }});

      document.addEventListener('focusout', function (e) {{
        const target = closestGlossTerm(e.target);
        if (!target) return;
        scheduleCloseGlossDialog(0);
      }});

      document.addEventListener('keydown', function (e) {{
        if ((e.key === 'Enter' || e.key === ' ') && document.activeElement && document.activeElement.classList.contains('gloss-term')) {{
          e.preventDefault();
          document.activeElement.click();
        }}
      }});
    }})();


    window.addEventListener('hashchange', function () {{
      scrollToCurrentHash(true);
    }});

    function normalizeNavPath(href) {{
      const parsed = new URL(href, window.location.origin);
      if (parsed.pathname.length > 1 && parsed.pathname.endsWith('/')) {{
        return parsed.pathname.slice(0, -1);
      }}
      return parsed.pathname || '/';
    }}

    function updateActiveNav(pathname) {{
      document.querySelectorAll('#topLinks a').forEach((link) => {{
        const href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('http')) {{
          return;
        }}
        const normalizedHref = normalizeNavPath(href);
        const isLessonsTrigger = normalizedHref === '/whisky-lessons';
        const isLessonsPage = pathname === '/whisky-lessons' || pathname === '/the-whisky-course' || pathname.startsWith('/phase-');
        const isActive = isLessonsTrigger ? isLessonsPage : normalizedHref === pathname;
        link.classList.toggle('active', isActive);
      }});
    }}

    function rerunWrapScripts(container) {{
      const scripts = Array.from(container.querySelectorAll('script'));
      scripts.forEach((script) => {{
        const replacement = document.createElement('script');
        Array.from(script.attributes).forEach((attr) => {{
          replacement.setAttribute(attr.name, attr.value);
        }});
        replacement.textContent = script.textContent;
        script.replaceWith(replacement);
      }});
    }}

    async function navigateWithinApp(href, pushState) {{
      const targetUrl = new URL(href, window.location.origin);
      const response = await fetch(targetUrl.pathname + targetUrl.search, {{ credentials: 'same-origin' }});
      if (!response.ok) {{
        window.location.href = targetUrl.href;
        return;
      }}

      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const nextWrap = doc.querySelector('.wrap');
      const currentWrap = document.querySelector('.wrap');
      if (!nextWrap || !currentWrap) {{
        window.location.href = targetUrl.href;
        return;
      }}

      currentWrap.innerHTML = nextWrap.innerHTML;
      rerunWrapScripts(currentWrap);
      document.title = doc.title;

      if (pushState) {{
        history.pushState({{ href: targetUrl.href }}, '', targetUrl.pathname + targetUrl.search + targetUrl.hash);
      }}

      updateActiveNav(normalizeNavPath(targetUrl.href));
      initializeDynamicPageContent();

      if (targetUrl.hash) {{
        const hashTarget = document.getElementById(targetUrl.hash.slice(1));
        if (hashTarget) {{
          hashTarget.scrollIntoView({{ behavior: 'auto', block: 'start' }});
          return;
        }}
      }}

      window.scrollTo(0, 0);
    }}

    document.addEventListener('click', (event) => {{
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {{
        return;
      }}

      const link = event.target.closest('a[href]');
      if (!link) {{
        return;
      }}

      const href = link.getAttribute('href');
      if (!href || href.startsWith('#') || link.getAttribute('target') === '_blank' || link.hasAttribute('download')) {{
        return;
      }}

      const targetUrl = new URL(href, window.location.href);
      if (targetUrl.origin !== window.location.origin) {{
        return;
      }}

      event.preventDefault();
      navigateWithinApp(targetUrl.href, true).catch(() => {{
        window.location.href = targetUrl.href;
      }});
    }});

    window.addEventListener('popstate', () => {{
      navigateWithinApp(window.location.href, false).catch(() => {{
        window.location.reload();
      }});
    }});

    // --- Player init ---
    renderPlaylistSongs();
    updateNowPlayingLabel();
    ensureYouTubePlayer();

    initializeDynamicPageContent();
  </script>
</body>
</html>
"""

    def render_privacy(self) -> None:
        body = """
        <section class=\"hero\">
          <h1>Privacy</h1>
          <p class=\"muted\"><strong>Note:</strong> all saved quizzes remain on your computer and are stored locally in your browser.</p>
        </section>

        <section class=\"panel markdown-panel\">
          <h2>Privacy Policy</h2>
          <p>We are committed to providing quality services to you and this policy outlines our ongoing obligations to you in respect of how we manage your Personal Information.</p>
          <p>We have adopted the Australian Privacy Principles (APPs) contained in the Privacy Act 1988 (Cth) (the Privacy Act). The APPs govern the way in which we collect, use, disclose, store, secure and dispose of your Personal Information.</p>
          <p>A copy of the Australian Privacy Principles may be obtained from the website of The Office of the Australian Information Commissioner at <a href=\"https://www.oaic.gov.au/\" target=\"_blank\" rel=\"noreferrer\">https://www.oaic.gov.au/</a>.</p>

          <h2>What is Personal Information and why do we collect it?</h2>
          <p>Personal Information is information or an opinion that identifies an individual. Examples of Personal Information we may collect include names, addresses, email addresses, phone and facsimile numbers, and billing information.</p>
          <p>This Personal Information is obtained in many ways including correspondence, by telephone and facsimile, by email, via our website, from media and publications, from other publicly available sources, from cookies and from third parties. We don't guarantee website links or policy of authorised third parties.</p>
          <p>We collect your Personal Information for the primary purpose of providing our services to you, providing information to our clients and marketing. We may also use your Personal Information for secondary purposes closely related to the primary purpose, in circumstances where you would reasonably expect such use or disclosure. You may unsubscribe from our mailing and marketing lists at any time by contacting us in writing.</p>
          <p>When we collect Personal Information we will, where appropriate and where possible, explain to you why we are collecting the information and how we plan to use it.</p>

          <h2>Sensitive Information</h2>
          <p>Sensitive information is defined in the Privacy Act to include information or opinion about such things as an individual's racial or ethnic origin, political opinions, membership of a political association, religious or philosophical beliefs, membership of a trade union or other professional body, criminal record or health information.</p>
          <p>Sensitive information will be used by us only:</p>
          <ul>
            <li>For the primary purpose for which it was obtained.</li>
            <li>For a secondary purpose that is directly related to the primary purpose.</li>
            <li>With your consent, or where required or authorised by law.</li>
          </ul>

          <h2>Third Parties</h2>
          <p>Where reasonable and practicable to do so, we will collect your Personal Information only from you. However, in some circumstances we may be provided with information by third parties. In such a case we will take reasonable steps to ensure that you are made aware of the information provided to us by the third party.</p>

          <h2>Disclosure of Personal Information</h2>
          <p>Your Personal Information may be disclosed in a number of circumstances including the following:</p>
          <ul>
            <li>Third parties where you consent to the use or disclosure.</li>
            <li>Where required or authorised by law.</li>
          </ul>

          <h2>Security of Personal Information</h2>
          <p>Your Personal Information is stored in a manner that reasonably protects it from misuse and loss and from unauthorized access, modification or disclosure.</p>
          <p>When your Personal Information is no longer needed for the purpose for which it was obtained, we will take reasonable steps to destroy or permanently de-identify your Personal Information. However, most of the Personal Information is or will be stored in client files which will be kept by us for a minimum of 7 years.</p>

          <h2>Access to your Personal Information</h2>
          <p>You may access the Personal Information we hold about you and to update and or correct it, subject to certain exceptions. If you wish to access your Personal Information, please contact us in writing.</p>
          <p>We will not charge any fee for your access request, but may charge an administrative fee for providing a copy of your Personal Information.</p>
          <p>In order to protect your Personal Information we may require identification from you before releasing the requested information.</p>

          <h2>Maintaining the Quality of your Personal Information</h2>
          <p>It is important to us that your Personal Information is up to date. We will take reasonable steps to make sure that your Personal Information is accurate, complete and up-to-date. If you find that the information we have is not up to date or is inaccurate, please advise us as soon as practicable so we can update our records and ensure we can continue to provide quality services to you.</p>

          <h2>Policy Updates</h2>
          <p>This Policy may change from time to time and is available on our website.</p>

          <h2>Privacy Policy Complaints and Enquiries</h2>
          <p>If you have any queries or complaints about our Privacy Policy please contact us at:</p>
          <p><a href=\"mailto:syntithenai@gmail.com\">syntithenai@gmail.com</a></p>
        </section>
        """
        self.send_html(self.page_shell("Privacy", body, "/privacy"))

    def render_glossary_data(self) -> None:
        self.send_json(WHISKY_GLOSSARY)

    def render_glossary(self) -> None:
        from collections import defaultdict
        groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for term, definition in sorted(WHISKY_GLOSSARY.items(), key=lambda x: x[0].lower()):
            letter = term[0].upper()
            groups[letter].append((term, definition))

        sections_html = ""
        for letter in sorted(groups.keys()):
            items_html = "".join(
                f"<dt id=\"gloss-{escape(term.lower().replace(' ', '-'))}\"><strong>{escape(term)}</strong></dt>"
                f"<dd>{escape(definition)}</dd>"
                for term, definition in groups[letter]
            )
            sections_html += (
                f"<section class=\"gloss-section\" id=\"gloss-letter-{escape(letter)}\">"
                f"<h2>{escape(letter)}</h2>"
                f"<dl class=\"gloss-dl\">{items_html}</dl>"
                f"</section>"
            )

        letter_nav = " ".join(
            f"<a class=\"gloss-letter-link\" href=\"#gloss-letter-{escape(l)}\">{escape(l)}</a>"
            for l in sorted(groups.keys())
        )

        body = f"""
        <section class=\"hero\">
          <h1>Whisky Glossary</h1>
          <p class=\"muted\">{len(WHISKY_GLOSSARY)} terms covering production, maturation, categories, and tasting vocabulary.</p>
        </section>
        <div class=\"gloss-letter-nav panel\">{letter_nav}</div>
        <div class=\"gloss-body\">
          {sections_html}
        </div>
        """
        self.send_html(self.page_shell("Whisky Glossary", body, "/glossary"))

    def render_home(self) -> None:
        body = f"""
        <section class=\"hero\">
          <h1>Welcome to the World of Whisky</h1>
          <p class=\"muted\">Explore a complete whisky study curriculum across seven phases, from foundations and history through production, regions, culture, operations, and advanced analysis. Use interactive quizzes to test your understanding, browse the distillery database and resources library, and navigate lessons quickly from the course menu.</p>
        </section>

        <section class=\"cards\">
            <a class=\"card-link\" href=\"{self.app_href('/whisky-lessons')}\">
              <h2>Whisky Lessons</h2>
              <p class=\"muted\">Lesson index page linking all phase pages, with direct access from the Whisky Lessons dropdown in navigation.</p>
          </a>
          <a class=\"card-link\" href=\"{self.app_href('/quizzes')}\">
            <h2>Quizzes</h2>
            <p class=\"muted\">Take multiple-choice quizzes from phase documents and track completion in browser storage.</p>
          </a>
          <a class=\"card-link\" href=\"{self.app_href('/resources')}\">
            <h2>Resources</h2>
            <p class=\"muted\">Browse categorized study links and curated references to deepen whisky knowledge beyond the core lessons.</p>
          </a>
          <a class=\"card-link\" href=\"{self.app_href('/glossary')}\">
            <h2>Glossary</h2>
            <p class=\"muted\">Look up key whisky terms, production language, and style vocabulary in one searchable reference page.</p>
          </a>
          <a class=\"card-link\" href=\"{self.app_href('/database')}\">
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
            f"<a class='card-link' href='{escape(self.app_href(page_path))}'>"
                f"<h2>{escape(page['title'])}</h2>"
            f"<p class='muted'>{escape(page.get('description', 'Explore this phase in detail.'))}</p>"
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

    def phase_data_relpath(self, page_path: str) -> str:
        match = re.fullmatch(r"/phase-(\d+)", page_path)
        if match:
            return f"curriculum-phase{match.group(1)}.json"
        return page_path.strip("/").replace("/", "-") + ".json"

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
            page_quizzes = self._parse_quizzes_from_markdown(markdown_path, page_path)
            for quiz in page_quizzes:
                quiz["phaseTitle"] = page["title"]
            collected.extend(page_quizzes)
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

                const cardUrl = quiz.pagePath + '#quiz-' + quiz.id;
                const cardTitle = quiz.phaseTitle || quiz.title;
                summaryHtml.push(
                  '<a class=\\\"quiz-card\\\" href=\\\"' + cardUrl + '\\\">' +
                    '<h3>' + escapeHtml(cardTitle) + '</h3>' +
                    '<p class=\\\"quiz-meta\\\">' + metrics.answered + '/' + metrics.total + ' answered | ' + metrics.correct + ' correct</p>' +
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
              const response = await fetch(whiskyPath('/quizzes/data'));
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
              const nextUrl = query ? whiskyPath('/database') + '?' + query : whiskyPath('/database');
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
                    '<td><a href="' + whiskyPath('/distillery/' + encodeURIComponent(item.id)) + '">' + htmlEscape(item.name) + '</a></td>' +
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
                fetch(whiskyPath('/data-web/distilleries.json')),
                fetch(whiskyPath('/data-web/taxonomy.json')),
                fetch(whiskyPath('/data-web/dataset-manifest.json')).catch(() => null),
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

    @staticmethod
    def _humanize_note_label(label: str) -> str:
        aliases = {
            "pages": "Pages visited",
            "history": "History pages",
            "process": "Process pages",
            "core": "Core range pages",
            "blog": "Technical/blog pages",
            "terms": "Glossary terms covered",
            "new terms": "Potential new glossary terms",
            "new_term": "Potential new glossary terms",
            "new_terms": "Potential new glossary terms",
        }
        normalized = re.sub(r"[_\s]+", " ", label.strip().strip(":=")).lower()
        if not normalized:
            return "Notes"
        if normalized in aliases:
            return aliases[normalized]
        return " ".join(word.capitalize() for word in normalized.split(" "))

    def _parse_research_notes(self, raw_notes: str) -> tuple[list[tuple[str, str]], list[str]]:
        text = raw_notes.strip()
        if not text:
            return [], []

        parsed: list[tuple[str, str]] = []
        leftovers: list[str] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if len(lines) == 1 and ";" in lines[0] and "=" in lines[0]:
            segments = [segment.strip() for segment in lines[0].split(";") if segment.strip()]
            for segment in segments:
                if "=" not in segment:
                    leftovers.append(segment)
                    continue
                label, value = segment.split("=", 1)
                parsed.append((self._humanize_note_label(label), value.strip()))
            return parsed, leftovers

        for line in lines:
            delimiter = ":" if ":" in line else "=" if "=" in line else ""
            if not delimiter:
                leftovers.append(line)
                continue
            label, value = line.split(delimiter, 1)
            parsed.append((self._humanize_note_label(label), value.strip()))

        return parsed, leftovers

    @staticmethod
    def _is_url(text: str) -> bool:
        return text.startswith("http://") or text.startswith("https://")

    @staticmethod
    def _note_link_label(url: str) -> str:
        parsed = urlparse(url)
        host = parsed.netloc.replace("www.", "")
        path = parsed.path.rstrip("/")
        if not path or path == "/":
            return host or url
        last_segment = path.split("/")[-1]
        return f"{host} / {last_segment}" if host else last_segment

    def _render_research_note_value(self, label: str, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return '<span class="muted">None recorded</span>'

        pipe_parts = [part.strip() for part in cleaned.split(" | ") if part.strip()]
        if pipe_parts and len(pipe_parts) > 1 and all(self._is_url(part) for part in pipe_parts):
            items = "".join(
                f'<li><a href="{escape(part)}" target="_blank" rel="noreferrer">{escape(self._note_link_label(part))}</a></li>'
                for part in pipe_parts
            )
            return f'<ul class="note-list">{items}</ul>'

        if label in {"Glossary terms covered", "Potential new glossary terms"}:
            chips = [part.strip() for part in cleaned.split(",") if part.strip()]
            if chips:
                items = "".join(f"<li>{escape(part)}</li>" for part in chips)
                return f'<ul class="note-chip-list">{items}</ul>'

        if label == "Production facts":
            facts = [part.strip() for part in cleaned.split(";") if part.strip()]
            if facts and all(":" in part for part in facts):
                items = []
                for part in facts:
                    fact_label, fact_value = part.split(":", 1)
                    items.append(
                        f'<li><strong>{escape(self._humanize_note_label(fact_label))}:</strong> {escape(fact_value.strip())}</li>'
                    )
                return f'<ul class="note-list">{"".join(items)}</ul>'

        if self._is_url(cleaned):
            return f'<a href="{escape(cleaned)}" target="_blank" rel="noreferrer">{escape(self._note_link_label(cleaned))}</a>'

        return f'<span class="note-raw">{escape(cleaned)}</span>'

    def render_research_record(
        self,
        why_study: str,
        key_focus: str,
        study_status: str,
        operating_status: str,
        website_confidence: str,
        notes: str,
    ) -> str:
        record_rows = [
            ("Why study", why_study.strip()),
            ("Production/style focus", key_focus.strip()),
            ("Study status", study_status.strip()),
            ("Operating status", operating_status.strip()),
            ("Website confidence", website_confidence.strip()),
        ]
        rows_html = "".join(
            f'''<div class="record-row"><p class="record-label">{escape(label)}</p><div class="record-value">{escape(value) if value else '<span class="muted">Not recorded</span>'}</div></div>'''
            for label, value in record_rows
        )

        note_rows, leftovers = self._parse_research_notes(notes)
        notes_html = "".join(
            f'<div class="research-note"><p class="research-note-label">{escape(label)}</p><div class="research-note-value">{self._render_research_note_value(label, value)}</div></div>'
            for label, value in note_rows
        )
        if leftovers:
            extra_lines = "".join(f'<p class="note-raw">{escape(line)}</p>' for line in leftovers)
            notes_html += f'<div class="research-note"><p class="research-note-label">Additional context</p><div class="research-note-value">{extra_lines}</div></div>'
        if not notes_html:
            notes_html = '<p class="muted">No notes recorded.</p>'

        return f'''
          <section class="panel">
            <h2>Research Record</h2>
            <div class="record-list">{rows_html}</div>
            <div class="research-notes">
              <p class="record-label">Notes</p>
              {notes_html}
            </div>
          </section>
        '''

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
                  <img src=\"{self.app_href('/media/' + str(image_path).lstrip('/'))}\" alt=\"{escape(image.get('altText') or distillery.get('name', 'Distillery'))}\" loading=\"lazy\" />
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

            research_record = self.render_research_record(
              str(distillery.get("whyStudy") or ""),
              str(distillery.get("keyFocus") or ""),
              str(distillery.get("studyStatus") or ""),
              str(distillery.get("operatingStatus") or ""),
              str(distillery.get("websiteConfidence") or ""),
              str(distillery.get("notes") or ""),
            )

            body = f"""
            <section class=\"hero\">
              <p><a href=\"{self.app_href('/database')}\">Back to database</a></p>
              <h1>{escape(str(distillery.get('name') or 'Distillery'))}</h1>
              <p class=\"muted\">{escape(str(distillery.get('country') or ''))} | {escape(str(distillery.get('region') or ''))} | {escape(str(distillery.get('section') or ''))}</p>
              {site_link}
              <div class=\"chips\">{style_chips}</div>
            </section>

            <div class=\"grid\" style=\"grid-template-columns: 1fr;\">
              {research_record}

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
              <img src=\"{self.app_href('/media/' + str(row['local_path']).lstrip('/'))}\" alt=\"{escape(row['alt_text'] or distillery['name'])}\" loading=\"lazy\" />
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

        research_record = self.render_research_record(
          str(distillery["why_study"] or ""),
          str(distillery["key_focus"] or ""),
          str(distillery["study_status"] or ""),
          str(distillery["operating_status"] or ""),
          str(distillery["website_confidence"] or ""),
          str(distillery["notes"] or ""),
        )

        body = f"""
        <section class=\"hero\">
          <p><a href=\"{self.app_href('/database')}\">Back to database</a></p>
          <h1>{escape(distillery['name'])}</h1>
          <p class=\"muted\">{escape(distillery['country'] or '')} | {escape(distillery['region'] or '')} | {escape(distillery['section'] or '')}</p>
          {site_link}
          <div class=\"chips\">{style_chips}</div>
        </section>

        <div class=\"grid\" style=\"grid-template-columns: 1fr;\">
          {research_record}

          <section class=\"panel\">
            <h2>Collected Images ({len(images)})</h2>
            <div class=\"images\">
              {image_cards or '<p class="muted">No images collected yet for this distillery. Re-run the crawler with --crawl-images.</p>'}
            </div>
          </section>
        </div>
        """

        self.send_html(self.page_shell(distillery["name"], body, ""))

    def _load_products(self, include_archive: bool = False) -> list[dict]:
        """Load product markdown files from data/products/. Returns list of product dicts."""
        products_dir = self.project_root / "data" / "products"
        if not products_dir.exists():
            return []

        results = []
        dirs_to_scan = [products_dir]
        if include_archive:
            archive_dir = products_dir / "archive"
            if archive_dir.exists():
                dirs_to_scan.append(archive_dir)

        for scan_dir in dirs_to_scan:
            is_archive = scan_dir.name == "archive"
            for md_file in sorted(scan_dir.glob("*.md")):
                if md_file.name == "README.md":
                    continue
                try:
                    text = md_file.read_text(encoding="utf-8")
                except OSError:
                    continue

                # Parse YAML-style frontmatter between --- delimiters
                fm: dict = {}
                body = text
                if text.startswith("---"):
                    end = text.find("\n---", 3)
                    if end != -1:
                        fm_block = text[3:end].strip()
                        body = text[end + 4:].strip()
                        for line in fm_block.splitlines():
                            if ":" in line:
                                key, _, val = line.partition(":")
                                key = key.strip()
                                val = val.strip().strip('"').strip("'")
                                fm[key] = val

                # Coerce typed fields
                try:
                    fm["price_aud"] = float(fm.get("price_aud", 0) or 0)
                except (ValueError, TypeError):
                    fm["price_aud"] = 0.0
                try:
                    fm["stock"] = int(fm.get("stock", 0) or 0)
                except (ValueError, TypeError):
                    fm["stock"] = 0
                raw_avail = str(fm.get("available", "true")).lower()
                fm["available"] = raw_avail not in ("false", "0", "no")
                fm["_archive"] = is_archive
                fm["body"] = body
                if "slug" not in fm or not fm["slug"]:
                    fm["slug"] = md_file.stem
                results.append(fm)

        return results

    def render_products(self) -> None:
        all_products = self._load_products(include_archive=True)
        products = [p for p in all_products if p.get("available") and not p.get("_archive")]

        if not products:
            body = """
<section class="hero">
  <h1>Products</h1>
  <p class="muted">No products are currently available.</p>
</section>"""
            self.send_html(self.page_shell("Products — Reedy Swamp Distillery", body, "/products"))
            return

        category_map: dict[str, dict[str, list[dict]]] = {}
        for product in all_products:
            category_name = str(product.get("category") or "Other")
            category_bucket = category_map.setdefault(category_name, {"all": [], "active": []})
            category_bucket["all"].append(product)
            if product.get("available") and not product.get("_archive"):
                category_bucket["active"].append(product)

        category_order = ["Whiskey", "Gins", "Liqueurs", "Rum", "Vodkas", "Brandy", "Other"]
        sorted_categories = sorted(
            category_map.items(),
            key=lambda item: (
                category_order.index(item[0]) if item[0] in category_order else len(category_order),
                item[0],
            ),
        )

        category_tiles = ""
        category_sections = ""
        for category_name, category_data in sorted_categories:
            category_all_products = sorted(category_data["all"], key=lambda p: str(p.get("title") or ""))
            category_products = sorted(category_data["active"], key=lambda p: str(p.get("title") or ""))
            category_id = re.sub(r"[^a-z0-9]+", "-", category_name.lower()).strip("-") or "other"

            lead_source = category_products[0] if category_products else category_all_products[0]
            lead_image = str(lead_source.get("image") or "")
            lead_title = escape(str(lead_source.get("title") or category_name))
            lead_src = self.app_href(lead_image) if lead_image.startswith("/") else lead_image
            lead_img = (
                f'<img src="{escape(lead_src)}" alt="{lead_title}" class="category-tile-img" loading="lazy" />'
                if lead_image
                else ""
            )

            available_count = len(category_products)
            tile_subtitle = f"{available_count} available" if available_count > 0 else "Currently unavailable"

            category_tiles += f"""
<a class="card-link category-tile" href="#{escape(category_id)}">
  {lead_img}
  <h2>{escape(category_name)}</h2>
  <p class="muted" style="margin:4px 0 0;">{tile_subtitle}</p>
</a>"""

            cards = ""
            for p in category_products:
                slug = escape(str(p.get("slug") or ""))
                title = escape(str(p.get("title") or slug))
                price = escape(str(p.get("price") or ""))
                abv = escape(str(p.get("abv") or ""))
                image = str(p.get("image") or "")
                stock = int(p.get("stock", 0))
                stock_label = f"In stock: {stock}" if stock > 0 else "Out of stock"
                stock_cls = "product-stock-in" if stock > 0 else "product-stock-out"

                img_src = self.app_href(image) if image.startswith("/") else image
                img_html = f'<img src="{escape(img_src)}" alt="{title}" class="product-card-img" loading="lazy" />' if image else ""
                meta_parts = [part for part in [price, abv] if part]
                meta_line = " &middot; ".join(meta_parts)

                cards += f"""
<a class="card-link product-card" href="{self.app_href(f'/products/{slug}')}">
  {img_html}
  <h2>{title}</h2>
  <p class="muted" style="margin:4px 0 6px;">{meta_line}</p>
  <span class="product-stock {stock_cls}">{stock_label}</span>
</a>"""

            if cards:
                section_body = f'<div class="products-grid-3">{cards}</div>'
            else:
                section_body = '<p class="muted" style="margin-top:0;">No products currently in stock for this category.</p>'

            category_sections += f"""
<section id="{escape(category_id)}" class="product-category-section">
  <h2 class="category-heading">{escape(category_name)}</h2>
  {section_body}
</section>"""

        body = f"""
<section class="hero">
  <h1>Products</h1>
  <p class="muted">Browse by spirit category. Select a category card, then open any product for full details.</p>
</section>
<style>
  .category-grid {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin-bottom: 24px;
  }}
  .category-tile-img {{
    width: 100%;
    height: 140px;
    object-fit: cover;
    border-radius: 8px;
    margin-bottom: 10px;
    display: block;
  }}
  .product-category-section {{
    margin-top: 18px;
  }}
  .category-heading {{
    margin: 0 0 10px;
    color: #5d3422;
    border-bottom: 1px solid var(--line);
    padding-bottom: 6px;
  }}
  .products-grid-3 {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }}
  .product-card-img {{
    width: 100%;
    height: 180px;
    object-fit: cover;
    border-radius: 8px;
    margin-bottom: 10px;
    display: block;
  }}
  .product-stock {{
    display: inline-block;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 600;
  }}
  .product-stock-in {{
    background: #d9f0d0;
    color: #2a6b1e;
    border: 1px solid #b2d9a0;
  }}
  .product-stock-out {{
    background: #f5e0e0;
    color: #8b1c1c;
    border: 1px solid #dba9a9;
  }}
  @media (max-width: 1020px) {{
    .category-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .products-grid-3 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  }}
  @media (max-width: 700px) {{
    .category-grid {{ grid-template-columns: 1fr; }}
    .products-grid-3 {{ grid-template-columns: 1fr; }}
  }}
</style>
<section class="category-grid">
  {category_tiles}
</section>
<section>
  {category_sections}
</section>"""
        self.send_html(self.page_shell("Products — Reedy Swamp Distillery", body, "/products"))

    def render_product_detail(self, slug: str) -> None:
        products = self._load_products(include_archive=True)
        product = next((p for p in products if p.get("slug") == slug), None)
        if product is None:
            self.send_error(404, f"Product '{escape(slug)}' not found")
            return

        title = escape(product.get("title", slug))
        price = escape(product.get("price", ""))
        abv = escape(product.get("abv", ""))
        category = escape(product.get("category", ""))
        image = product.get("image", "")
        source_url = product.get("source_url", "")
        stock = int(product.get("stock", 0))
        available = product.get("available", True)
        body_text = escape(product.get("body", ""))

        stock_label = f"In stock: {stock} available" if stock > 0 else "Out of stock"
        stock_cls = "product-stock-in" if stock > 0 else "product-stock-out"
        archive_notice = ""
        if product.get("_archive"):
            archive_notice = '<div class="panel" style="margin-bottom:18px;background:#fff5e0;border-color:#e8c870;"><p style="margin:0;color:#7a5800;">&#9888; This product is from the archive and is not currently available in the online store.</p></div>'

        img_html = ""
        if image:
            img_src = self.app_href(image) if image.startswith("/") else image
            img_html = f'<img src="{escape(img_src)}" alt="{title}" style="width:100%;max-width:420px;border-radius:12px;display:block;margin-bottom:16px;" />'

        # Add to Bag button — links to original store page
        bag_btn = ""
        if source_url and available and stock > 0:
            bag_btn = f'<a href="{escape(source_url)}" target="_blank" rel="noreferrer" class="btn-add-bag">Add to Bag &#x2192;</a>'
        elif not available or stock == 0:
            bag_btn = '<button disabled class="btn-add-bag btn-unavailable">Out of Stock</button>'

        # Share links — same URL pattern as original Reedy Swamp site
        share_html = ""
        if source_url:
            from urllib.parse import quote as urlquote
            su = urlquote(source_url, safe="")
            # Pinterest needs an absolute public URL for the image; use source_image if set,
            # otherwise skip the media parameter (local paths are not usable for sharing).
            share_image = product.get("source_image") or ""
            image_encoded = urlquote(share_image, safe="") if share_image else ""
            title_encoded = urlquote(product.get("title", slug), safe="")
            fb_url = f"https://facebook.com/sharer/sharer.php?u={su}"
            tw_url = f"https://twitter.com/intent/tweet/?text={title_encoded}&url={su}"
            pin_url = f"https://pinterest.com/pin/create/button/?url={su}&media={image_encoded}&description={title_encoded}" if image_encoded else f"https://pinterest.com/pin/create/button/?url={su}&description={title_encoded}"
            share_html = f"""
<div class="product-share">
  <span class="muted" style="font-size:13px;">Share:</span>
  <a href="{escape(fb_url)}" target="_blank" rel="noreferrer" class="share-btn share-fb" aria-label="Share on Facebook">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/></svg>
    Facebook
  </a>
  <a href="{escape(tw_url)}" target="_blank" rel="noreferrer" class="share-btn share-tw" aria-label="Share on X / Twitter">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4 4l16 16M4 20L20 4" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>
    X
  </a>
  <a href="{escape(pin_url)}" target="_blank" rel="noreferrer" class="share-btn share-pin" aria-label="Pin on Pinterest">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.477 2 2 6.477 2 12c0 4.236 2.636 7.855 6.356 9.312-.088-.791-.167-2.005.035-2.868.181-.78 1.172-4.97 1.172-4.97s-.299-.598-.299-1.482c0-1.388.806-2.428 1.808-2.428.853 0 1.267.64 1.267 1.408 0 .858-.546 2.14-.828 3.33-.236.995.499 1.806 1.476 1.806 1.772 0 3.137-1.868 3.137-4.568 0-2.386-1.716-4.054-4.165-4.054-2.836 0-4.5 2.128-4.5 4.328 0 .857.33 1.776.742 2.278a.3.3 0 0 1 .069.286c-.076.314-.244.995-.277 1.134-.044.183-.146.222-.337.134-1.249-.581-2.03-2.407-2.03-3.874 0-3.154 2.292-6.052 6.608-6.052 3.469 0 6.165 2.473 6.165 5.776 0 3.447-2.173 6.22-5.19 6.22-1.013 0-1.966-.527-2.292-1.148l-.623 2.378c-.226.869-.835 1.958-1.244 2.621.937.29 1.931.446 2.962.446 5.522 0 10-4.477 10-10S17.523 2 12 2z"/></svg>
    Pinterest
  </a>
</div>"""

        meta_rows = ""
        for label, value in [
            ("Price", price),
            ("ABV", abv),
            ("Category", category),
            ("Availability", stock_label),
        ]:
            if value:
                cls = f' class="{stock_cls}"' if label == "Availability" else ""
                meta_rows += (
                    f'<div class="record-row">'
                    f'<p class="record-label">{label}</p>'
                    f'<p class="record-value"{cls}>{value}</p>'
                    f'</div>'
                )

        body = f"""
<style>
  .product-stock-in {{ color: #2a6b1e; font-weight: 600; }}
  .product-stock-out {{ color: #8b1c1c; font-weight: 600; }}
  .btn-add-bag {{
    display: inline-block;
    background: var(--accent);
    color: #fff;
    border: 0;
    border-radius: 10px;
    padding: 12px 24px;
    font-size: 16px;
    font-family: inherit;
    cursor: pointer;
    text-decoration: none;
    margin: 16px 0;
    transition: background 120ms;
  }}
  .btn-add-bag:hover {{ background: #7a3218; color: #fff; }}
  .btn-unavailable {{ opacity: 0.5; cursor: not-allowed; background: #999; }}
  .product-share {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 14px;
  }}
  .share-btn {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 13px;
    text-decoration: none;
    border: 1px solid var(--line);
    background: var(--panel);
    color: var(--ink);
    transition: background 120ms;
  }}
  .share-btn:hover {{ background: #ecdabb; color: var(--ink); }}
  .share-fb:hover {{ background: #1877f2; color: #fff; border-color: #1877f2; }}
  .share-tw:hover {{ background: #000; color: #fff; border-color: #000; }}
  .share-pin:hover {{ background: #e60023; color: #fff; border-color: #e60023; }}
  .product-description {{ line-height: 1.7; font-size: 16px; margin-top: 14px; }}
</style>
<nav style="margin-bottom:14px;font-size:13px;">
  <a href="{self.app_href('/products')}">&larr; All Products</a>
</nav>
{archive_notice}
<div class="grid" style="grid-template-columns: minmax(260px, 380px) 1fr; gap: 28px; align-items: start;">
  <div>
    {img_html}
  </div>
  <div>
    <h1 style="margin:0 0 8px 0;">{title}</h1>
    <p class="muted" style="margin:0 0 12px;">{category}</p>
    <div class="panel">
      <div class="record-list">{meta_rows}</div>
    </div>
    {bag_btn}
    {share_html}
    <div class="product-description">
      <p>{body_text}</p>
    </div>
  </div>
</div>"""
        self.send_html(self.page_shell(f"{title} — Products", body, "/products"))

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
    configure_handler_class(
      handler_class=handler_class,
      project_root=Path(".").resolve(),
      db_path=Path(args.db).resolve(),
      web_data_root=Path(args.web_data).resolve(),
      static_mode=args.static_mode,
    )

    server = HTTPServer((args.host, args.port), handler_class)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "db": str(handler_class.db_path)}))
    try:
      server.serve_forever()
    except KeyboardInterrupt:
      pass
    finally:
      server.server_close()


def configure_handler_class(
    handler_class: type[DistillerySiteHandler],
    project_root: Path,
    db_path: Path,
    web_data_root: Path,
    static_mode: bool,
    base_path: str = "/",
  ) -> None:
    handler_class.db_path = db_path.resolve()
    handler_class.project_root = project_root.resolve()
    handler_class.web_data_root = web_data_root.resolve()
    handler_class.static_mode = static_mode
    handler_class.base_path = base_path if base_path.startswith("/") else f"/{base_path}"
    handler_class.phase1_markdown_path = (handler_class.project_root / "PHASE_1_ORIENTATION_FOUNDATIONS_EXPANDED.md").resolve()
    handler_class.phase_pages = {
      "/phase-1": {
        "title": "Orientation and Foundations",
        "description": "Build core whisky literacy: legal definitions, production basics, label terms, and category structure.",
        "source": "PHASE_1_ORIENTATION_FOUNDATIONS_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_1_ORIENTATION_FOUNDATIONS_EXPANDED.md").resolve()),
      },
      "/phase-2": {
        "title": "History",
        "description": "Trace whisky from early records through industrialization, regulation, global expansion, and modern markets.",
        "source": "PHASE_2_HISTORY_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_2_HISTORY_EXPANDED.md").resolve()),
      },
      "/phase-3": {
        "title": "Process",
        "description": "Study end-to-end production: grain, fermentation, distillation, maturation, blending, and bottling choices.",
        "source": "PHASE_3_PROCESS_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_3_PROCESS_EXPANDED.md").resolve()),
      },
      "/phase-4": {
        "title": "Regional Identity",
        "description": "Compare regional styles with evidence by separating geography signals from process and brand storytelling.",
        "source": "PHASE_4_REGIONAL_IDENTITY_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_4_REGIONAL_IDENTITY_EXPANDED.md").resolve()),
      },
      "/phase-5": {
        "title": "Cultural Backgrounds and Social Importance",
        "description": "Examine whisky as culture: identity, symbolism, tourism, community practices, and social narratives.",
        "source": "PHASE_5_CULTURAL_SOCIAL_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_5_CULTURAL_SOCIAL_EXPANDED.md").resolve()),
      },
      "/phase-6": {
        "title": "Distillery Operations, Safety, and Commercial Execution",
        "description": "Focus on execution systems: operations control, safety, compliance, quality management, and go-to-market discipline.",
        "source": "PHASE_6_OPERATIONS_EXECUTION_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_6_OPERATIONS_EXECUTION_EXPANDED.md").resolve()),
      },
      "/phase-7": {
        "title": "Advanced Brand and Region Analysis",
        "description": "Apply advanced frameworks to evaluate claims, evidence quality, price-value, and regional-brand positioning.",
        "source": "PHASE_7_ADVANCED_BRAND_REGION_ANALYSIS_EXPANDED.md",
        "markdown_path": str((handler_class.project_root / "PHASE_7_ADVANCED_BRAND_REGION_ANALYSIS_EXPANDED.md").resolve()),
      },
      "/phase-8": {
        "title": "Starting a Craft Distillery",
        "description": "A practical guide to launching and running a craft distillery: regulation, equipment, capital, staffing, sales, and the real commitments involved.",
        "source": "PHASE_8_STARTING_A_CRAFT_DISTILLERY.md",
        "markdown_path": str((handler_class.project_root / "PHASE_8_STARTING_A_CRAFT_DISTILLERY.md").resolve()),
      },
    }
    handler_class.quiz_markdown_paths = [Path(item["markdown_path"]) for item in handler_class.phase_pages.values()]


if __name__ == "__main__":
    main()
