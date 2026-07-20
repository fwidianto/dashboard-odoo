# MVP Specification — Odoo Protocol Control Tower

Status: Phase 0 Draft v2 — validation-first

## 1. Current Objective

Before building the active UI, validate that the current Odoo Protocol, actual operating process, Odoo source data, and existing dashboards describe the same flow.

The first implementation remains a read-only application page that shows the end-to-end process as clickable stages and reuses existing traceability views/APIs. Implementation begins only after the selected process mappings pass sample-record validation.

The product must answer:

1. How many records are currently at each data-valid stage?
2. Which records are waiting, in progress, partial, blocked, completed, exception, manual, or mapping pending?
3. Who owns the next action and approval?
4. Which SOP rule applies?
5. What upstream/downstream documents are related?
6. Is the displayed status proven by Odoo, derived, hybrid, or manual?

## 2. Validated Process Architecture

```text
Customer PO / Confirmed Quotation
→ Sales Order & Approval
→ Distribusi JO / Operational Handover
→ Fulfilment Decision
→ Internal Order / Manufacturing Planning when applicable
→ RKB / ROP when applicable
→ RFQ / Purchase Order when applicable
→ Receipt when applicable
→ Material Transfer / Pre-Production
→ Production / Finish Good
→ Delivery
→ Invoice
→ Payment / Collection
```

Approval is not one generic stage. It appears inside the relevant stage:

- SO approval at Sales Order;
- ROP approval at RKB / ROP;
- PO review/Confirm at RFQ / PO;
- Lock/Unlock as an overlay on the affected document.

## 3. Page Structure

### A. Header

- selected company;
- data refresh timestamp;
- SOP version;
- Rule Registry version;
- validation status/version;
- total open Critical/High exceptions;
- filters: date, owner, customer/project, source type, status, confidence, coverage mode.

### B. End-to-End Process Map

Every stage shows:

- active count only when data-valid;
- waiting count;
- partial count;
- exception count;
- oldest age;
- highest severity;
- process owner;
- data-readiness;
- data confidence;
- coverage mode: Odoo, Hybrid, Manual, or Mapping Pending.

Manual or unmapped stages must not show misleading zero values.

### C. Stage Worklist

Clicking a stage opens:

```text
Document Number / Manual Milestone Reference
Root SO / IO
Customer / Project
Native Odoo Status
Canonical Status
Operational Status when available
Status Reason
Age
Owner / Approver
Related Documents
Open Exceptions
Highest Severity
SOP / Rule
Coverage Mode
Data Confidence
Last Activity
Source Updated At
```

### D. Record Journey Drawer/Page

Clicking one record opens:

- business start evidence: Customer PO / confirmed quotation where available;
- root identity and source classification;
- process journey;
- current and completed stages;
- waiting/blocked/manual/mapping-pending stages;
- related SO, IO, MO, ROP, PO, Receipt, Delivery, Invoice, and payment evidence;
- approval status within each relevant document;
- ERP status versus operational/manual status;
- anomaly history when available;
- related SOP sections and Rule IDs;
- data confidence, coverage mode, and source timestamp.

## 4. Validation Scope Before UI Build

### Validation Pack A — Customer Order and Handover

1. Customer PO / Confirmed Quotation;
2. Sales Order creation and approval/Confirm;
3. Distribusi JO timing, recipients, and evidence;
4. Fulfilment Decision.

### Validation Pack B — Fulfilment Branches

1. Trading from Stock;
2. Sales Order from Internal Order;
3. Make-to-Order / JO;
4. Mixed Source.

### Validation Pack C — Procurement and Manufacturing

1. MO planning;
2. RKB / ROP approval;
3. RFQ / PO review and approval;
4. Receipt and inspection;
5. Material Transfer / WIP;
6. Production / Finish Good, including manual production evidence.

### Validation Pack D — Commercial Completion

1. Delivery;
2. Invoice / DP / Final Invoice;
3. payment record;
4. invoice residual and receivable reconciliation.

## 5. MVP Data Scope After Validation

### Fully Live First

1. Sales Order;
2. Fulfilment Decision;
3. Internal Order / Manufacturing summary;
4. Delivery;
5. Invoice progress.

### Partially Live / Hybrid

1. Customer PO / Confirmed Quotation;
2. Distribusi JO;
3. RKB / ROP;
4. RFQ / Purchase Order;
5. Receipt;
6. Material Transfer / WIP;
7. Production / Finish Good.

### Validation Pending

1. Payment / Collection source of truth;
2. complete approval event history;
3. complete external evidence linkage.

Formal ticketing and AI SOP proposal are not part of the current validation/MVP scope.

## 6. Proposed API Contracts

### `GET /api/control-tower/process-map`

Returns aggregate stage health with readiness and coverage:

```json
{
  "sop_version": "draft-v4",
  "rule_version": "v1",
  "validation_version": "phase0-v2",
  "source_updated_at": "timestamp",
  "nodes": [
    {
      "node_id": "CT-01",
      "name": "Sales Order & Approval",
      "readiness": "READY",
      "coverage_mode": "ODOO",
      "confidence": "HIGH",
      "counts_are_valid": true,
      "counts": {
        "WAITING": 0,
        "IN_PROGRESS": 0,
        "PARTIAL": 0,
        "COMPLETED": 0,
        "EXCEPTION": 0
      },
      "oldest_age_days": 0,
      "highest_severity": null
    }
  ]
}
```

For Manual or Mapping Pending stages, `counts_are_valid` is `false` and the API must return a reason rather than a fabricated zero.

### `GET /api/control-tower/nodes/{node_id}/records`

Filters:

- canonical status;
- operational status;
- owner / approver;
- severity;
- date range;
- customer/project;
- source type;
- confidence;
- coverage mode;
- page and page size.

### `GET /api/control-tower/journey/{root_type}/{root_id}`

Returns the complete journey for one SO or IO, including manual and pending milestones.

### `GET /api/control-tower/rules/{rule_id}`

Returns business-facing rule metadata, SOP reference, evidence requirement, and validation status.

## 7. Proposed Data Views

```text
vw_ct_process_instances
vw_ct_stage_status
vw_ct_stage_summary
vw_ct_document_links
vw_ct_exception_worklist
vw_ct_order_journey
vw_ct_validation_evidence
```

### `vw_ct_process_instances`

One row per root SO/IO.

### `vw_ct_stage_status`

One row per root and stage with native status, canonical status, operational status, coverage mode, and confidence.

### `vw_ct_stage_summary`

Aggregate counts used by the process map. Counts are only published for validated mappings.

### `vw_ct_document_links`

Normalized upstream/downstream document graph.

### `vw_ct_exception_worklist`

Rule output linked to owner and SOP. Formal ticket storage is deferred.

### `vw_ct_order_journey`

UI-ready root-level journey summary.

### `vw_ct_validation_evidence`

Stores or references sample-record validation results, expected outcome, actual outcome, reviewer, and evidence location.

## 8. UI Behavior

- Stage click filters without navigating away where practical.
- Exception count opens the worklist prefiltered to `EXCEPTION`.
- Manual/Mapping Pending stages explain what evidence or mapping is missing.
- Status reason is readable, not only code.
- ERP Status and Operational Status are visually distinct.
- Raw technical diagnostics stay behind an expandable section.
- Existing Sales Order/Internal Order pages remain available as deep links.
- No write action to Odoo.
- No automatic ticket closure or SOP update.

## 9. Acceptance Criteria

The first release is acceptable when:

1. one SO can be traced from available customer-order evidence to all related documents;
2. stage definitions have process-owner approval;
3. each live stage count reconciles to its worklist and sample Odoo records;
4. Distribusi JO is shown as a manual/future-Odoo milestone without false automated conclusions;
5. approval is shown in the correct document context;
6. Production displays Odoo and manual coverage honestly;
7. each exception shows Rule ID, owner, severity, suggested action, SOP reference, confidence, and evidence requirement;
8. source timestamp and data confidence are visible;
9. cancelled records are excluded from active counts but remain searchable;
10. Mixed Source is represented line-first and header-rollup;
11. missing stages show `Manual`, `Data Mapping Pending`, or `Validation Pending`, not misleading zero;
12. PT Nobi Putra Angkasa scope is enforced in the data layer;
13. payment is not declared valid until payment record and receivable reconciliation samples agree;
14. regression cases pass for each approved mapping.

## 10. Implementation Sequence

### Sprint 0A — Business Process Validation

- validate CT-00 to CT-13 with process owners;
- identify Odoo, Hybrid, Manual, and Pending coverage;
- select sample transactions;
- record actual evidence and expected SOP outcome.

### Sprint 0B — Data and Dashboard Reconciliation

- trace sample records through existing views/APIs;
- compare Dashboard output with Odoo and physical/manual evidence;
- classify mismatch as data issue, dashboard logic issue, SOP gap, or valid exception;
- approve node and rule mappings.

### Sprint 1 — Read Model

- build normalized document links;
- create stage status and validation evidence views;
- create stage summary API;
- add source timestamp, readiness, coverage, and confidence.

### Sprint 2 — UI

- process map;
- stage worklist;
- journey detail;
- deep links to existing dashboards.

### Sprint 3 — Consistency Rules

- implement approved Priority 1 rules;
- add severity and owner;
- add SOP Rule Explorer;
- run regression tests.

### Future Phase — Active Improvement Loop

- formal ticketing;
- assignment/evidence/verification/closure;
- AI SOP impact proposal;
- human approval workflow.

## 11. Explicit Non-Goals for Current Scope

- writing back to Odoo;
- replacing Odoo UI;
- automatic process correction;
- formal ticketing implementation;
- automatic SOP publication;
- profitability/COGS engine;
- choosing a payment source of truth before Accounting reconciliation validation;
- treating manual production completion as proven only from Odoo status.