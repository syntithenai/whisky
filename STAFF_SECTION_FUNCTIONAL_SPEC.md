# Distillery Staff Section — Full Functional Specification

**Document status:** Draft v1.0  
**Date:** 2026-04-14  
**Scope:** Google-authenticated staff area, SOP execution hub, and integrated compliance management system  
**Supersedes:** STAFF_SECTION_COMPLIANCE_SYSTEM_PLAN.md (planning document)

---

## Contents

1. [Document Conventions](#1-document-conventions)
2. [System Context](#2-system-context)
3. [User Roles and Permissions](#3-user-roles-and-permissions)
4. [Authentication and Session Specification](#4-authentication-and-session-specification)
5. [Global Navigation and Shell](#5-global-navigation-and-shell)
6. [Staff Home Dashboard](#6-staff-home-dashboard)
7. [SOP Hub](#7-sop-hub)
8. [Raw Receiving and Quarantine Module](#8-raw-receiving-and-quarantine-module)
9. [Mashing and Wort Production Module](#9-mashing-and-wort-production-module)
10. [Fermentation Module](#10-fermentation-module)
11. [Distillation Module](#11-distillation-module)
12. [CIP and Sanitation Module](#12-cip-and-sanitation-module)
13. [Cask Management Module](#13-cask-management-module)
14. [Sampling and Lab Release Module](#14-sampling-and-lab-release-module)
15. [Bottling and Packaging Module](#15-bottling-and-packaging-module)
16. [Non-Conformance and CAPA Module](#16-non-conformance-and-capa-module)
17. [Incident and Near-Miss Module](#17-incident-and-near-miss-module)
18. [Recall and Traceability Module](#18-recall-and-traceability-module)
19. [Inventory and Excise Ledger](#19-inventory-and-excise-ledger)
20. [Reports and Regulatory Exports](#20-reports-and-regulatory-exports)
21. [Admin Module](#21-admin-module)
22. [Data Model Specification](#22-data-model-specification)
23. [API Surface Specification](#23-api-surface-specification)
24. [SOP Document Update Specification](#24-sop-document-update-specification)
25. [Non-Functional Requirements](#25-non-functional-requirements)
26. [Security Requirements](#26-security-requirements)
27. [Error Handling and Edge Cases](#27-error-handling-and-edge-cases)
28. [Acceptance Criteria by Module](#28-acceptance-criteria-by-module)
29. [Technology Stack Recommendation](#29-technology-stack-recommendation)
30. [Integration With Existing Codebase](#30-integration-with-existing-codebase)
31. [Deployment Script and Runbook](#31-deployment-script-and-runbook)

---

## 1. Document Conventions

### 1.1 Requirement IDs

Every functional requirement uses an ID of the form `FR-<MODULE>-<NNN>`. Non-functional requirements use `NFR-<NNN>`. Acceptance criteria use `AC-<MODULE>-<NNN>`.

Modules:

| Code | Module |
|------|--------|
| AUTH | Authentication |
| SHELL | Navigation shell |
| HOME | Staff home |
| SOP | SOP hub |
| REC | Raw receiving |
| MASH | Mashing/wort |
| FERM | Fermentation |
| DIST | Distillation |
| CIP | CIP/sanitation |
| CASK | Cask management |
| LAB | Sampling/lab |
| BOTT | Bottling/packaging |
| NC | Non-conformance/CAPA |
| INC | Incident/near-miss |
| RCLL | Recall/traceability |
| INV | Inventory/excise |
| RPT | Reports/exports |
| ADMIN | Administration |

### 1.2 Priority

- **P1** — Required for go-live
- **P2** — Required within 90 days of go-live
- **P3** — Planned improvement, not blocking

### 1.3 Status Conventions

Throughout the spec, status fields follow this convention unless otherwise stated in the module:

- `draft` — created, not submitted
- `submitted` — submitted for review
- `approved` — approved by authorized role
- `rejected` — rejected with reason
- `closed` — resolved and archived

---

## 2. System Context

### 2.1 Existing Public Site

The current site is a Python HTTP server (`scripts/serve_site.py`) that renders HTML for the public learning curriculum, distillery database, resources, glossary, and quizzes. A static export (`scripts/build_github_pages.py`) produces a GitHub Pages-compatible build.

**No existing authentication exists.** All current pages are public.

### 2.2 Staff Section Boundary

The staff area is a distinct logical subsystem:

- routes prefixed `/staff/`
- all routes require a valid authenticated session
- the staff backend operates a separate API (`/staff/api/`)
- staff sections are **excluded** from the static export pipeline
- SOPs linked from `sops/*.md` open the public SOP document; the link to the digital workflow is an additional element that requires auth before the workflow opens

### 2.3 Deployment Architecture

```
[Browser]
    │
    ├─ /                   ← Public site (existing serve_site.py or static export)
    ├─ /staff/            ← Staff SPA shell (served by staff backend)
    ├─ /staff/api/        ← REST JSON API (authenticated)
    └─ /auth/             ← OAuth2 callback handler
```

A reverse proxy (e.g., nginx or Caddy) routes `/staff` and `/auth` to the staff backend; all other paths serve the existing public site.

### 2.4 Compliance Context (Australia Primary)

The system is designed to meet Australian requirements as primary:

- ATO excise on spirits framework (spirit stock account, movement records, LPA tracking)
- FSANZ food safety requirements
- State-level RSA and licensing conditions
- APVMA and WHS obligations for chemical handling (CIP chemicals)

The schema and reports are jurisdictionally parameterized to accommodate other markets (e.g., Scotland, USA) as a Phase 3 extension.

### 2.5 Minimum Complexity and Minimum Entry Principles

This specification is constrained by two implementation principles:

1. **Minimum public-site change:** Production public pages remain static on GitHub Pages and do not host auth logic.
2. **Minimum operator data entry:** The staff system defaults, auto-populates, scans, and derives values before asking humans to type.

**`FR-SHELL-000` P1** — Integration to the existing public runtime is limited to one routing change in `serve_site.py`: redirect `/staff/*` and `/auth/*` requests to the serverless staff host, preserving path and query string.

**`FR-SHELL-000A` P1** — Public pages never read or render staff session state; the login flow is entirely handled by the serverless staff host.

---

## 3. User Roles and Permissions

### 3.1 Role Definitions

| Role | Description |
|------|-------------|
| `operator` | Floor staff; executes workflows, logs readings, raises incidents |
| `warehouse` | Cask and goods movement; receiving; dispatch |
| `quality` | Lab, sampling, release decisions, non-conformance ownership |
| `production_lead` | Approves process deviations, batch dispositions, run strategies |
| `compliance` | Excise records, regulatory exports, audit support |
| `management` | Read-all dashboards, approve significant events, review trends |
| `admin` | User management, role grants, SOP publishing, system config |

### 3.2 Permission Matrix

| Action | operator | warehouse | quality | prod_lead | compliance | mgmt | admin |
|--------|----------|-----------|---------|-----------|------------|------|-------|
| View own records | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| View all records | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| Submit workflow step | ✓ | ✓ | ✓ | ✓ | — | — | — |
| Release material/batch | — | — | ✓ | ✓ | — | — | — |
| Approve disposition | — | — | — | ✓ | — | ✓ | ✓ |
| Raise non-conformance | ✓ | ✓ | ✓ | ✓ | — | — | — |
| Investigate/close NC | — | — | ✓ | ✓ | — | — | — |
| Raise incident | ✓ | ✓ | ✓ | ✓ | — | — | — |
| Investigate incident | — | — | — | ✓ | — | ✓ | ✓ |
| View excise ledger | — | — | — | — | ✓ | ✓ | ✓ |
| Export regulatory reports | — | — | — | — | ✓ | ✓ | ✓ |
| Run recall simulation | — | — | ✓ | ✓ | ✓ | ✓ | — |
| Publish SOP version | — | — | — | — | — | — | ✓ |
| Manage users | — | — | — | — | — | — | ✓ |
| View all dashboards | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |

### 3.3 Role Assignment Rules

`FR-ADMIN-001` **P1** — A user must be explicitly granted a role by an admin. No self-service role elevation.

`FR-ADMIN-002` **P1** — A user may hold multiple roles. Permissions are additive.

`FR-ADMIN-003` **P1** — Role grants and revocations are recorded in the immutable audit log.

`FR-ADMIN-004` **P2** — Users with no role after login see a "pending access" screen with a message to contact the administrator.

---

## 4. Authentication and Session Specification

### 4.1 Provider

**Google Identity Services (GIS)** — pure client-side sign-in using `accounts.google.com/gsi/client`. The browser handles the Google Sign-In popup and receives a signed **ID token (JWT)** directly. The server never participates in an OAuth redirect dance; it only verifies the token on one endpoint.

Key properties:
- No server-side OAuth callback route
- No client secret stored anywhere (server verifies using Google's public JWKS, not a shared secret)
- Only an **Authorised JavaScript Origin** (not a redirect URI) is registered in the Google Console
- Works on `http://localhost` without TLS — Google explicitly whitelists localhost for GIS
- Works identically in local dev and Cloud Run production with no environment-specific client configuration

**`FR-AUTH-001` P1** — The Sign In with Google button (rendered by the GIS `gsi/client` script) appears on the staff login page. On success, GIS calls a JavaScript callback with a credential (signed JWT). The browser immediately posts this credential to `POST /auth/verify` on the staff API.

**`FR-AUTH-002` P1** — The staff API `POST /auth/verify` endpoint verifies the JWT signature and `aud` claim against Google's public JWKS endpoint (cached with TTL). Only the `OIDC_CLIENT_ID` value is needed server-side — no client secret.

**`FR-AUTH-003` P1** — Only email addresses in an approved allowlist or matching an approved domain suffix (configured per deployment) are granted access. All other Google accounts receive an "Access not authorized" response with no staff data.

**`FR-AUTH-004` P1** — On successful verification, the backend issues a signed HTTP-only session cookie with `SameSite=Strict` and `Secure` flags. No credentials are stored in `localStorage` or `sessionStorage`. The ID token is discarded server-side after verification.

**`FR-AUTH-005` P1** — Session lifetime is 12 hours of inactivity. Any `/staff/` URL accessed after expiry returns HTTP 401; the staff SPA redirects to the login page with the intended URL preserved.

**`FR-AUTH-006` P1** — Sensitive actions (approvals, release decisions, recall initiation) require step-up re-authentication: GIS prompts the user to re-confirm, the resulting credential is posted to `POST /auth/verify?step_up=1`, and only then is the action committed.

**`FR-AUTH-007` P1** — Logout posts to `POST /auth/logout`, which clears the session cookie and deletes the server-side session record immediately.

**`FR-AUTH-008` P2** — All authentication events (login, logout, re-auth, failed auth) are appended to the immutable audit log with timestamp, user identity, and IP address.

### 4.2 Login Flow (GIS)

1. User navigates to `/staff/` (unauthenticated)
2. Staff SPA renders a login page with the GIS Sign In with Google button
3. User clicks — GIS shows the Google account picker popup (no page redirect)
4. On success, GIS calls the JS callback with a `credential` (signed JWT)
5. JS posts `{ credential }` to `POST /auth/verify`
6. Server verifies, checks allowlist, creates session, sets HTTP-only cookie
7. JS redirects to `/staff/dashboard` (or the originally requested URL)
8. Subsequent API calls send session cookie automatically

When the user **is authenticated:**

- Staff shell shows: `[First name] [▼]`
- Dropdown contains: Dashboard, My records, Sign out
- No staff session data ever appears in public page DOM

---

## 5. Global Navigation and Shell

### 5.1 Public Header Change

**`FR-SHELL-001` P1** — Public header shows a static `Staff Login` link targeting `/staff/` only; no dynamic auth state is rendered by public pages.

**`FR-SHELL-002` P1** — Authentication happens exclusively on the serverless staff host. If unauthenticated, `/staff/` redirects to Google login.

### 5.2 Staff App Shell

The `/staff/` path loads a lightweight single-page application shell containing:

- Top navigation bar with active-section highlight
- Left sidebar (collapsible on mobile) with module navigation
- Main content area rendered per route
- Notification tray (unread incident/NC counts)
- Current user display with role badge and sign-out

**`FR-SHELL-003` P1** — Staff navigation links:

1. Home
2. SOPs
3. Production (dropdown: Receiving, Mashing, Fermentation, Distillation, CIP)
4. Maturation (dropdown: Cask Management, Lab / Release)
5. Packaging (dropdown: Bottling, Label Compliance)
6. Quality (dropdown: Non-Conformance, Incidents)
7. Traceability (dropdown: Recall Simulation, Trace Lookup)
8. Inventory / Excise
9. Reports
10. Admin *(admin role only)*

**`FR-SHELL-004` P1** — All staff routes implement server-side authorization. A missing or expired session on any `/staff/api/` endpoint returns HTTP 401. An authenticated user without the required role returns HTTP 403. Neither response includes staff business data.

**`FR-SHELL-005` P2** — Notification tray shows badge counts for: open incidents awaiting investigation, overdue CAPAs, batches on hold pending disposition, and recalls in progress.

### 5.3 Minimum Data Entry Controls (Global)

**`FR-SHELL-006` P1** — All forms auto-fill `operator`, `site`, and current timestamp by default.

**`FR-SHELL-007` P1** — Every workflow supports a "scan-first" path (QR/barcode lot/cask lookup) before manual search.

**`FR-SHELL-008` P1** — Repeated values from the user's last completed run in the same module (equipment, location, recipe, shift) are prefilled and require one-tap confirmation.

**`FR-SHELL-009` P1** — Derived values (LPA, variances, tolerance checks, period totals) are computed server-side and never manually typed.

**`FR-SHELL-010` P2** — For time-series checks (fermentation, bottling QC), default cadence prompts create single-row quick-entry cards to reduce field count per check.

---

## 6. Staff Home Dashboard

### 6.1 Overview

The home page is a role-filtered card dashboard providing a real-time operational snapshot.

**`FR-HOME-001` P1** — Cards rendered per role:

| Card | Roles |
|------|-------|
| Active fermenters (count + any in-alert) | operator, production_lead, quality, management |
| Batches on hold (count + oldest age) | quality, production_lead, management |
| Open non-conformances (count + overdue) | quality, production_lead, management |
| Open incidents (count + unresolved) | all |
| Overdue CAPAs (count) | quality, production_lead, management |
| Recall readiness (last drill date + result) | compliance, management |
| Excise period status (current period, last lodged) | compliance, management |
| Quick actions (raise incident, start shift log) | operator, warehouse |

**`FR-HOME-002` P2** — Each card links to the relevant module filtered to the card's state.

**`FR-HOME-003` P2** — Trending KPI sparklines (7-day): fermentation on-time completions, NC open rate, CAPA closure rate.

---

## 7. SOP Hub

### 7.1 SOP List Page

`GET /staff/sops`

**`FR-SOP-001` P1** — Displays a table of all SOPs with columns: SOP ID, Title, Version, Effective Date, Owner, Status (Active/Superseded/Draft), Workflow Link.

**`FR-SOP-002` P1** — Each SOP title links to the read-only SOP viewer within the staff app (rendered from the SOP markdown files in `sops/`).

**`FR-SOP-003` P1** — Each row has a "Start Workflow" button that creates a new workflow execution record pre-filled with the SOP ID and current user.

**`FR-SOP-004` P1** — Staff SOP viewer renders the SOP markdown and appends a "Digital Workflow" panel (see §24 for additions to each SOP file).

**`FR-SOP-005` P2** — SOP version history is viewable from the hub. Past versions are read-only.

**`FR-SOP-006` P2** — Training acknowledgement status is shown per user. Users who have not acknowledged the current version of a SOP are flagged when they try to execute that SOP's workflow.

### 7.2 SOP Document Control (Admin)

**`FR-SOP-007` P2** — Admin can upload a new revision of an SOP (markdown source). System assigns next version number and sets status to Draft.

**`FR-SOP-008` P2** — Publishing a new version archives the previous version and notifies all users with workflows tied to that SOP to re-acknowledge.

**`FR-SOP-009` P2** — Revision history table: version, date published, author, change summary.

### 7.3 SOP Coverage Map

**`FR-SOP-010` P2** — Visual grid showing: SOP × workflow execution coverage for the past 30 days. Highlights SOPs with no recent workflow execution.

---

## 8. Raw Receiving and Quarantine Module

**Corresponds to:** SOP-01

### 8.1 Receiving Event Form

`POST /staff/api/receiving`

Minimum required fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `receipt_date` | datetime | auto-filled to now; editable |
| `supplier_id` | FK → suppliers | picklist from master |
| `material_type` | enum | grain, yeast, enzyme, cask, closure, label, chemical, other |
| `material_name` | string | picklist or free text |
| `lot_number` | string | supplier lot; scanned or typed |
| `quantity` | number | |
| `unit` | enum | kg, L, each, pallet |
| `purchase_order_ref` | string | optional |
| `received_by` | FK → users | auto-filled |
| `coa_attached` | boolean | flags whether supplier COA is filed |
| `vehicle_condition_ok` | boolean | |
| `initial_status` | enum | quarantine (default), released, rejected |
| `notes` | text | optional |

**`FR-REC-001` P1** — On save, the system creates a material lot record in inventory with status `quarantine` unless overridden.

**`FR-REC-002` P1** — On save, the receiving log entry is appended to the inventory ledger with movement type `received`.

**`FR-REC-003` P1** — A QR-code label is generated for printing containing the lot ID, material name, date, and status. Print target is the browser print dialog.

### 8.2 Quarantine Review and Release

`PATCH /staff/api/receiving/{id}/status`

**`FR-REC-004` P1** — Release decision requires: inspection outcome, any test results, and authorized reviewer (quality or production_lead role).

**`FR-REC-005` P1** — Rejection triggers a non-conformance record automatically pre-filled with material lot, supplier, and receiving event reference.

**`FR-REC-006` P1** — Conditional release (deviation-approved) requires a written restriction note and countersignature.

**`FR-REC-007` P1** — All status transitions are timestamped and attributed to the authorizing user in the audit log.

### 8.3 Receiving Ledger

`GET /staff/api/receiving?status=&material_type=&supplier=&from=&to=`

**`FR-REC-008` P1** — Filterable list. Columns: date, supplier, material, lot, qty, status, released by, NC reference (if any).

**`FR-REC-009` P2** — Export to CSV.

---

## 9. Mashing and Wort Production Module

**Corresponds to:** SOP-02

### 9.1 Mash Run Record

`POST /staff/api/mash-runs`

Minimum required fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `batch_id` | string | links to master batch; auto-generated prefix |
| `recipe_id` | FK → recipes | |
| `start_datetime` | datetime | auto-filled |
| `grain_lots` | array | lot IDs + weights from inventory |
| `target_mash_volume_L` | number | from recipe |
| `target_strike_temp_C` | number | from recipe |
| `actual_strike_temp_C` | number | operator entry |
| `mash_pH_readings` | array | [{time, pH, operator}] |
| `mash_temp_readings` | array | [{time, temp_C, rest_stage, operator}] |
| `conversion_check_passed` | boolean | iodine test or equivalent |
| `lauter_start_time` | datetime | |
| `lauter_end_time` | datetime | |
| `pre_ferment_gravity` | number | SG or °Plato |
| `pre_ferment_pH` | number | |
| `wort_volume_L` | number | collected |
| `fermenter_id` | FK → vessels | destination vessel |
| `released_by` | FK → users | quality/production_lead |
| `notes` | text | optional |

**`FR-MASH-001` P1** — Grain lots consumed are deducted from inventory on save. System validates that all grain lot IDs exist and have status `released`.

**`FR-MASH-002` P1** — If actual strike temperature deviates more than ±2 °C from target, a soft warning is shown. Operator must acknowledge before proceeding.

**`FR-MASH-003` P1** — Release to fermentation is a distinct step requiring production_lead or quality role.

**`FR-MASH-004` P2** — Mash run record auto-links to the batch genealogy chain.

---

## 10. Fermentation Module

**Corresponds to:** SOP-04

### 10.1 Fermentation Batch

`POST /staff/api/fermentation-batches`

Created automatically when a mash run is released to a fermenter, or manually for fermentation from external wort supply.

Key fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `batch_id` | string | inherits or links to mash batch |
| `vessel_id` | FK → vessels | |
| `yeast_lot_id` | FK → material_lots | |
| `pitch_datetime` | datetime | |
| `pitch_rate_g_per_L` | number | |
| `target_temp_C` | number | |
| `target_final_gravity` | number | |
| `status` | enum | active, on_hold, complete, transferred |

### 10.2 Monitoring Check Records

`POST /staff/api/fermentation-batches/{id}/checks`

| Field | Type | Notes |
|-------|------|-------|
| `check_datetime` | datetime | auto-filled |
| `gravity` | number | |
| `temp_C` | number | |
| `pH` | number | optional |
| `sensory_ok` | boolean | quick ok/flag |
| `sensory_note` | text | required if sensory_ok = false |
| `operator_id` | FK → users | auto-filled |

**`FR-FERM-001` P1** — If temperature is outside target ± tolerance, the check form shows an alert and requires the operator to select: "intervened" or "escalated."

**`FR-FERM-002` P1** — If gravity has not dropped at least the expected increment since last check (configurable threshold), a stall warning fires and the operator must log a response.

**`FR-FERM-003` P1** — Escalation puts the batch status to `on_hold` and sends a notification to production_lead.

**`FR-FERM-004` P1** — Gravity trend is rendered as a mini chart on the batch detail page (data: all check records for that batch).

**`FR-FERM-005` P1** — Transfer to distillation creates a movement record in the inventory ledger.

**`FR-FERM-006` P2** — Configurable monitoring schedule reminder: if no check exists for a vessel within the configured maximum interval, a notification fires to the assigned operator.

### 10.3 Yeast Pitch Record

`POST /staff/api/yeast-pitches`

**`FR-FERM-007` P1** — Pitch record captures: yeast lot, viability check result, pitch rate, wort volume, oxygenation method. Yeast lot is deducted/flagged in inventory.

---

## 11. Distillation Module

**Corresponds to:** SOP-05

### 11.1 Distillation Run Record

`POST /staff/api/distillation-runs`

Key fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `run_id` | string | auto-generated |
| `batch_id` | string | links to wash/fermentation batch |
| `still_id` | FK → equipment | |
| `run_type` | enum | stripping, spirit (full), single_pot |
| `start_datetime` | datetime | |
| `end_datetime` | datetime | |
| `wash_volume_L` | number | charge volume |
| `wash_ABV_pct` | number | |
| `foreshots_volume_L` | number | |
| `hearts_cut_start_time` | datetime | |
| `hearts_cut_start_ABV` | number | |
| `hearts_cut_end_time` | datetime | |
| `hearts_cut_end_ABV` | number | |
| `hearts_volume_L` | number | |
| `hearts_ABV_pct` | number | |
| `feints_volume_L` | number | |
| `feints_routed_to` | enum | re-run, downgrade, disposal |
| `operator_id` | FK → users | |
| `production_lead_verified` | boolean | |
| `notes` | text | |

**`FR-DIST-001` P1** — System auto-calculates LPA (litres of pure alcohol) for hearts fraction: `hearts_volume_L × hearts_ABV_pct / 100`. This value feeds the excise ledger.

**`FR-DIST-002` P1** — Entering a hearts ABV below 60% or above 94.8% triggers a hard validation warning requiring confirmation or non-conformance flag.

**`FR-DIST-003` P1** — End of run creates a new-make spirit lot in inventory with volume and ABV locked.

**`FR-DIST-004` P1** — Foreshots and feints routed to re-run are tracked as a separate lot (not yet released to the spirit account until redistilled).

**`FR-DIST-005` P2** — Run log allows adding time-series ABV readings (time, ABV, temperature) for trend visualization and cut-point audit.

**`FR-DIST-006` P2** — Deviation report pre-filled if hearts fraction ABV or volume deviates from target band.

---

## 12. CIP and Sanitation Module

**Corresponds to:** SOP-07

### 12.1 CIP Log

`POST /staff/api/cip-logs`

Key fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `equipment_id` | FK → equipment | |
| `purpose` | enum | pre_production, post_production, deep_clean, allergen_changeover |
| `start_datetime` | datetime | |
| `end_datetime` | datetime | |
| `detergent_type` | string | picklist |
| `detergent_conc_pct` | number | |
| `detergent_temp_C` | number | |
| `rinse_cycles` | integer | |
| `sanitizer_type` | string | picklist |
| `sanitizer_conc_pct` | number | |
| `verification_method` | enum | visual, atp_swab, ph_endpoint, rinse_conductivity, microbiological |
| `verification_passed` | boolean | |
| `released_by` | FK → users | |
| `notes` | text | |

**`FR-CIP-001` P1** — Equipment cannot be allocated to a new production run unless its most recent CIP log has `verification_passed = true` and `released_by` is populated.

**`FR-CIP-002` P1** — If `verification_passed = false`, a non-conformance record is raised automatically and the equipment remains locked.

**`FR-CIP-003` P2** — CIP chemical usage is tracked to a chemical lot (received under SOP-01) to maintain hazardous materials audit trail.

---

## 13. Cask Management Module

**Corresponds to:** SOP-06

### 13.1 Cask Registry

Each cask is a master record in the system with a permanent cask ID.

Key cask record fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `cask_id` | string | primary key; scannable QR/barcode |
| `cask_type` | enum | hogshead, barrel, butt, puncheon, quarter, other |
| `volume_L_nominal` | number | nominal capacity |
| `previous_contents` | string | e.g., bourbon, sherry, port, virgin oak |
| `previous_fill_count` | integer | 0 = first-fill |
| `supplier_id` | FK → suppliers | cooperage or vendor |
| `received_date` | date | |
| `current_status` | enum | empty_available, filled, emptied, rejected, retired |
| `current_location_id` | FK → locations | warehouse + stack/bay/position |
| `notes` | text | |

### 13.2 Cask Fill Record

`POST /staff/api/cask-fills`

Key fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `cask_id` | FK → casks | scanned |
| `spirit_lot_id` | FK → inventory_lots | new-make or re-fill source |
| `fill_date` | date | |
| `fill_ABV_pct` | number | |
| `fill_volume_L` | number | actual fill |
| `fill_LPA` | computed | auto: volume × ABV/100 |
| `batch_id` | string | production batch reference |
| `location_id` | FK → locations | |
| `operator_id` | FK → users | |

**`FR-CASK-001` P1** — Fill immediately moves the cask status to `filled` and records a spirit movement in the inventory ledger (type: `cask_fill`).

**`FR-CASK-002` P1** — A QR label with cask ID, fill date, spirit type, batch ID, and ABV is generated for warehouse printing.

**`FR-CASK-003` P1** — Location tracking: every cask movement between warehouse locations is recorded with date, operator, and new location.

**`FR-CASK-004` P1** — Ullage/leak inspection records: date, inspector, condition (ok / leak / damage), estimated loss volume if applicable.

**`FR-CASK-005` P1** — A confirmed leak record triggers an incident record (pre-filled with cask ID, location, estimated loss).

**`FR-CASK-006` P2** — Cask detail page shows: fill record, location history, all inspection events, estimated angel's share per year, expected maturation end date.

**`FR-CASK-007` P2** — Warehouse map view: grid of locations with filled/empty/status heat map.

### 13.3 Cask Emptying / Vatting

`POST /staff/api/cask-empties`

Records the withdrawal of matured spirit from a cask into a vatting or receiving vessel for bottling or blend preparation.

Key fields (P1): cask ID, emptied date, withdrawal volume, withdrawal ABV, receiving vessel ID, operator.

**`FR-CASK-008` P1** — Emptying updates cask status to `emptied` and moves spirit into a new mature-spirit lot in inventory.

**`FR-CASK-009` P1** — Excise ledger is updated with the LPA withdrawn.

---

## 14. Sampling and Lab Release Module

**Corresponds to:** SOP-08

### 14.1 Sample Record

`POST /staff/api/samples`

Key fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `sample_id` | string | auto-generated |
| `batch_or_lot_id` | string | FK to the source: mash, fermentation, distillation, cask, or bottling |
| `sample_point` | enum | raw_material, wort, wash, new_make, maturation, pre_bottling, packaged |
| `sample_datetime` | datetime | |
| `container_id` | string | lab reference label |
| `sampled_by` | FK → users | |
| `tests_requested` | array | enum choices: ABV, gravity, pH, micro, sensory, DO, haze, acetaldehyde, methanol, SO2 |
| `external_lab` | boolean | |
| `external_lab_name` | string | if external |
| `status` | enum | collected, in_lab, completed, on_hold |

### 14.2 Lab Results

`POST /staff/api/samples/{id}/results`

Key fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `results` | json | map of test_code → {value, unit, spec_min, spec_max, pass} |
| `overall_pass` | boolean | computed or manually overridden |
| `tested_by` | FK → users | lab tech or quality |
| `tested_datetime` | datetime | |
| `release_decision` | enum | released, hold, non_conformance |
| `released_by` | FK → users | quality/prod_lead |

**`FR-LAB-001` P1** — If any individual test result is outside specification limits, `overall_pass` is forced to false and `release_decision` must be `hold` or `non_conformance`.

**`FR-LAB-002` P1** — A `non_conformance` release decision auto-creates a non-conformance record linked to the sample.

**`FR-LAB-003` P2** — Sample chain-of-custody: automated timestamp at each handoff (collected, received in lab, tested, released).

**`FR-LAB-004` P2** — Trend charts for key parameters (ABV, pH, gravity, micro counts) per vessel/batch over time.

---

## 15. Bottling and Packaging Module

**Corresponds to:** SOP-09

### 15.1 Bottling Run Record

`POST /staff/api/bottling-runs`

Minimum required fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `run_id` | string | auto-generated |
| `sku_id` | FK → products | product definition |
| `lot_code` | string | batch/lot code for labels and traceability |
| `planned_quantity` | integer | bottles |
| `spirit_lot_ids` | array | source mature-spirit lots with volumes |
| `target_ABV_pct` | number | |
| `target_fill_volume_mL` | number | |
| `start_datetime` | datetime | |
| `line_clearance_by` | FK → users | quality/lead |
| `first_off_approved_by` | FK → users | quality |
| `status` | enum | setup, running, paused, complete, hold |

### 15.2 Label Compliance Checklist

`POST /staff/api/bottling-runs/{id}/label-check`

Required fields (P1) — all boolean:

| Field | Label declaration |
|-------|------------------|
| `product_name_correct` | Product name and legal category match approved label |
| `abv_correct` | Declared ABV matches pre-bottling test result ±0.1% |
| `volume_correct` | Declared volume matches fill setting |
| `country_of_origin_present` | Country of origin present |
| `lot_code_present` | Lot/batch code legible and correct |
| `barcode_scannable` | GS1 barcode scans and matches the SKU |
| `allergen_declaration_ok` | Allergen text meets jurisdiction requirement |
| `health_warnings_ok` | Health warning text present and correct for market |
| `market_specific_ok` | Market-specific text verified (e.g., export destination) |
| `label_artwork_version` | Approved artwork version confirmed |

**`FR-BOTT-001` P1** — All label checklist fields must be `true` before a bottling run can progress to `running` status.

**`FR-BOTT-002` P1** — Any `false` field blocks run start with a clear message identifying the specific failure.

**`FR-BOTT-003` P1** — Label checklist signoff requires quality role.

### 15.3 In-Line QC Records

`POST /staff/api/bottling-runs/{id}/qc-checks`

| Field | Type | Notes |
|-------|------|-------|
| `check_time` | datetime | auto-filled |
| `bottles_inspected` | integer | |
| `fill_volume_ok` | boolean | |
| `fill_volume_deviation_mL` | number | required if not ok |
| `closure_torque_ok` | boolean | |
| `label_placement_ok` | boolean | |
| `barcode_readable` | boolean | |
| `lot_code_readable` | boolean | |
| `defects_found` | text | optional |
| `operator_id` | FK → users | auto-filled |

**`FR-BOTT-004` P1** — If any in-line check is `false`, the run is not automatically stopped but a hold notification fires to quality and the packaging lead.

### 15.4 End-of-Run Reconciliation

`POST /staff/api/bottling-runs/{id}/reconciliation`

| Field | Type |
|-------|------|
| `spirit_used_L` | number |
| `spirit_declared_L` | number |
| `bottles_filled` | integer |
| `bottles_planned` | integer |
| `bottles_rejected` | integer |
| `labels_issued` | integer |
| `labels_used` | integer |
| `labels_returned` | integer |
| `labels_spoiled` | integer |
| `closures_issued` | integer |
| `closures_used` | integer |
| `cartons_used` | integer |
| `variance_spirit_L` | computed |
| `variance_pct` | computed |
| `variance_within_tolerance` | boolean — auto if ≤0.5% |
| `variance_explanation` | text — required if outside tolerance |

**`FR-BOTT-005` P1** — Spirit consumed is moved from the spirit inventory lot to `dispatched` in the ledger.

**`FR-BOTT-006` P1** — The LPA bottled and lot code are posted to the excise ledger.

**`FR-BOTT-007` P1** — If `variance_pct > tolerance_threshold`, status is locked until `variance_explanation` is populated and approved by production_lead.

**`FR-BOTT-008` P2** — Reconciliation report is exportable as PDF for record retention.

---

## 16. Non-Conformance and CAPA Module

**Corresponds to:** SOP-10

### 16.1 Non-Conformance Record

`POST /staff/api/non-conformances`

Key fields (P1):

| Field | Type | Notes |
|-------|------|-------|
| `nc_id` | string | auto-generated NC-YYYY-NNN |
| `title` | string | short description |
| `discovery_datetime` | datetime | auto-filled |
| `discovered_by` | FK → users | auto-filled |
| `nc_type` | enum | product, process, supplier, labeling, regulatory, safety, other |
| `affected_lots` | array | material or spirit lot references |
| `affected_quantity` | number + unit | |
| `description` | text | required |
| `immediate_action_taken` | text | containment steps |
| `severity` | enum | critical, major, minor |
| `status` | enum | open, investigating, dispositioned, capa_open, capa_closed, closed |
| `owner_id` | FK → users | quality role assigned |

**`FR-NC-001` P1** — Affected lots are placed on hold in inventory automatically when NC is created.

**`FR-NC-002` P1** — Critical and major NCs send a real-time notification to production_lead and management.

### 16.2 Investigation Record

`POST /staff/api/non-conformances/{id}/investigation`

| Field | Type |
|-------|------|
| `root_cause_method` | enum: 5_whys, fishbone, fault_tree, narrative |
| `root_cause_summary` | text |
| `evidence_refs` | text (URLs or attachment references) |
| `risk_to_product` | enum: none, low, medium, high |
| `risk_to_consumer` | enum: none, low, medium, high |
| `risk_justification` | text |

### 16.3 Disposition Record

`POST /staff/api/non-conformances/{id}/disposition`

| Field | Type | Notes |
|-------|------|-------|
| `disposition` | enum | release_with_concession, rework, regrade, return_to_supplier, destroy |
| `disposition_rationale` | text | |
| `approved_by` | FK → users | production_lead or quality |
| `approved_datetime` | datetime | |

**`FR-NC-003` P1** — Disposition to `release_with_concession` requires additional management sign-off via step-up re-auth.

**`FR-NC-004` P1** — Destruction records the quantity destroyed and removes from inventory.

### 16.4 CAPA Record

`POST /staff/api/non-conformances/{id}/capa`

| Field | Type |
|-------|------|
| `corrective_actions` | array: [{description, owner_id, due_date}] |
| `preventive_actions` | array: [{description, owner_id, due_date}] |
| `effectiveness_check_date` | date |
| `effectiveness_check_by` | FK → users |
| `effectiveness_outcome` | enum: effective, partially_effective, not_effective |
| `effectiveness_notes` | text |

**`FR-NC-005` P1** — Any CAPA action past its due date triggers a notification to the action owner plus management.

**`FR-NC-006` P1** — NC cannot transition to `closed` until effectiveness check is recorded.

**`FR-NC-007` P2** — CAPA trend dashboard: top 5 root causes by frequency (rolling 90 days), average time to close by NC type.

---

## 17. Incident and Near-Miss Module

**Corresponds to:** SOP-11

### 17.1 Reporting Screen

Target: incident capture in under 60 seconds.

Quick capture form at `GET /staff/incidents/new`:

| Field | Type | Notes |
|-------|------|-------|
| `reported_by` | FK → users | auto-filled |
| `incident_datetime` | datetime | auto-filled |
| `location` | string | free text or picklist |
| `type` | enum | safety, environmental, quality, property, security, near_miss |
| `description` | text | required; voice-to-text supported |
| `immediate_action` | text | optional at capture |
| `people_injured` | boolean | |
| `emergency_called` | boolean | |

**`FR-INC-001` P1** — Injury or emergency_called = true sends an immediate push notification to management and compliance.

**`FR-INC-002` P1** — Near-miss records are given distinct visual treatment to encourage reporting without stigma.

**`FR-INC-003` P1** — Serious incidents (injury, reportable environmental release) change the header notification badge to red.

### 17.2 Investigation Record

`POST /staff/api/incidents/{id}/investigation`

| Field | Type |
|-------|------|
| `contributing_factors` | multiselect enum: equipment, process_gap, training, supervision, environment, human_error |
| `root_cause` | text |
| `timeline_narrative` | text |
| `witness_contacts` | text |
| `corrective_actions` | array same as CAPA format |

**`FR-INC-004` P2** — Incident trend report: frequency by type and location, near-miss vs. actual ratio, repeat-location incidents.

---

## 18. Recall and Traceability Module

**Corresponds to:** SOP-12

### 18.1 Trace Lookup

`GET /staff/api/trace?lot={lot_id}&direction={forward|backward|both}`

**`FR-RCLL-001` P1** — Given a lot ID (finished goods, spirit, material), the API returns the complete genealogy graph:

- **Backward**: lot → bottling run → spirit lots → cask fills → distillation run → fermentation batch → mash run → raw material lots → supplier
- **Forward**: raw material lot → all batches that consumed it → all finished lots that contain it → all dispatch records

**`FR-RCLL-002` P1** — The trace result is rendered as an interactive tree/graph in the browser and as a flat table exportable to CSV and PDF.

**`FR-RCLL-003` P1** — Trace covers: quantities at each step, date ranges, key operators, batch/lot IDs, and current status of each derived lot.

### 18.2 Recall Simulation Drill

`POST /staff/api/recall-drills`

| Field | Type |
|-------|------|
| `drill_name` | string |
| `trigger_lot` | string | test lot to simulate recall from |
| `direction` | enum | forward, backward, both |
| `initiated_by` | FK → users |
| `initiated_datetime` | datetime |

Drill execution:

1. System runs the trace query.
2. Records the total affected quantity found.
3. Records quantities in each status: warehouse, dispatched (with customer info), in-production, recovered.
4. Timestamps each step.

**`FR-RCLL-004` P1** — Drill is timed from initiation to full trace completion.

**`FR-RCLL-005` P1** — Drill produces a report including: elapsed time, lots identified, quantities accounted for, percentage of dispatched product with customer contact records on file.

**`FR-RCLL-006` P2** — Drill can be marked as closed with a gap analysis and action items.

**`FR-RCLL-007` P2** — Recall readiness score is computed: time to trace threshold × % customer records on file × % batch records complete. Score shown on staff home dashboard.

### 18.3 Live Recall Event

`POST /staff/api/recalls`

For a real recall (not a drill), the same trace logic runs but also:

- places all forward-affected finished lots on hold immediately
- creates a recall event record with mandatory regulatory notification status field
- generates a notification pack (PDF) with lot IDs, quantities, customer distribution list

**`FR-RCLL-008` P1** — Only compliance or management roles can initiate a live recall event.

---

## 19. Inventory and Excise Ledger

### 19.1 Ledger Overview

The inventory ledger is an append-only ledger of all spirit and material movements. It is the system of record for the spirit stock account.

**`FR-INV-001` P1** — Every quantity movement in the system (receiving, mash consumption, fermentation transfer, distillation output, cask fill, cask empty, bottling consumption, dispatch, loss, adjustment) posts a ledger entry automatically as part of the workflow transaction.

**`FR-INV-002` P1** — Ledger entries cannot be deleted. Corrections are recorded as reversal + replacement entries with a reason and authorizing user.

### 19.2 Ledger Entry Schema

| Field | Description |
|-------|-------------|
| `entry_id` | Immutable UUID |
| `entry_datetime` | Server timestamp |
| `movement_type` | enum: received, quarantine_released, quarantine_rejected, mash_consumed, wort_produced, wash_produced, spirit_produced, cask_filled, cask_transferred, cask_emptied, bottled, dispatched, loss_evaporation, loss_leak, loss_breakage, adjustment, reversal |
| `lot_id` | The inventory lot affected |
| `quantity` | signed number (positive = in, negative = out) |
| `unit` | kg, L |
| `LPA` | computed for spirit movements |
| `source_doc_type` | e.g., `receiving`, `cask_fill`, `bottling_run` |
| `source_doc_id` | FK to originating record |
| `operator_id` | auto-filled |
| `notes` | optional |

### 19.3 Excise Reporting Period

**`FR-INV-003` P1** — The system maintains excise periods (monthly or quarterly, configured per deployment). Each period has a status: open, lodged, amended.

**`FR-INV-004` P1** — For each open period, the system computes:
- total LPA produced
- total LPA removed from bond (dispatched)
- total LPA still in bond (cask + tank)
- total LPA losses (angel's share + incidents)
- remission-eligible LPA (for eligible small producers, e.g., ATO craft producer remissions)

**`FR-INV-005` P1** — Period summary is exportable as a structured report suitable for lodgement support (see §20).

**`FR-INV-006` P2** — Automated cross-check: total LPA produced = sum of LPA in all downstream lots plus recorded losses. Discrepancy triggers an alert.

### 19.4 Lot Registry

**`FR-INV-007` P1** — Every material and spirit lot is registered with: lot ID, material/product name, type (raw material / intermediate / new-make / mature-spirit / packaged), quantity, unit, current status, and current location.

**`FR-INV-008` P1** — Stock on hand view: filter by type, status, location. Total LPA per spirit type in bond.

---

## 20. Reports and Regulatory Exports

### 20.1 Available Reports

| Report | Roles | Format | Frequency | P |
|--------|-------|--------|-----------|---|
| Spirit stock account (full period) | compliance, mgmt | PDF, CSV | per period | P1 |
| Inventory movement ledger | compliance, mgmt | CSV | on demand | P1 |
| Batch genealogy / traceability report | quality, compliance | PDF | on demand | P1 |
| Bottling reconciliation report | quality, mgmt | PDF | per run | P1 |
| Non-conformance register | quality, mgmt | PDF, CSV | on demand | P1 |
| CAPA status tracker | quality, mgmt | PDF | on demand | P2 |
| Incident and near-miss register | mgmt, compliance | PDF, CSV | on demand | P1 |
| Recall drill history | compliance, mgmt | PDF | on demand | P1 |
| Excise period summary | compliance | structured CSV/PDF | per period | P1 |
| Label compliance checklist archive | quality, compliance | PDF | per bottling run | P1 |
| SOP acknowledgement register | admin, mgmt | PDF | on demand | P2 |
| Management KPI pack (weekly auto) | mgmt | PDF email attachment | weekly | P3 |

**`FR-RPT-001` P1** — All reports are generated server-side. No sensitive data is exposed in client-side export logic.

**`FR-RPT-002` P1** — Reports include: generation datetime, system version, period covered, and total record count.

**`FR-RPT-003` P2** — Reports are retained in a report archive (not regenerated each time) once a period is lodged, to ensure regulatory records are immutable after lodgement.

### 20.2 Australian Compliance Reporting Pack

The P1 Australian reporting pack must be complete enough for operational lodgement preparation and audit support.

**`FR-RPT-010` P1** — Excise stock account pack includes opening balance, production, maturation transfers, packaging removals, losses, and closing balance in both volume and LPA.

**`FR-RPT-011` P1** — Excise period report includes a reconciliation section mapping each subtotal to ledger movement types and source document counts.

**`FR-RPT-012` P1** — Duty/remission working report includes computed dutiable LPA, remission-eligible LPA, assumed rate table version, and period estimate outputs for compliance review.

**`FR-RPT-013` P1** — Product traceability report satisfies one-step-back/one-step-forward recall evidence with supplier lots, internal batches, finished lots, and dispatch recipients.

**`FR-RPT-014` P1** — Label compliance archive includes immutable pre-start checklist result, signer identity, and timestamp per bottling lot.

**`FR-RPT-015` P1** — Every regulatory export embeds a dataset hash and generation timestamp to support audit integrity verification.

**`FR-RPT-016` P2** — GST/sales integration endpoint (or CSV import) links dispatch lots to invoice references for cross-check reporting, without requiring operators to enter invoice data in production workflows.

---

## 21. Admin Module

### 21.1 User Management

`GET /staff/admin/users`, `POST /staff/admin/users/{id}/roles`

**`FR-ADMIN-010` P1** — Admin can view all registered users, their roles, last login, and active status.

**`FR-ADMIN-011` P1** — Admin can add or remove roles. All changes logged.

**`FR-ADMIN-012` P1** — Admin can deactivate an account (blocks login without deletion; preserves audit history).

### 21.2 System Configuration

**`FR-ADMIN-020` P1** — Allowed Google domains / email allowlist. Stored server-side only.

**`FR-ADMIN-021` P1** — Excise period type (monthly/quarterly) and current period dates.

**`FR-ADMIN-022` P1** — Tolerance thresholds: fermentation temp tolerance, bottling reconciliation variance, gravity stall threshold.

**`FR-ADMIN-023` P2** — Equipment registry (vessels, stills, tanks, lines) with type, capacity, and active/retired status.

**`FR-ADMIN-024` P2** — Location registry (warehouses, bays, stacks) for cask and inventory location tracking.

**`FR-ADMIN-025` P2** — Product / SKU registry (name, ABV, volume, barcode, market approvals).

**`FR-ADMIN-026` P2** — Supplier registry (name, country, approved materials, contact).

**`FR-ADMIN-027` P2** — Recipe registry (name, grain bill, process targets) linked to mash runs.

---

## 22. Data Model Specification

### 22.1 Core Tables

#### users
```
id             UUID PK
google_sub     STRING UNIQUE NOT NULL
email          STRING UNIQUE NOT NULL
display_name   STRING
created_at     TIMESTAMPTZ
last_login_at  TIMESTAMPTZ
is_active      BOOLEAN DEFAULT TRUE
```

#### user_roles
```
id         UUID PK
user_id    FK → users
role       ENUM(operator, warehouse, quality, production_lead, compliance, management, admin)
granted_by FK → users
granted_at TIMESTAMPTZ
revoked_at TIMESTAMPTZ NULL
```

#### sessions
```
id           UUID PK (session token)
user_id      FK → users
created_at   TIMESTAMPTZ
expires_at   TIMESTAMPTZ
last_seen_at TIMESTAMPTZ
ip_address   STRING
user_agent   STRING
invalidated  BOOLEAN DEFAULT FALSE
```

#### audit_log
```
id            UUID PK
event_type    STRING
actor_id      FK → users NULL (null for system events)
target_type   STRING
target_id     UUID NULL
payload       JSONB
ip_address    STRING
created_at    TIMESTAMPTZ NOT NULL
```
Append-only, no UPDATE or DELETE permitted.

#### suppliers
```
id            UUID PK
name          STRING
country       STRING
contact_email STRING
contact_phone STRING
notes         TEXT
is_active     BOOLEAN
```

#### equipment
```
id          UUID PK
name        STRING
type        ENUM(mash_tun, fermenter, still, receiver_tank, cip_unit, bottling_line, other)
capacity_L  NUMERIC NULL
is_active   BOOLEAN
notes       TEXT
```

#### locations
```
id        UUID PK
label     STRING (e.g., "WH-A Bay 3 Stack 2")
type      ENUM(warehouse, cellar, production, dispatch, lab)
is_active BOOLEAN
```

#### material_lots
```
id               UUID PK
lot_code         STRING UNIQUE
material_type    ENUM(grain, yeast, enzyme, cask_empty, closure, label, chemical, other)
material_name    STRING
supplier_id      FK → suppliers NULL
supplier_lot     STRING
quantity         NUMERIC
unit             ENUM(kg, L, each, pallet)
received_date    DATE
expiry_date      DATE NULL
current_status   ENUM(quarantine, released, conditional_release, rejected, consumed, depleted)
location_id      FK → locations NULL
notes            TEXT
```

#### receiving_events
```
id                  UUID PK
receipt_datetime    TIMESTAMPTZ
supplier_id         FK → suppliers
lot_id              FK → material_lots
purchase_order_ref  STRING NULL
vehicle_ok          BOOLEAN
coa_attached        BOOLEAN
received_by_id      FK → users
status              ENUM(quarantine, released, conditional_release, rejected)
reviewed_by_id      FK → users NULL
reviewed_at         TIMESTAMPTZ NULL
review_notes        TEXT NULL
nc_id               FK → non_conformances NULL
```

#### batches
```
id               UUID PK
batch_code       STRING UNIQUE NOT NULL (e.g., "BATCH-2026-042")
batch_type       ENUM(mash, fermentation, distillation, vatting, bottling)
parent_batch_id  FK → batches NULL
created_at       TIMESTAMPTZ
status           ENUM(active, complete, hold, abandoned)
notes            TEXT
```

#### mash_runs
```
id                       UUID PK
batch_id                 FK → batches
recipe_id                FK → recipes NULL
start_datetime           TIMESTAMPTZ
end_datetime             TIMESTAMPTZ NULL
fermenter_id             FK → equipment NULL
pre_ferment_gravity      NUMERIC NULL
pre_ferment_pH           NUMERIC NULL
wort_volume_L            NUMERIC NULL
wort_lot_id              FK → inventory_lots NULL
released_by_id           FK → users NULL
released_at              TIMESTAMPTZ NULL
status                   ENUM(in_progress, released, hold, abandoned)
notes                    TEXT
```

#### mash_run_grain_lots
```
mash_run_id    FK → mash_runs
lot_id         FK → material_lots
weight_kg      NUMERIC
```

#### mash_readings  (time-series)
```
id           UUID PK
mash_run_id  FK → mash_runs
reading_type ENUM(temperature, pH, gravity)
rest_stage   STRING NULL
reading_time TIMESTAMPTZ
value        NUMERIC
operator_id  FK → users
```

#### fermentation_batches
```
id                    UUID PK
batch_id              FK → batches
vessel_id             FK → equipment
yeast_lot_id          FK → material_lots NULL
pitch_datetime        TIMESTAMPTZ NULL
pitch_rate_g_per_L    NUMERIC NULL
target_temp_C         NUMERIC NULL
target_final_gravity  NUMERIC NULL
status                ENUM(active, on_hold, complete, transferred, abandoned)
transferred_to_run_id FK → distillation_runs NULL
notes                 TEXT
```

#### fermentation_checks  (time-series)
```
id              UUID PK
batch_id        FK → fermentation_batches
check_datetime  TIMESTAMPTZ
gravity         NUMERIC
temp_C          NUMERIC
pH              NUMERIC NULL
sensory_ok      BOOLEAN
sensory_note    TEXT NULL
in_tolerance    BOOLEAN
intervention    ENUM(none, temperature_corrected, escalated) DEFAULT none
operator_id     FK → users
```

#### distillation_runs
```
id                        UUID PK
batch_id                  FK → batches
fermentation_batch_id     FK → fermentation_batches NULL
still_id                  FK → equipment
run_type                  ENUM(stripping, spirit, single_pot)
start_datetime            TIMESTAMPTZ
end_datetime              TIMESTAMPTZ NULL
wash_volume_L             NUMERIC
wash_ABV_pct              NUMERIC
foreshots_volume_L        NUMERIC NULL
hearts_cut_start_time     TIMESTAMPTZ NULL
hearts_cut_start_ABV_pct  NUMERIC NULL
hearts_cut_end_time       TIMESTAMPTZ NULL  
hearts_cut_end_ABV_pct    NUMERIC NULL
hearts_volume_L           NUMERIC NULL
hearts_ABV_pct            NUMERIC NULL
hearts_LPA                NUMERIC computed
feints_volume_L           NUMERIC NULL
feints_routed_to          ENUM(re_run, downgrade, disposal) NULL
spirit_lot_id             FK → inventory_lots NULL
operator_id               FK → users
production_lead_verified  BOOLEAN DEFAULT FALSE
status                    ENUM(in_progress, complete, on_hold, abandoned)
notes                     TEXT
```

#### cip_logs
```
id                    UUID PK
equipment_id          FK → equipment
purpose               ENUM(pre_production, post_production, deep_clean, allergen_changeover)
start_datetime        TIMESTAMPTZ
end_datetime          TIMESTAMPTZ NULL
detergent_type        STRING
detergent_conc_pct    NUMERIC
detergent_temp_C      NUMERIC
rinse_cycles          INTEGER
sanitizer_type        STRING NULL
sanitizer_conc_pct    NUMERIC NULL
verification_method   ENUM(visual, atp_swab, ph_endpoint, rinse_conductivity, microbiological)
verification_passed   BOOLEAN
released_by_id        FK → users NULL
released_at           TIMESTAMPTZ NULL
nc_id                 FK → non_conformances NULL
notes                 TEXT
```

#### casks
```
id                   UUID PK
cask_code            STRING UNIQUE
cask_type            ENUM(hogshead, barrel, butt, puncheon, quarter, octave, other)
volume_L_nominal     NUMERIC
previous_contents    STRING
previous_fill_count  INTEGER DEFAULT 0
supplier_id          FK → suppliers NULL
received_date        DATE NULL
current_status       ENUM(empty_available, filled, emptied, rejected, retired)
current_location_id  FK → locations NULL
notes                TEXT
```

#### cask_events
```
id              UUID PK
cask_id         FK → casks
event_type      ENUM(received, filled, moved, inspected, emptied, rejected, retired)
event_datetime  TIMESTAMPTZ
operator_id     FK → users
location_id     FK → locations NULL
notes           TEXT
```

#### cask_fills
```
id             UUID PK
cask_id        FK → casks
batch_id       FK → batches
spirit_lot_id  FK → inventory_lots
fill_date      DATE
fill_ABV_pct   NUMERIC
fill_volume_L  NUMERIC
fill_LPA       NUMERIC computed
location_id    FK → locations
operator_id    FK → users
```

#### cask_empties
```
id                    UUID PK
cask_id               FK → casks
cask_fill_id          FK → cask_fills
emptied_date          DATE
withdrawal_volume_L   NUMERIC
withdrawal_ABV_pct    NUMERIC
withdrawal_LPA        NUMERIC computed
receiving_lot_id      FK → inventory_lots
operator_id           FK → users
notes                 TEXT
```

#### cask_inspections
```
id              UUID PK
cask_id         FK → casks
inspection_date DATE
inspector_id    FK → users
condition       ENUM(ok, minor_seep, active_leak, structural_damage)
estimated_loss_L NUMERIC NULL
incident_id     FK → incidents NULL
notes           TEXT
```

#### inventory_lots
```
id              UUID PK
lot_code        STRING UNIQUE
lot_type        ENUM(raw_material, wort, wash, new_make, mature_spirit, packaged, waste_feints, waste_off_cuts)
material_name   STRING
quantity        NUMERIC
unit            ENUM(kg, L, bottles)
ABV_pct         NUMERIC NULL
LPA             NUMERIC NULL
status          ENUM(in_bond, dispatched, consumed, on_hold, destroyed, adjusted)
location_id     FK → locations NULL
created_at      TIMESTAMPTZ
notes           TEXT
```

#### inventory_ledger
```
id               UUID PK
entry_datetime   TIMESTAMPTZ NOT NULL
movement_type    ENUM (see §19.2)
lot_id           FK → inventory_lots
quantity         NUMERIC
unit             ENUM(kg, L, bottles)
LPA              NUMERIC NULL
source_doc_type  STRING
source_doc_id    UUID
operator_id      FK → users
notes            TEXT
```
Append-only: no UPDATE, no DELETE. Corrections via reversal entries only.

#### samples
```
id              UUID PK
sample_code     STRING UNIQUE
batch_or_lot_id STRING
sample_point    ENUM(raw_material, wort, wash, new_make, maturation, pre_bottling, packaged)
sample_datetime TIMESTAMPTZ
container_id    STRING
sampled_by_id   FK → users
tests_requested JSONB
external_lab    BOOLEAN
external_lab_name STRING NULL
status          ENUM(collected, in_lab, completed, on_hold)
release_decision ENUM(released, hold, non_conformance) NULL
released_by_id  FK → users NULL
released_at     TIMESTAMPTZ NULL
nc_id           FK → non_conformances NULL
```

#### lab_results
```
id          UUID PK
sample_id   FK → samples
results     JSONB  -- {test_code: {value, unit, spec_min, spec_max, pass}}
overall_pass BOOLEAN
tested_by_id FK → users
tested_at   TIMESTAMPTZ
notes       TEXT
```

#### bottling_runs
```
id                  UUID PK
run_code            STRING UNIQUE
sku_id              FK → products NULL
lot_code            STRING
planned_quantity    INTEGER
spirit_lots         JSONB  -- [{lot_id, volume_L}]
target_ABV_pct      NUMERIC
target_fill_mL      NUMERIC
start_datetime      TIMESTAMPTZ
end_datetime        TIMESTAMPTZ NULL
line_clearance_by_id FK → users NULL
first_off_approved_by_id FK → users NULL
status              ENUM(setup, label_check, running, paused, complete, hold)
```

#### bottling_label_checks
```
id                       UUID PK
run_id                   FK → bottling_runs
product_name_correct     BOOLEAN
abv_correct              BOOLEAN
volume_correct           BOOLEAN
country_of_origin_present BOOLEAN
lot_code_present         BOOLEAN
barcode_scannable        BOOLEAN
allergen_declaration_ok  BOOLEAN
health_warnings_ok       BOOLEAN
market_specific_ok       BOOLEAN
label_artwork_version    STRING NULL
checked_by_id            FK → users
checked_at               TIMESTAMPTZ
all_passed               BOOLEAN computed
```

#### bottling_qc_checks  (time-series)
```
id                     UUID PK
run_id                 FK → bottling_runs
check_time             TIMESTAMPTZ
bottles_inspected      INTEGER
fill_volume_ok         BOOLEAN
fill_deviation_mL      NUMERIC NULL
closure_torque_ok      BOOLEAN
label_placement_ok     BOOLEAN
barcode_readable       BOOLEAN
lot_code_readable      BOOLEAN
defects_found          TEXT NULL
operator_id            FK → users
```

#### bottling_reconciliations
```
id                       UUID PK
run_id                   FK → bottling_runs UNIQUE
spirit_used_L            NUMERIC
spirit_declared_L        NUMERIC
bottles_filled           INTEGER
bottles_planned          INTEGER
bottles_rejected         INTEGER
labels_issued            INTEGER
labels_used              INTEGER
labels_returned          INTEGER
labels_spoiled           INTEGER
closures_issued          INTEGER
closures_used            INTEGER
cartons_used             INTEGER
variance_spirit_L        NUMERIC computed
variance_pct             NUMERIC computed
variance_within_tolerance BOOLEAN
variance_explanation     TEXT NULL
approved_by_id           FK → users NULL
approved_at              TIMESTAMPTZ NULL
```

#### non_conformances
```
id                    UUID PK
nc_code               STRING UNIQUE  -- NC-YYYY-NNN
title                 STRING
discovery_datetime    TIMESTAMPTZ
discovered_by_id      FK → users
nc_type               ENUM(product, process, supplier, labeling, regulatory, safety, other)
affected_lots         JSONB
affected_quantity     NUMERIC NULL
affected_unit         STRING NULL
description           TEXT
immediate_action      TEXT NULL
severity              ENUM(critical, major, minor)
status                ENUM(open, investigating, dispositioned, capa_open, capa_closed, closed)
owner_id              FK → users NULL
root_cause_method     ENUM NULL
root_cause_summary    TEXT NULL
risk_to_product       ENUM(none, low, medium, high) NULL
risk_to_consumer      ENUM(none, low, medium, high) NULL
disposition           ENUM(release_with_concession, rework, regrade, return_to_supplier, destroy) NULL
disposition_rationale TEXT NULL
disposition_approved_by FK → users NULL
disposition_approved_at TIMESTAMPTZ NULL
closed_at             TIMESTAMPTZ NULL
```

#### capa_actions
```
id              UUID PK
nc_id           FK → non_conformances
action_type     ENUM(corrective, preventive)
description     TEXT
owner_id        FK → users
due_date        DATE
completed_at    TIMESTAMPTZ NULL
effectiveness_check_date DATE NULL
effectiveness_by_id FK → users NULL
effectiveness_outcome ENUM(effective, partially_effective, not_effective) NULL
effectiveness_notes TEXT NULL
```

#### incidents
```
id                  UUID PK
incident_code       STRING UNIQUE
reported_by_id      FK → users
incident_datetime   TIMESTAMPTZ
location            STRING
incident_type       ENUM(safety, environmental, quality, property, security, near_miss)
description         TEXT
immediate_action    TEXT NULL
people_injured      BOOLEAN
emergency_called    BOOLEAN
status              ENUM(reported, investigating, actions_open, closed)
contributing_factors JSONB NULL
root_cause          TEXT NULL
closed_at           TIMESTAMPTZ NULL
```

#### incident_actions
```
id            UUID PK
incident_id   FK → incidents
description   TEXT
owner_id      FK → users
due_date      DATE
completed_at  TIMESTAMPTZ NULL
```

#### recall_drills
```
id                  UUID PK
drill_name          STRING
trigger_lot         STRING
direction           ENUM(forward, backward, both)
initiated_by_id     FK → users
initiated_at        TIMESTAMPTZ
completed_at        TIMESTAMPTZ NULL
elapsed_seconds     INTEGER NULL
is_live             BOOLEAN DEFAULT FALSE
lots_identified     INTEGER NULL
total_qty_affected  NUMERIC NULL
qty_in_bond         NUMERIC NULL
qty_dispatched      NUMERIC NULL
qty_recovered       NUMERIC NULL
customer_contact_pct NUMERIC NULL
gap_analysis        TEXT NULL
status              ENUM(in_progress, complete, closed)
```

#### sop_documents
```
id              UUID PK
sop_code        STRING  -- e.g., SOP-01
title           STRING
current_version STRING
effective_date  DATE
owner_role      STRING
markdown_path   STRING  -- relative path to .md source
status          ENUM(active, superseded, draft)
```

#### sop_versions
```
id              UUID PK
sop_id          FK → sop_documents
version         STRING
published_at    TIMESTAMPTZ NULL
published_by_id FK → users NULL
change_summary  TEXT NULL
markdown_path   STRING
status          ENUM(draft, active, superseded)
```

#### sop_acknowledgements
```
id            UUID PK
user_id       FK → users
sop_version_id FK → sop_versions
acknowledged_at TIMESTAMPTZ
```

#### excise_periods
```
id              UUID PK
period_type     ENUM(monthly, quarterly)
period_start    DATE
period_end      DATE
status          ENUM(open, lodged, amended)
lodged_at       TIMESTAMPTZ NULL
lodged_by_id    FK → users NULL
LPA_produced    NUMERIC NULL
LPA_removed     NUMERIC NULL
LPA_in_bond     NUMERIC NULL
LPA_losses      NUMERIC NULL
LPA_remission_eligible NUMERIC NULL
notes           TEXT NULL
```

---

## 23. API Surface Specification

All staff API endpoints are under `/staff/api/v1/`. All require valid session cookie. All return JSON.

### Conventions

- `GET /resource` — list with query filters
- `GET /resource/{id}` — single record
- `POST /resource` — create
- `PATCH /resource/{id}` — partial update
- `POST /resource/{id}/action` — state transition or sub-record creation

All responses: `{"data": ..., "meta": {total, page, per_page, generated_at}}`  
Errors: `{"error": {code, message, field_errors: {field: [messages]}}}`

### Endpoint Summary

```
POST   /auth/verify          ← receives GIS credential JWT from browser JS
POST   /auth/logout

GET    /staff/api/v1/users
GET    /staff/api/v1/users/{id}
PATCH  /staff/api/v1/users/{id}/roles

GET    /staff/api/v1/sops
GET    /staff/api/v1/sops/{id}
POST   /staff/api/v1/sops/{id}/acknowledge

GET    /staff/api/v1/receiving
POST   /staff/api/v1/receiving
GET    /staff/api/v1/receiving/{id}
PATCH  /staff/api/v1/receiving/{id}/status

GET    /staff/api/v1/mash-runs
POST   /staff/api/v1/mash-runs
GET    /staff/api/v1/mash-runs/{id}
POST   /staff/api/v1/mash-runs/{id}/readings
POST   /staff/api/v1/mash-runs/{id}/release

GET    /staff/api/v1/fermentation-batches
POST   /staff/api/v1/fermentation-batches
GET    /staff/api/v1/fermentation-batches/{id}
POST   /staff/api/v1/fermentation-batches/{id}/checks
POST   /staff/api/v1/fermentation-batches/{id}/release
POST   /staff/api/v1/fermentation-batches/{id}/hold

GET    /staff/api/v1/distillation-runs
POST   /staff/api/v1/distillation-runs
GET    /staff/api/v1/distillation-runs/{id}
POST   /staff/api/v1/distillation-runs/{id}/readings
POST   /staff/api/v1/distillation-runs/{id}/complete

GET    /staff/api/v1/cip-logs
POST   /staff/api/v1/cip-logs
GET    /staff/api/v1/cip-logs/{id}

GET    /staff/api/v1/casks
POST   /staff/api/v1/casks
GET    /staff/api/v1/casks/{id}
POST   /staff/api/v1/casks/{id}/fill
POST   /staff/api/v1/casks/{id}/move
POST   /staff/api/v1/casks/{id}/inspect
POST   /staff/api/v1/casks/{id}/empty

GET    /staff/api/v1/samples
POST   /staff/api/v1/samples
GET    /staff/api/v1/samples/{id}
POST   /staff/api/v1/samples/{id}/results
POST   /staff/api/v1/samples/{id}/release

GET    /staff/api/v1/bottling-runs
POST   /staff/api/v1/bottling-runs
GET    /staff/api/v1/bottling-runs/{id}
POST   /staff/api/v1/bottling-runs/{id}/label-check
POST   /staff/api/v1/bottling-runs/{id}/qc-checks
POST   /staff/api/v1/bottling-runs/{id}/reconciliation
POST   /staff/api/v1/bottling-runs/{id}/complete

GET    /staff/api/v1/non-conformances
POST   /staff/api/v1/non-conformances
GET    /staff/api/v1/non-conformances/{id}
POST   /staff/api/v1/non-conformances/{id}/investigation
POST   /staff/api/v1/non-conformances/{id}/disposition
POST   /staff/api/v1/non-conformances/{id}/capa
PATCH  /staff/api/v1/non-conformances/{id}/capa/{action_id}

GET    /staff/api/v1/incidents
POST   /staff/api/v1/incidents
GET    /staff/api/v1/incidents/{id}
POST   /staff/api/v1/incidents/{id}/investigation
PATCH  /staff/api/v1/incidents/{id}/actions/{action_id}

GET    /staff/api/v1/trace
POST   /staff/api/v1/recall-drills
GET    /staff/api/v1/recall-drills/{id}
POST   /staff/api/v1/recall-drills/{id}/close
POST   /staff/api/v1/recalls

GET    /staff/api/v1/inventory
GET    /staff/api/v1/inventory/lots
GET    /staff/api/v1/inventory/ledger
GET    /staff/api/v1/excise/periods
GET    /staff/api/v1/excise/periods/{id}/summary
POST   /staff/api/v1/excise/periods/{id}/lodge

GET    /staff/api/v1/reports
POST   /staff/api/v1/reports/generate
GET    /staff/api/v1/reports/{id}/download

GET    /staff/api/v1/admin/config
PATCH  /staff/api/v1/admin/config
GET    /staff/api/v1/admin/audit-log
```

---

## 24. SOP Document Update Specification

Each SOP markdown file in `sops/` receives a new section appended before the final review frequency line. The section is titled `## Digital Workflow` and contains:

- A link to start the corresponding digital workflow (accessible only after login)
- The system records that the workflow auto-creates
- The escalation path

### SOP-01: Raw Receiving and Quarantine Release

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/raw-receiving](/staff/workflows/raw-receiving)  
*(Requires staff login)*

**Records created automatically:**
- Receiving event log (supplier, lot, quantity, date, receiver)
- Material lot in inventory with quarantine status
- Printable QR identification label
- Release or rejection record with authoriser and timestamp
- Non-conformance record (if rejected)
- Inventory ledger entry (movement type: received)

**Escalation path:**  
Rejected material or failed release check → Non-Conformance module → Quality owner → Production Lead disposition decision
```

### SOP-02: Milling, Mashing, and Lautering

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/mashing-lautering](/staff/workflows/mashing-lautering)  
*(Requires staff login)*

**Records created automatically:**
- Mash run record (batch ID, recipe, grain lots consumed, time-series temperature/pH readings)
- Grain lot deduction from inventory
- Wort lot creation on release
- Inventory ledger entry (movement type: mash_consumed / wort_produced)

**Escalation path:**  
Pre-ferment gravity or pH out of specification → Soft warning with mandatory operator acknowledgement → Production Lead review if outside hard limit
```

### SOP-03: Yeast Handling and Pitch Protocol

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/yeast-pitch](/staff/workflows/yeast-pitch)  
*(Requires staff login)*

**Records created automatically:**
- Yeast pitch record (yeast lot, viability check, pitch rate, wort volume)
- Fermentation batch created and linked to mash batch
- Yeast lot consumption posted to inventory

**Escalation path:**  
Viability check result below threshold or contamination indicator → Hold status on yeast lot → Quality decision before pitch approved
```

### SOP-04: Fermentation Monitoring and Intervention

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/fermentation-monitoring](/staff/workflows/fermentation-monitoring)  
*(Requires staff login)*

**Records created automatically:**
- Time-series monitoring check records (gravity, temperature, pH, sensory)
- Automated stall and temperature alerts
- Intervention and escalation log records
- Batch disposition record on transfer or hold

**Escalation path:**  
Temperature or gravity trigger → Operator intervention logged → If not resolved within one check cycle → Production Lead notified → Batch placed on hold
```

### SOP-05: Distillation Cuts and Spirit Handling

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/distillation-cuts](/staff/workflows/distillation-cuts)  
*(Requires staff login)*

**Records created automatically:**
- Distillation run record (still, run type, fraction volumes and ABVs, cut times)
- New-make spirit lot in inventory with LPA auto-calculated
- Feints lot with disposition routing
- Excise ledger entry (movement type: spirit_produced)
- Production Lead verification signoff record

**Escalation path:**  
Hearts ABV or volume outside target band → Soft warning with confirmation required → If outside hard limit → Automatic non-conformance record
```

### SOP-06: Cask Receiving, Filling, Movement, and Leak Response

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/cask-management](/staff/workflows/cask-management)  
*(Requires staff login)*

**Records created automatically:**
- Cask registry entry on receipt (cask ID, type, previous contents, supplier)
- Cask fill record (batch linkage, fill date, ABV, volume, LPA, location)
- Printable QR cask label
- Movement records for every relocation
- Inspection records at each check interval
- Incident record (auto-created on confirmed leak with estimated loss)
- Excise ledger entry (movement type: cask_filled / cask_emptied)

**Escalation path:**  
Confirmed leak → Incident record raised → Quality and Production Lead notified → Product disposition decision on affected spirit
```

### SOP-07: CIP and Sanitation Verification

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/cip-sanitation](/staff/workflows/cip-sanitation)  
*(Requires staff login)*

**Records created automatically:**
- CIP log (equipment, cycle parameters, verification result, release status)
- Equipment clean-release status (blocks allocation to production until passed)
- Non-conformance record (auto-created if verification fails)

**Escalation path:**  
Verification failure → Equipment locked → Non-Conformance raised → Quality resolution before re-release
```

### SOP-08: Sampling and Lab Release

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/lab-release](/staff/workflows/lab-release)  
*(Requires staff login)*

**Records created automatically:**
- Sample record with chain-of-custody timestamps
- Lab results log for each test performed against specification
- Batch release or hold record
- Non-conformance record (auto-created on out-of-spec result)

**Escalation path:**  
Out-of-spec result → Batch on hold → Non-Conformance module → Quality-led investigation → Production Lead disposition
```

### SOP-09: Bottling Setup, In-Line Checks, and Reconciliation

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/bottling-reconciliation](/staff/workflows/bottling-reconciliation)  
*(Requires staff login)*

**Records created automatically:**
- Bottling run record with label compliance checklist (all fields must pass before run starts)
- Time-series in-line QC check records
- End-of-run reconciliation (spirit, bottles, labels, closures, cartons with variance calculation)
- Inventory ledger entries (movement type: bottled / dispatched)
- Excise ledger entry (LPA removed from bond)

**Escalation path:**  
Label compliance check failure → Run blocked until corrected and re-checked by quality  
Reconciliation variance outside tolerance → Run locked → Production Lead approval with documented explanation
```

### SOP-10: Non-Conformance Management

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/non-conformance](/staff/workflows/non-conformance)  
*(Requires staff login)*

**Records created automatically:**
- Non-conformance record (NC code, type, severity, affected lots placed on hold)
- Investigation record with root cause method and risk assessment
- Disposition record with required approvals
- CAPA actions with owners and due dates
- Overdue CAPA notifications
- Effectiveness check record before closure

**Escalation path:**  
Critical/major NC → Immediate notification to Production Lead and Management  
Release with concession disposition → Additional management step-up re-authentication required  
CAPA overdue → Notification to action owner and Management
```

### SOP-11: Incident and Near-Miss Reporting

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/incidents-near-miss](/staff/workflows/incidents-near-miss)  
*(Requires staff login)*

**Records created automatically:**
- Incident record (type, description, immediate action, injury/emergency flags)
- Real-time notification on injury or emergency_called = true
- Investigation record with contributing factors and corrective actions
- Action records with owners and due dates

**Escalation path:**  
Injury or emergency → Immediate push notification to Management and Compliance  
Serious incident classification → Written report required same shift; supervisor secures area  
Overdue corrective action → Notification to owner and Management
```

### SOP-12: Recall and Traceability Exercises

```markdown
## Digital Workflow

**Start workflow:** [/staff/workflows/recall-traceability](/staff/workflows/recall-traceability)  
*(Requires staff login)*

**Records created automatically:**
- Recall drill record (trigger lot, direction, timing, completeness metrics)
- Traceability graph (backward to suppliers and forward to customers)
- Drill report (elapsed time, lots identified, quantities accounted, customer contact coverage)
- Gap analysis and corrective action records
- Recall readiness score updated on staff home dashboard

For live recalls:
- Immediate hold placed on all forward-identified finished lots
- Regulatory notification status field
- Notification pack (PDF) with lot IDs, quantities, customer distribution list

**Escalation path:**  
Drill identifies trace gap → Gap analysis record → Quality action plan  
Live recall initiated → Compliance and Management role step-up authentication required → Regulatory authority notification within required window
```

---

## 25. Non-Functional Requirements

**`NFR-001` P1** — All staff API endpoints must respond within 500 ms for list queries with up to 1,000 records.

**`NFR-002` P1** — The trace query for a lot with up to 500 children must complete within 3 seconds.

**`NFR-003` P1** — The incident capture form must be fully usable on a mobile browser in under 60 seconds from tap to submission.

**`NFR-004` P1** — The system must function for at least 10 simultaneous operator sessions without degradation.

**`NFR-005` P1** — Database backups must run daily with point-in-time recovery capability for a minimum 90-day retention window (compliance data: 7 years).

**`NFR-006` P1** — All staff data at rest is encrypted (AES-256 or equivalent). TLS 1.2+ required for all transport.

**`NFR-007` P2** — Offline-first capability for core operator forms (fermentation checks, cask inspections, incident capture) using a service worker queue; sync on reconnect.

**`NFR-008` P2** — The system must be accessible (WCAG 2.1 AA) for all staff-facing screens.

**`NFR-009` P3** — Peak-read dashboard response under 1 second for pre-aggregated KPI data.

---

## 26. Security Requirements

**`NFR-SEC-001` P1** — Server-side authorization on every request. No client-side role skip possible.

**`NFR-SEC-002` P1** — All form inputs validated server-side. Client-side validation is for UX convenience only.

**`NFR-SEC-003` P1** — SQL queries use parameterized statements only (no string concatenation).

**`NFR-SEC-004` P1** — Session tokens are cryptographically random (128-bit minimum), stored in the database, and invalidated immediately on logout.

**`NFR-SEC-005` P1** — CSRF protection on all state-changing endpoints (double-submit cookie or SameSite=Strict cookie).

**`NFR-SEC-006` P1** — Rate limiting on authentication endpoints (max 10 attempts per IP per 15 minutes).

**`NFR-SEC-007` P1** — The audit log table has no DELETE or UPDATE permissions granted to the application user. Only INSERT is permitted.

**`NFR-SEC-008` P1** — File upload endpoints (COA attachments) validate MIME type and size server-side. Files are stored outside the web root.

**`NFR-SEC-009` P2** — Penetration test executed before go-live covering OWASP Top 10. Critical findings must be resolved before launch.

**`NFR-SEC-010` P2** — Dependency scanning (pip audit or equivalent) run in CI with automatic PR blocking on high-severity CVEs.

---

## 27. Error Handling and Edge Cases

### 27.1 Inventory Consistency

- If a batch or run creation fails mid-way (e.g., after inventory deduction but before record commit), the transaction must be atomic and roll back completely.
- All inventory movements are part of the same database transaction as their parent record.

### 27.2 Duplicate Records

- Mash run: the same batch_id cannot be assigned to two concurrent mash runs with `in_progress` status.
- Cask fill: a cask with status `filled` cannot be filled again without an explicit emptying record.
- Bottling run: a lot_code must be unique across all confirmed bottling runs.

### 27.3 Partial Form Saves

- For long workflows (distillation runs, bottling runs), the form auto-saves a draft every 2 minutes and on tab loss.
- Draft records are clearly labelled and excluded from inventory and excise calculations until explicitly submitted.

### 27.4 Network Loss

- Offline queue (service worker, P2) stores pending submissions locally and replays on reconnect.
- Optimistic UI must reconcile with server state on reconnect and surface conflicts to the user.

### 27.5 Date/Time Consistency

- All datetimes stored in UTC.
- All user-facing datetimes rendered in the site's configured local timezone.
- Timezone is a deployment configuration value.

### 27.6 Bulk Import (P2)

- Initial cask registry and supplier registry can be loaded from CSV upload (admin only).
- CSV upload validates all rows before committing any; returns row-level errors for failed rows.

---

## 28. Acceptance Criteria by Module

### Authentication
**`AC-AUTH-001`** Given a Google account on the allowed domain, when the user completes GIS sign-in, the browser JS receives a credential, posts it to `/auth/verify`, and the staff SPA navigates to `/staff/dashboard` with an active session.  
**`AC-AUTH-002`** Given an unapproved Google account, when `/auth/verify` is called, the API returns HTTP 403 and the SPA shows an "Access not authorized" message with no staff data.  
**`AC-AUTH-003`** Given an expired session, when the user loads any `/staff/` URL, the SPA redirects to the login page and returns to the original URL after successful sign-in.

### SOP Hub
**`AC-SOP-001`** All 12 SOPs appear in the hub with correct version and effective date.  
**`AC-SOP-002`** Clicking "Start Workflow" on any SOP opens the correct workflow form pre-filled with the SOP reference.

### Raw Receiving
**`AC-REC-001`** Submitting a receiving form creates a material lot in quarantine status and a ledger entry.  
**`AC-REC-002`** Releasing a lot requires quality or production_lead role; lower roles are denied with HTTP 403.  
**`AC-REC-003`** Rejecting a lot auto-creates a non-conformance record.

### Fermentation
**`AC-FERM-001`** A monitoring check with temperature outside tolerance shows a warning and requires the operator to respond before save.  
**`AC-FERM-002`** A gravity reading that shows no decline over two check intervals triggers a stall alert and production_lead notification.

### Distillation
**`AC-DIST-001`** Hearts LPA is auto-calculated and matches volume × ABV/100 to 3 decimal places.  
**`AC-DIST-002`** Completing a distillation run creates a new-make spirit lot in inventory and an excise ledger entry.

### Bottling
**`AC-BOTT-001`** A bottling run cannot progress to `running` status if any label compliance checklist field is false.  
**`AC-BOTT-002`** A reconciliation variance greater than the configured tolerance blocks run completion until a Production Lead provides a written explanation.

### Non-Conformance
**`AC-NC-001`** Creating a non-conformance places all referenced lots on hold in inventory.  
**`AC-NC-002`** A non-conformance cannot be closed until an effectiveness check record exists.

### Recall
**`AC-RCLL-001`** A backward trace from a finished-goods lot ID returns all source lots back to raw material supplier.  
**`AC-RCLL-002`** A forward trace from a raw material lot returns all finished lots and all dispatch records.  
**`AC-RCLL-003`** A recall drill produces a timed report with quantities at each status.

### Inventory / Excise
**`AC-INV-001`** Total LPA in bond equals sum of all spirit lots with status `in_bond`.  
**`AC-INV-002`** The excise period summary shows correct LPA produced, removed, and in bond, consistent with the ledger.  
**`AC-INV-003`** Ledger entries cannot be edited or deleted; corrections create reversal + replacement entries.

### Minimum Entry and AU Reporting
**`AC-RPT-010`** An operator can complete a fermentation check in under 20 seconds with no more than 4 required manual fields.  
**`AC-RPT-011`** A receiving event can be completed with scan-first flow and no typed fields except supplier lot when scan is unavailable.  
**`AC-RPT-012`** Australian excise pack exports opening, movement, and closing balances with LPA reconciled to the immutable ledger and no manual spreadsheet arithmetic.

---

## 29. Technology Stack Recommendation

| Layer | Recommendation | Notes |
|-------|---------------|-------|
| Auth | Google Identity Services (GIS) — client-side JWT, server verifies via `google-auth-library` | No redirect URIs, no client secret, works on localhost without TLS |
| Backend API | Python / FastAPI | Consistent with existing Python project; async-ready |
| Database | PostgreSQL 15+ | ACID compliance for excise records; JSONB for flexible readings |
| ORM | SQLAlchemy 2.0 | Compatible with existing whisky_local/ module style |
| Session store | Database table (sessions) | No Redis dependency for small deployments; upgrade path exists |
| Frontend staff shell | Vanilla JS + HTML templates | Consistent with existing site approach; no build pipeline overhead |
| PDF generation | WeasyPrint | Python-native; no external service |
| QR code generation | python-qrcode | Browser print target |
| Reverse proxy | Optional (local only) | Not required in production split-host model |
| Deployment | GitHub Pages + Google Cloud Run + Cloud SQL Postgres | Keeps public site static and isolates secure staff runtime |

---

## 30. Integration With Existing Codebase

### 30.1 serve_site.py Changes Required

1. Add one early-path redirect handler: if request path starts with `/staff/` or `/auth/`, return HTTP 302 to `${STAFF_APP_ORIGIN}{path}{query}`.
2. No other auth/session changes in public renderer.

### 30.2 build_github_pages.py Changes Required

1. Add `/staff/` to the exclusion list; do not statically export any staff route.
2. Public SOP pages (rendered from `sops/*.md`) continue to be exported with the new Digital Workflow section appended, but the workflow link targets a runtime staff URL and gracefully shows a login prompt when accessed without auth.

### 30.3 whisky_local/ Module Additions

New modules to add alongside existing `database.py`, `enrichment.py`, etc.:

- `whisky_local/staff_auth.py` — token verification, session management, allowlist check
- `whisky_local/staff_db.py` — staff schema, migrations
- `whisky_local/staff_api.py` — FastAPI app factory
- `whisky_local/staff_reports.py` — PDF and CSV generation

### 30.4 New Entry Points

- `scripts/serve_staff.py` — launches the FastAPI staff backend
- `scripts/migrate_staff_db.py` — runs schema migrations
- `scripts/start_staff.sh` — combined launcher (staff backend + existing public site)

### 30.6 Split Hosting Topology (Production)

- Public static site: GitHub Pages (`build/github-pages/` output)
- Staff frontend + API + auth callback: Google Cloud Run service
- Database: Cloud SQL for PostgreSQL
- Secrets: Google Secret Manager (DB credentials only — no OAuth client secret needed with GIS)
- Artifact/CI: GitHub Actions builds both targets, deploys independently

---

## 31. Deployment Script and Runbook

The plan includes a deployment script for split hosting.

### 31.1 Script Location

- `scripts/deploy_split_hosting.sh`

### 31.2 Script Responsibilities

1. Build public static site via `scripts/build_github_pages.py`
2. Publish static artifacts to GitHub Pages branch (`gh-pages`)
3. Build staff service container image
4. Push image to Google Artifact Registry
5. Deploy/update Cloud Run service
6. Run database migrations on Cloud SQL
7. Emit deployment summary with public URL and staff URL

### 31.3 Required Environment Variables

- `GCP_PROJECT`
- `GCP_REGION`
- `ARTIFACT_REPO`
- `CLOUD_RUN_SERVICE`
- `CLOUD_SQL_INSTANCE`
- `STAFF_APP_ORIGIN`
- `GITHUB_PAGES_BRANCH` (default `gh-pages`)

### 31.4 Deployment Acceptance Criteria

**`AC-DEPLOY-001`** Running `scripts/deploy_split_hosting.sh` from a clean main branch completes without manual steps except cloud authentication.  
**`AC-DEPLOY-002`** Public Pages deployment and staff Cloud Run deployment are independently releasable.  
**`AC-DEPLOY-003`** A request to `/staff/` from the public origin is redirected to the configured staff host and login flow functions end-to-end.

### 30.5 SOP Files Updated

All 12 SOP markdown files in `sops/` receive the new `## Digital Workflow` section as specified in §24. The section is appended in the same markdown style as the existing content and does not break the current public SOP rendering.

---

*Document ends. Next steps: Phase 0 discovery — confirm legal field requirements per jurisdiction, approve role matrix, confirm auth stack, produce field-level mapping sheet before implementation tickets.*
