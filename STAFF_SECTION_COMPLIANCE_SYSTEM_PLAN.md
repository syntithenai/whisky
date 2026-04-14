# Staff Section + Compliance Management System Plan (Planning Only)

## 0. Scope and Intent

This document is a planning artifact only. It proposes how to add a staff-only section to the whisky site, protected by Google login, with:

- a staff SOP hub
- an integrated management system for stock management and process control
- SOP updates that link directly into the management system workflows

No implementation steps are executed in this document.

---

## 1. Vision

Create a single operating system for craft distillery execution where compliance is a natural byproduct of daily work, not separate paperwork.

Design goal:

- operators scan once, confirm once, and keep moving
- supervisors review exceptions and trends, not raw log noise
- audit-ready records are generated automatically from workflow events

This addresses recurring themes in training materials:

- traceability must be fast and complete (supplier -> batch -> cask -> bottling lot -> customer)
- excise and stock records must be daily controls, not periodic admin
- label and packaging errors must be blocked before release
- CAPA/incident/non-conformance loops must close with evidence
- SOPs must be versioned, current, and tied to real execution

---

## 2. Outcomes

### 2.1 Business and Compliance Outcomes

1. One-click regulator-ready exports for:
- spirit stock account and movement ledger
- batch genealogy and traceability map
- bottling reconciliation and variance investigation
- recall drill reports and CAPA closure evidence

2. Faster recall performance:
- bottle/lot to source materials trace in minutes, not hours

3. Reduced compliance risk:
- release gates prevent shipment when critical checks are missing

4. Lower admin burden:
- target 60-80% reduction in manual re-entry from paper/spreadsheets

### 2.2 Operational Outcomes

1. Shift-start and shift-close checklists become guided workflows.
2. Deviations trigger structured response, ownership, and due dates.
3. Weekly management review is auto-assembled from captured events and KPI trends.

---

## 3. Staff Section Product Definition

## 3.1 Header and Access

Add a Staff button in the global header:

- label: Staff
- state when logged out: opens Google Sign-In
- state when logged in: opens staff dashboard

Access policy:

- allow only approved Google Workspace domain(s) and/or explicit allowlist emails
- unauthorized users receive denied page with no staff data leakage

Session behavior:

- short-lived access token + refresh strategy
- explicit logout button in staff top bar
- session timeout and re-auth on sensitive actions (release approvals, inventory adjustments)

## 3.2 Information Architecture (Staff)

1. Staff Home (role-based cards)
2. SOP Hub
3. Production Records
4. Inventory and Excise
5. Quality and Release
6. Bottling and Packaging
7. Incidents / Non-Conformance / CAPA
8. Recall and Traceability Drills
9. Reports and Regulatory Exports
10. Admin (roles, users, document control, integrations)

Roles (minimum):

- Operator
- Quality
- Warehouse
- Production Lead
- Compliance/Regulatory
- Management
- Admin

---

## 4. Minimal Data Entry Strategy (Core Principle)

## 4.1 Data Entry Rules

1. Capture once at source; reuse everywhere.
2. Scan IDs instead of typing IDs.
3. Pre-fill from master data and prior step context.
4. Use exception-driven forms (show extra fields only on out-of-spec/deviation).
5. Auto-calculate derived values (LPA, ABV correction factors, reconciliation deltas).
6. Convert repeated free text into controlled picklists.
7. Voice-to-text allowed only for notes; structured fields remain standardized.

## 4.2 UX Patterns

- QR/barcode labels for material lots, tanks, casks, and bottling lots
- mobile-first operator screens for floor use
- offline queue for warehouse/production weak-signal zones
- one-tap "same as last run" templates for recurring operations
- guided wizard for each SOP execution path

## 4.3 Data Quality Controls

- required fields only when legally/operationally necessary
- hard validation for critical controls (ABV, lot code format, release status)
- soft warnings for unusual but possible values
- immutable audit trail for edits and approvals

---

## 5. Compliance Management System Modules

## 5.1 SOP Execution Engine

Purpose:

- turn SOPs into executable digital workflows with signoff and evidence capture

Features:

- SOP version control with effective dates
- role-based step ownership
- critical-limit guardrails
- forced deviation capture when limits are breached
- training acknowledgement tied to SOP revisions

## 5.2 Stock and Spirit Account

Purpose:

- maintain continuous stock and excise-ready records

Tracks:

- raw materials (received/quarantine/released/rejected)
- WIP (mash/wort/wash/distillate)
- cask inventory and movements
- finished goods and dispatch
- losses (evaporation, breakage, leaks, scrap)

Auto outputs:

- movement ledger
- period reconciliation
- duty-support reports

## 5.3 Process Control and Batch Records

Capture:

- mash, fermentation, distillation, cask fill, bottling records
- parameter trends (gravity, temperature, ABV, cut points)
- release gates between process stages

Smart features:

- trend anomaly flags
- intervention prompts based on SOP thresholds

## 5.4 Quality, Release, and Lab

- hold/release decisions with reason codes
- sampling chain-of-custody
- out-of-spec workflow -> non-conformance -> CAPA
- pre-release compliance checklist (including packaging/label verification)

## 5.5 Incident, Non-Conformance, CAPA

- quick incident capture in under 60 seconds
- severity matrix and escalation routing
- root cause workflow
- CAPA assignment, due dates, effectiveness check

## 5.6 Recall and Traceability

- one-step backward and forward trace graph
- mock recall simulator with timer and completeness scoring
- unresolved quantity tracking (shipped/recovered/quarantined)
- post-drill action plan generation

## 5.7 Reporting and Audits

Dashboards:

- compliance health
- inventory integrity
- process drift
- CAPA closure performance
- recall readiness

Exports:

- CSV, PDF, and regulator/auditor packs

---

## 6. SOP Hub Plan and Required Linking

Each SOP page should include a new section:

- Digital Workflow Link
- Required Records in System
- Escalation Path

Proposed linking pattern for existing SOP files:

- sops/01_raw_receiving_quarantine_release.md -> /staff/workflows/raw-receiving
- sops/02_milling_mashing_lautering.md -> /staff/workflows/mashing-lautering
- sops/03_yeast_handling_pitch_protocol.md -> /staff/workflows/yeast-pitch
- sops/04_fermentation_monitoring_intervention.md -> /staff/workflows/fermentation-monitoring
- sops/05_distillation_cuts_spirit_handling.md -> /staff/workflows/distillation-cuts
- sops/06_cask_receiving_filling_movement_leak_response.md -> /staff/workflows/cask-management
- sops/07_cip_sanitation_verification.md -> /staff/workflows/cip-sanitation
- sops/08_sampling_lab_release.md -> /staff/workflows/lab-release
- sops/09_bottling_setup_in_line_checks_reconciliation.md -> /staff/workflows/bottling-reconciliation
- sops/10_non_conformance_management.md -> /staff/workflows/non-conformance
- sops/11_incident_near_miss_reporting.md -> /staff/workflows/incidents-near-miss
- sops/12_recall_traceability_exercises.md -> /staff/workflows/recall-traceability

Note: links above are target routes for implementation planning; final paths can be adjusted to match routing conventions.

---

## 7. Data Model Blueprint (High Level)

Core entities:

- users, roles, permissions
- sop_documents, sop_versions, training_acknowledgements
- materials, supplier_lots, receiving_events, quarantine_status
- batches, process_steps, measurements
- casks, cask_events, warehouse_locations
- bottling_runs, packaging_materials, reconciliation_records
- samples, lab_results, release_decisions
- incidents, non_conformances, capa_actions
- recall_events, traceability_links, drill_results
- inventory_ledger, excise_ledger, report_snapshots

Cross-cutting requirements:

- immutable event log
- full who/when/what audit metadata
- e-signature support for critical approvals
- document attachment support (COA, photos, calibration certs)

---

## 8. Technology and Architecture Plan

## 8.1 Frontend

- keep current public site UX for non-staff pages
- add Staff entry in shared header
- add staff web app shell optimized for desktop + mobile floor devices

## 8.2 Auth

Google identity options:

1. OAuth/OIDC via Google Identity Services with backend token verification
2. Firebase Authentication (Google provider) if preferring managed auth flows

Mandatory controls:

- allowlist/domain restriction
- role bootstrap + admin grant workflow
- server-side authorization checks on every staff API

## 8.3 Backend

Recommended:

- dedicated staff API layer (Python FastAPI or equivalent)
- transactional datastore for compliance records (PostgreSQL recommended)
- append-only event store table for auditability

## 8.4 Deployment Modes

Because public pages can be static-exported, while staff requires secure auth + protected APIs:

- keep public site static-compatible
- host staff app + API on secure runtime (container or managed platform)
- optionally reverse-proxy under /staff for a unified domain experience

## 8.5 Integration With Existing Project

Planned touchpoints:

- scripts/serve_site.py: header navigation + staff route handoff
- scripts/build_github_pages.py: exclude protected runtime pages from static export, keep public docs and SOP links intact
- sops/*.md: add digital workflow links and records mapping sections

---

## 9. Compliance Coverage Matrix

## 9.1 Key Risks From Training Material and Responses

1. Traceability gaps and manual reconstruction:
- response: event-linked lot genealogy + mandatory release gate checks

2. Label non-compliance and release errors:
- response: controlled label workflow + release checklist + legal signoff state

3. Packaging reconciliation failures:
- response: expected vs actual reconciliation engine with tolerance alerts

4. Fermentation/distillation drift not acted on early:
- response: threshold-based intervention prompts and deviation workflows

5. CAPA without effectiveness closure:
- response: CAPA lifecycle with verification task and overdue escalation

6. Recall readiness uncertainty:
- response: scheduled mock recall drills with measurable SLA and gap actions

7. Excise and stock account treated as periodic admin:
- response: daily ledger updates auto-generated from process events

---

## 10. Phased Delivery Plan

## Phase 0: Discovery and Compliance Design (2-4 weeks)

Deliverables:

- jurisdiction-specific legal requirements matrix (fields, retention, report formats)
- SOP-to-data-field mapping
- role and approval matrix
- baseline KPI definitions

## Phase 1: Foundation (4-6 weeks)

Deliverables:

- Google login + RBAC
- staff shell and navigation
- document control foundations (SOP hub, versioning metadata)
- audit log framework

## Phase 2: Core Workflows (6-10 weeks)

Deliverables:

- raw receiving/quarantine/release
- fermentation + distillation records
- cask management and movement
- bottling reconciliation
- hold/release decisions

## Phase 3: Compliance Intelligence (4-8 weeks)

Deliverables:

- non-conformance/incidents/CAPA modules
- recall simulator and traceability graph
- excise and stock reporting pack
- management dashboards

## Phase 4: Optimization and Automation (ongoing)

Deliverables:

- scanner integration hardening
- predictive alerts and trend forecasts
- external integration (accounting/LIMS/ERP as needed)
- periodic SOP usability improvements

---

## 11. Acceptance Criteria

Minimum go-live criteria:

1. Google-gated staff access works with role enforcement.
2. All 12 SOPs have digital workflow links and records mapping sections.
3. End-to-end traceability from supplier lot to customer dispatch lot is demonstrable.
4. Release-blocking gates prevent incomplete critical records.
5. Mock recall can account for affected inventory within defined target time.
6. Bottling reconciliation and variance workflows are operational.
7. Audit trail is immutable and exportable.
8. Daily stock/spirit account reports can be generated without manual re-entry.

---

## 12. KPI Framework

Operational KPIs:

- records completed on time (% by workflow)
- manual overrides per 100 batches
- reconciliation variance rate
- CAPA overdue rate
- repeat deviation rate by process step

Compliance KPIs:

- mock recall trace completion time
- missing mandatory field incidents
- release holds due to compliance failures
- excise/report adjustment frequency

Adoption KPIs:

- median data-entry time per workflow
- scans vs typed entries ratio
- staff training completion for current SOP revisions

---

## 13. Governance and Change Control

1. Monthly compliance steering review.
2. Quarterly SOP review cycle tied to workflow analytics.
3. Change advisory process for new fields (must justify legal/operational necessity).
4. Data retention and privacy policy for staff records.

---

## 14. Risks and Mitigations

1. Risk: over-complex forms reduce usage.
- mitigation: strict field minimization, operator testing, progressive disclosure.

2. Risk: auth complexity delays rollout.
- mitigation: implement standard OIDC pattern first, advanced controls second.

3. Risk: fragmented systems duplicate data.
- mitigation: establish system-of-record ownership by domain before build.

4. Risk: SOP updates drift from actual workflows.
- mitigation: SOP and workflow releases are linked and versioned together.

5. Risk: audit failures due to mutable records.
- mitigation: immutable event log + controlled amendment mechanism.

---

## 15. Immediate Planning Next Steps (Still Planning, No Build)

1. Confirm jurisdiction(s) and legal record requirements to finalize mandatory field list.
2. Approve role matrix and approval hierarchy.
3. Approve route and URL convention for staff workflows.
4. Confirm preferred auth stack (Google OIDC direct vs Firebase Auth).
5. Produce field-level SOP mapping sheet before implementation tickets are created.

---

## 16. Dream-Big Extensions (Future)

1. Sensor-assisted auto-capture (tank temperature, flow, ABV instrumentation).
2. AI-assisted anomaly narratives for weekly management packs.
3. Digital twin for cask warehouse loss prediction and maturation planning.
4. Smart recall rehearsal with scenario generation and scoring history.
5. Supplier portal for COA and lot pre-notification to reduce receiving data entry further.
