# Google Analytics + Google Ads Integration Plan (No-Action Planning Doc)

Date: 2026-04-16
Status: Planning only (no implementation in this document)

## 1. Goals

1. Measure which pages and topics are most popular.
2. Track engagement quality (scroll, time on page, outbound clicks, search usage).
3. Monetize selected pages with Google AdSense while protecting user experience.
4. Maintain privacy compliance with consent-aware analytics and ad serving.

## 2. Scope and Success Criteria

### In Scope

1. GA4 setup and event taxonomy for the whisky site.
2. AdSense setup strategy and ad placement plan.
3. Consent and privacy updates required for analytics and advertising.
4. Rollout, QA, and monitoring plan.

### Out of Scope (For This Plan)

1. Any code or infrastructure changes.
2. Legal advice (this plan defines technical compliance tasks only).

### Success Criteria

1. Page-level popularity is visible in GA4 dashboards within 24 hours of deployment.
2. Core engagement events have less than 5% event loss in QA checks.
3. AdSense is approved and serving ads on enabled routes.
4. No material layout shifts from ad slots (CLS stays acceptable).

## 3. Current Architecture Notes

1. The site is rendered through Python route rendering and static build output.
2. Primary routing and page shell logic are generated from a central renderer.
3. Static output is published under the GitHub Pages build path.

Implication: analytics and ad tags should be injected once in the shared page shell/template path so all public pages inherit the integration.

## 4. Measurement Strategy (GA4)

### 4.1 Account and Property Structure

1. Create one GA4 property for production site traffic.
2. Optional: separate GA4 property for local/staging traffic to avoid polluting production reports.
3. Define at least two data streams if needed:
   - Web (production domain)
   - Web (staging/local testing domain)

### 4.2 Event Taxonomy

Use GA4 default events plus custom events relevant to content popularity.

Recommended custom events:

1. `content_view`
   - Trigger: route/page render complete.
   - Params: `content_type` (phase, resource, distillery, glossary, quiz), `content_id`, `slug`, `section`.
2. `content_scroll_depth`
   - Trigger: 25/50/75/90% scroll milestones.
   - Params: `content_type`, `content_id`, `scroll_percent`.
3. `resource_outbound_click`
   - Trigger: clicks on external links.
   - Params: `target_domain`, `target_url`, `source_page`.
4. `site_search`
   - Trigger: internal search submit.
   - Params: `search_term`, `results_count`, `source_page`.
5. `quiz_interaction`
   - Trigger: quiz start/submit/complete.
   - Params: `quiz_id`, `score`, `completion_time_sec`.
6. `distillery_profile_engagement`
   - Trigger: deep interactions on distillery pages.
   - Params: `distillery_id`, `action_type` (gallery_open, website_click, map_click).

### 4.3 Reporting Views Needed

1. Top pages by `views`, `engaged_sessions`, and average engagement time.
2. Top content categories (phase/resource/distillery/glossary/quiz).
3. Entry pages vs exit pages.
4. Most-clicked outbound resources.
5. Search terms with high volume and low engagement (content gap finder).

### 4.4 Popularity KPI Definitions

Define a weighted popularity score to avoid over-valuing raw pageviews:

`popularity_score = (1.0 * page_views) + (1.5 * engaged_sessions) + (0.8 * outbound_clicks) + (1.2 * deep_scroll_sessions)`

Use this score in monthly "what to expand next" planning.

## 5. Monetization Strategy (AdSense)

### 5.1 Placement Principles

1. Prioritize informational pages with sustained engagement (long-form learning pages).
2. Avoid ad overload on utility-heavy pages (quizzes, cart, dense interactive tools).
3. Keep ad density conservative at launch.

### 5.2 Route-Level Ad Policy (Initial)

Enable ads on:

1. Phase/lesson pages.
2. Resource pages.
3. Glossary pages (light placement only).

Delay ads on:

1. Quiz flow pages.
2. Cart-related pages.
3. Privacy and policy pages.

### 5.3 Initial Ad Slots

1. In-content unit after first meaningful section.
2. Mid-content unit for long pages only.
3. Optional sticky anchor ad on mobile if UX remains acceptable.

### 5.4 Ad Performance KPIs

1. RPM (revenue per thousand pageviews).
2. Viewability.
3. CTR.
4. Revenue by route and content type.
5. Bounce-rate shift after ads are enabled.

## 6. Privacy, Consent, and Policy Work

### 6.1 Consent Requirements

1. Implement consent banner before non-essential analytics/ads storage.
2. Configure Google Consent Mode (current standard) with default denied state where required.
3. Fire GA4 and AdSense only after consent or in consent-mode-compliant way.

### 6.2 Policy Updates

1. Update privacy policy with:
   - Analytics tracking purpose.
   - Advertising cookies and partners.
   - User controls and opt-out guidance.
2. Add a cookie/consent policy page if jurisdictional requirements apply.

### 6.3 Regional Compliance Checklist

1. GDPR/EEA consent handling.
2. UK GDPR handling.
3. CCPA/CPRA disclosure language (if relevant audience).
4. Age-sensitive ad settings if needed.

## 7. Technical Integration Plan (No Code Yet)

### Phase A: Foundations

1. Create GA4 property and gather Measurement ID.
2. Create AdSense account and verify site ownership.
3. Define environment variables/secrets strategy for IDs.
4. Finalize event taxonomy and naming conventions.

### Phase B: Instrumentation

1. Inject GA4 base tag in global page shell.
2. Add route-aware `content_view` emission.
3. Add custom event hooks for search, quiz, outbound links, and scroll depth.
4. Add AdSense script and reserved ad containers for selected routes.

### Phase C: Consent and Governance

1. Integrate consent banner logic.
2. Gate analytics/ads behavior by consent state.
3. Update privacy/cookie policy text.
4. Add documentation for future maintenance.

### Phase D: Validation and Launch

1. Validate GA4 events in DebugView and realtime.
2. Validate route targeting for ad-enabled vs ad-disabled pages.
3. Check Core Web Vitals and layout stability after ad slot insertion.
4. Launch in staged rollout (for example 25% routes, then 100%).

## 8. QA and Acceptance Checklist

1. Each public route sends exactly one `content_view` event per load.
2. Scroll milestones fire once per threshold.
3. Outbound click events capture target domain correctly.
4. Quiz and search events include required parameters.
5. Consent decline path suppresses non-essential tracking.
6. Ad slots do not overlap critical content or controls.
7. No severe CLS regressions from ad loading.

## 9. Dashboard Plan

Build these dashboards in GA4/Looker Studio:

1. Content Popularity Dashboard
   - Top pages, top categories, popularity score trend.
2. Engagement Quality Dashboard
   - Scroll depth completion, engaged sessions, outbound clicks.
3. Monetization Dashboard
   - Ad-enabled pages, revenue by route type, RPM trend.
4. Content Opportunity Dashboard
   - High traffic + low engagement pages that need improvement.

## 10. Risks and Mitigations

1. Risk: ad clutter hurts learning experience.
   - Mitigation: conservative slot count and route-level exclusions.
2. Risk: compliance gaps with consent.
   - Mitigation: consent mode first, policy update before launch.
3. Risk: analytics noise from bots/internal traffic.
   - Mitigation: internal traffic filters and bot filtering.
4. Risk: poor ad performance on low-intent pages.
   - Mitigation: only enable ads on validated high-engagement routes.

## 11. Rollout Timeline (Example)

1. Week 1: account setup, taxonomy sign-off, privacy text draft.
2. Week 2: instrumentation implementation in staging.
3. Week 3: QA, consent validation, dashboard build.
4. Week 4: production soft launch and KPI review.

## 12. Decision Log Needed Before Build

1. Which routes are ad-free by policy.
2. Acceptable ad density and allowed ad formats.
3. Consent framework/tool choice.
4. Primary KPI for optimization (revenue, engagement, or blended).
5. Whether to use a tag manager or direct script integration.

## 13. Practical Next Steps (Still Planning)

1. Approve event taxonomy and parameter schema.
2. Approve initial ad placement matrix by route category.
3. Approve privacy/cookie policy additions.
4. Approve phased rollout and KPI gates.