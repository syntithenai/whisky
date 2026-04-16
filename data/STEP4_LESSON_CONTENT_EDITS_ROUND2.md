# Step 4 Implementation: Concrete Lesson Content Edits (Round 2)

Date: 2026-04-17

## 1) What I Indexed First (Across All Current Scraped Files)

I rebuilt the source index from the current corpus before proposing edits.

Corpus scanned:
- 485 markdown pages
- 39 source directories
- Root: `data/crawl_markdown/`

Saved index artifact:
- `data/scrape_topic_density_index.json`

Ranking axes used:
1. Product density: product names + flavor words + ABV/price signals.
2. Process density: chemical terms + equipment terms + process vocabulary.
3. Regulatory density: glossary/legal terms + excise/tax/label compliance language.

Top source clusters from this run:

Product-dense clusters:
1. `resource-distiller-magazine`
2. `resource-national-research-institute-of-brewing-nrib`
3. `resource-whiskyfun-japan-archive`
4. `resource-stilldragon-learn`
5. `resource-whisky-notes`

Process-dense clusters:
1. `resource-distiller-magazine`
2. `resource-japan-national-tax-agency-whisky-labelling-standards`
3. `resource-american-craft-spirits-association`
4. `resource-stilldragon-learn`
5. `resource-whisky-magazine`

Regulatory-dense clusters:
1. `resource-japan-national-tax-agency-whisky-labelling-standards`
2. `resource-distiller-magazine`
3. `resource-american-craft-spirits-association`
4. `resource-scotch-whisky-association`
5. `resource-australian-distillers-association`

## 2) Extraction Transparency: What Is Reliable vs Limited

Reliable extraction (high utility for lesson edits):
1. Structured rule summaries in legal/compliance pages.
2. Technical concept pages with explicit compounds/equipment/process terms.
3. Direct product/release pages with ABV/price/availability fields.

Current limitations in this corpus snapshot:
1. Several source directories now contain fewer direct product detail pages than earlier runs.
2. Some pages are summary-heavy or nav-heavy; good for topic routing, weak for quote-level evidence.
3. Some PDF-derived pages are excellent conceptually but should be paraphrased, not quoted heavily.
4. Product examples are available, but fewer high-confidence direct product pages exist right now.

How this affects the lesson plan:
1. I prioritize edits that improve conceptual rigor and compliance literacy first.
2. I still include product-lifecycle edits, but with tighter confidence notes.

Confidence key:
- A: direct, structured, high confidence.
- B: useful but partially summary-heavy.
- C: discovery-only (not used for lesson prose edits).

## 3) Concrete Edit List by Lesson File

Format per edit:
- Edit ID
- Target section
- Exact edit action
- Source files
- Why useful
- Confidence

---

## PHASE_2_HISTORY_EXPANDED.md

### P2-01
Target section:
- `## 9. Industrialization: The Coffey Still and the Rise of Blending`
- `### Aeneas Coffey and the Invention That Changed Everything`

Edit action:
- Add a new subsection: `### Evidence Note: Why Column Stills Won Commercially`
- Add 1 paragraph on throughput/cost changes and one 4-bullet comparison (pot vs column).

Source files:
- `data/crawl_markdown/resource-whisky-science/2013-08-history-of-column-still-html.md`

Usefulness:
- Links industrial history directly to process economics.

Confidence: A

### P2-02
Target section:
- `## 3. Scotland: Highlands, Illicit Stills, and the Excise Wars`
- `### The 1823 Excise Act: From Outlaws to Industry`

Edit action:
- Add a modern comparison callout: `Then vs Now: Duty Pressure Still Shapes Producers`.
- Add 3 bullets tying historical excise tension to current duty debates.

Source files:
- `data/crawl_markdown/resource-scotch-whisky-association/newsroom-scotch-whisky-association-responds-to-rise-in-excise-duty.md`
- `data/crawl_markdown/resource-australian-distillers-association/393901-resources-documents-2023-20pre-budget-20submission-pdf.md`

Usefulness:
- Makes tax history operationally relevant.

Confidence: A

### P2-03
Target section:
- `## 12. Empire, Trade, and the Global Rise of Scotch`

Edit action:
- Add `### Export/Policy Friction in the Modern Era` mini-case with 4 bullets.

Source files:
- `data/crawl_markdown/resource-scotch-whisky-association/newsroom-2025-export-figures.md`
- `data/crawl_markdown/resource-scotch-whisky-association/newsroom-us-tariffs-increase-to-15.md`

Usefulness:
- Updates history chapter with contemporary policy continuity.

Confidence: B

---

## PHASE_3_PROCESS_EXPANDED.md

### P3-01
Target section:
- `## 8. Fermentation: Where Spirit Personality Starts`
- `### Lactic and Fruity Pathways`

Edit action:
- Add subsection: `### Yeast Physiology Levers That Actually Move Flavor`.
- Include concise points on attenuation, flocculation, sulfur compounds, and ester risk.

Source files:
- `data/crawl_markdown/resource-whisky-science/2011.md`

Usefulness:
- Upgrades fermentation section from broad overview to operational mechanism.

Confidence: A

### P3-02
Target section:
- `## 11. Column Stills: Continuous Production and Style Control`

Edit action:
- Add a `History-to-Design` sidebar: how column architecture affects reflux and spirit style.

Source files:
- `data/crawl_markdown/resource-whisky-science/2013-08-history-of-column-still-html.md`

Usefulness:
- Better continuity between engineering and flavor outcomes.

Confidence: A

### P3-03
Target section:
- `## 7. Mashing: Turning Starch Potential Into Wort`

Edit action:
- Add an `Oak impact preview` note that introduces why cask chemistry must be considered early in style planning.

Source files:
- `data/crawl_markdown/resource-distiller-magazine/wp-content-uploads-2015-04-enartis-oak-in-distilled-beverage-adi-april-2015-ec-pdf.md`

Usefulness:
- Helps students think process-end-to-end, not as isolated stages.

Confidence: A

### P3-04
Target section:
- `## 9. Distillation: Selection, Not Simple Purification`

Edit action:
- Add a practical checklist: batch vs continuous decision factors for small distilleries.

Source files:
- `data/crawl_markdown/resource-stilldragon-learn/blog-distillery-planning-series-batch-vs-continuous.md`

Usefulness:
- Converts theory into a plant-design decision framework.

Confidence: B

---

## PHASE_4_REGIONAL_IDENTITY_EXPANDED.md

### P4-01
Target section:
- `## 6. Japan: Precision Blending and Controlled Diversity`
- `### 6.2 Identity Pressure After Global Demand Surges`

Edit action:
- Add `Release Economics Snapshot (Japan)` with ABV, price, availability, and cask narrative.

Source files:
- `data/crawl_markdown/resource-dekanta-japanese-whisky-blog-market/products-suntory-hakushu-story-of-distillery-2024-edition.md`

Usefulness:
- Gives one high-confidence direct product page to anchor Japan identity claims.

Confidence: A

### P4-02
Target section:
- `## 2. Scotland: Regional Myth, Real Process, and Global Prestige`

Edit action:
- Add a case vignette on Brora: scarcity, ABV, bottle count, and in-person distribution.

Source files:
- `data/crawl_markdown/resource-whisky-magazine/articles-brora-toasts-its-first-whisky-coming-of-age-since-reopening.md`

Usefulness:
- Adds hard market signals to regional storytelling.

Confidence: A

### P4-03
Target section:
- `## 9. Regional Style vs Brand Identity: A Practical Matrix`

Edit action:
- Add one matrix row: `Policy-defined identity` (US ASM and English GI rules).

Source files:
- `data/crawl_markdown/resource-whisky-magazine/articles-american-single-malt-recognised-as-official-category-by-federal-law.md`
- `data/crawl_markdown/resource-whisky-magazine/articles-english-whisky-gi-application-is-damaging-to-single-malt-claims-swa.md`

Usefulness:
- Clarifies the difference between legal category and sensory style.

Confidence: A

### P4-04
Target section:
- `## 8. Australia: The Deepest Regional Grid in Your Database`

Edit action:
- Add a note on why tax/excise conditions affect regional product strategy and release cadence.

Source files:
- `data/crawl_markdown/resource-australian-distillers-association/393901-resources-documents-2023-20pre-budget-20submission-pdf.md`

Usefulness:
- Adds commercial realism to Australian regional analysis.

Confidence: A

---

## PHASE_5_CULTURAL_SOCIAL_EXPANDED.md

### P5-01
Target section:
- `## 7. Global Modern Culture: From Dram to Asset`
- `### 7.3 Luxury Packaging and Symbolic Value`

Edit action:
- Add a mini-case on couture collaboration and symbolic pricing.

Source files:
- `data/crawl_markdown/resource-whisky-magazine/articles-couture-expressions-inside-johnnie-walkers-collaboration-with-balmain-creative-director-olivier-rousteing.md`

Usefulness:
- Demonstrates how non-liquid factors shape cultural value.

Confidence: A

### P5-02
Target section:
- `## 9. Place-Making and Distillery Tourism`

Edit action:
- Add visitor-center design example (heritage architecture + education + commercial goals).

Source files:
- `data/crawl_markdown/resource-whisky-magazine/articles-glencadam-shares-treasured-traditions-with-the-opening-of-its-first-visitor-centre.md`

Usefulness:
- Strengthens tourism/place-making section with a concrete distillery case.

Confidence: B

### P5-03
Target section:
- `## 8. Gender, Class, and Inclusion in Whisky Culture`

Edit action:
- Add a short comparative note on how modern brand partnerships and media narratives signal inclusion and status.

Source files:
- `data/crawl_markdown/resource-whisky-magazine/articles-chivas-regal-puts-itself-in-pole-position-with-charles-leclerc-partnership.md`
- `data/crawl_markdown/resource-whisky-magazine/articles-a-crazy-new-idea-feddie-ocean-distillerys-community-spirit.md`

Usefulness:
- Expands inclusion discussion with contemporary media evidence.

Confidence: B

---

## PHASE_6_OPERATIONS_EXECUTION_EXPANDED.md

### P6-01
Target section:
- `## 7. Label and Regulatory Execution`
- `### 7.1 Legal Label Fundamentals`

Edit action:
- Add a side-by-side legal definition table: US ASM, English GI proposal, UK HMRC operational guide context.

Source files:
- `data/crawl_markdown/resource-whisky-magazine/articles-american-single-malt-recognised-as-official-category-by-federal-law.md`
- `data/crawl_markdown/resource-whisky-magazine/articles-english-whisky-gi-application-is-damaging-to-single-malt-claims-swa.md`
- `data/crawl_markdown/resource-uk-hmrc-excise-notice-39/guidance-alcoholic-products-technical-guide.md`

Usefulness:
- Gives legal clarity that operations teams can use directly.

Confidence: A

### P6-02
Target section:
- `## 11. Australia Operational Compliance Map (Expanded Use)`

Edit action:
- Add one quantified excise pressure example and one control recommendation for growth-stage distilleries.

Source files:
- `data/crawl_markdown/resource-australian-distillers-association/393901-resources-documents-2023-20pre-budget-20submission-pdf.md`

Usefulness:
- Makes compliance map financially concrete.

Confidence: A

### P6-03
Target section:
- `## 8. Safety Program: Operating in a Flammable Process Environment`

Edit action:
- Add a compliance-adjacent checklist: insurance, permits, and audit-readiness records.

Source files:
- `data/crawl_markdown/resource-distiller-magazine/wp-content-uploads-2015-04-aaron-linden-insurance-adi-2015-pdf.md`
- `data/crawl_markdown/resource-distiller-magazine/wp-content-uploads-2015-04-adi-2015-ttb-audits-what-to-expect-pdf.md`

Usefulness:
- Converts safety chapter into inspection-ready operations behavior.

Confidence: A

---

## PHASE_9_CHEMISTRY_OF_WHISKY_EXPANDED.md

### P9-01
Target section:
- `## 22. Esters in Mature Whisky: Fruit, Lift, and Fragility`

Edit action:
- Add `Yeast-to-ester pathway` micro-box with named compounds and practical controls.

Source files:
- `data/crawl_markdown/resource-whisky-science/2011.md`

Usefulness:
- Adds mechanism-level clarity for sensory chemistry.

Confidence: A

### P9-02
Target section:
- `## 29. Wood Chemistry II: Oxygen, Time, and Secondary Reactions`

Edit action:
- Add oxygen ingress and micro-oxygenation summary with practical implications.

Source files:
- `data/crawl_markdown/resource-distiller-magazine/wp-content-uploads-2015-04-enartis-oak-in-distilled-beverage-adi-april-2015-ec-pdf.md`

Usefulness:
- Improves the cask-chemistry section with quant-style thinking.

Confidence: A

### P9-03
Target section:
- `## 43. Analytical Chemistry Toolkit for Distillery Control`

Edit action:
- Add a subsection on ABV measurement rigor and spectroscopy fingerprints in QC.

Source files:
- `data/crawl_markdown/resource-distiller-magazine/wp-content-uploads-2015-04-gary-spedding-quality-considerations1-pdf.md`

Usefulness:
- Gives concrete instrumentation context for quality labs.

Confidence: A

### P9-04
Target section:
- `## 38. Ethyl Carbamate and Other Regulatory Chemical Concerns`

Edit action:
- Add a compliance-bridge paragraph tying chemical risk controls to label/duty/record systems.

Source files:
- `data/crawl_markdown/resource-uk-hmrc-excise-notice-39/guidance-alcoholic-products-technical-guide.md`
- `data/crawl_markdown/resource-japan-national-tax-agency-whisky-labelling-standards/law-kokuji-pdf-0026003-091-06-pdf.md`

Usefulness:
- Connects chemistry and compliance, reducing silo thinking.

Confidence: B

---

## PHASE_10_BIOCHEMISTRY_OF_WHISKY_EXPANDED.md

### P10-01
Target section:
- `## 9. Nutrient Biochemistry and Nitrogen Management`

Edit action:
- Add one `Cross-domain caution` note: wine fermentation nutrient guidance can inform distillers, but transfer must be validated per mash matrix.

Source files:
- `data/crawl_markdown/resource-australian-wine-research-institute-awri/wp-content-uploads-2023-02-s2327-pdf.md`

Usefulness:
- Introduces disciplined transfer-learning instead of copy-paste assumptions.

Confidence: B

### P10-02
Target section:
- `## 17. Fermentation Time, Flavor, and Reliability Tradeoff Map`

Edit action:
- Add a practical tradeoff table with three fermentation windows and likely biochemical effects.

Source files:
- `data/crawl_markdown/resource-whisky-science/2011.md`

Usefulness:
- Makes tradeoff map easier to apply in operations planning.

Confidence: A

### P10-03
Target section:
- `## 21. Common Failure Modes and Biochemical Root Causes`

Edit action:
- Add 3 troubleshooting signatures tied to sulfur persistence, yeast stress, and poor attenuation.

Source files:
- `data/crawl_markdown/resource-whisky-science/2011.md`
- `data/crawl_markdown/resource-distiller-magazine/wp-content-uploads-2015-04-gary-spedding-quality-considerations1-pdf.md`

Usefulness:
- Improves diagnostic quality of the failure-mode section.

Confidence: A

---

## PHASE_11_DISTILLERY_EQUIPMENT_EXPANDED.md

### P11-01
Target section:
- `## 3. Small Distillery Equipment Stack (Single-Operator Friendly)`

Edit action:
- Add phased procurement list: launch-stage, stability-stage, and scale-stage equipment.

Source files:
- `data/crawl_markdown/resource-stilldragon-learn/blog-5-equipment-must-haves-in-a-new-distillery.md`
- `data/crawl_markdown/resource-stilldragon-learn/blog-choosing-the-right-distillery-equipment.md`

Usefulness:
- Gives startup learners a practical sequencing model.

Confidence: B

### P11-02
Target section:
- `## 8. Utilities, CIP, and Safety Infrastructure`

Edit action:
- Add a CIP decision matrix: when to install CIP and when manual protocols are acceptable.

Source files:
- `data/crawl_markdown/resource-stilldragon-learn/blog-is-a-cip-right-for-you.md`
- `data/crawl_markdown/resource-stilldragon-learn/blog-its-time-to-clean-your-equipment-from-an-experienced-brewer.md`

Usefulness:
- Adds realistic sanitation strategy guidance.

Confidence: B

### P11-03
Target section:
- `## 12. Common Failure Modes in Equipment Planning`

Edit action:
- Add a risk list for building constraints, permit mismatch, and retrofit costs.

Source files:
- `data/crawl_markdown/resource-stilldragon-learn/blog-building-requirements-for-a-distillery.md`
- `data/crawl_markdown/resource-distiller-magazine/wp-content-uploads-2015-04-adi-2015-permits-permits-online-pdf.md`

Usefulness:
- Prevents common capex mistakes in real projects.

Confidence: A

## 4) First Five Edits To Execute (Recommended Sequence)

1. P6-01 (legal definitions table: US ASM + English GI + HMRC technical guide)
2. P9-03 (ABV measurement and spectroscopy quality controls)
3. P4-01 (Japan release economics anchored on Hakushu 2024 direct product page)
4. P3-01 (fermentation/yeast physiology mechanism upgrade)
5. P11-03 (building requirements and permit-failure risk map)

Why this sequence:
- Highest confidence sources.
- Highest impact on learner clarity (law, chemistry controls, process realism).
- Requires minimal speculative interpretation.

## 5) Implementation Note

This document is intentionally an edit specification, not prose patches.
Each item can now be implemented directly in the target phase files with citation callouts to the listed source pages.
