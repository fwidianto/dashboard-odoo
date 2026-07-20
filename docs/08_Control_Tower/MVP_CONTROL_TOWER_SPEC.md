# MVP Specification — Odoo Protocol Control Tower

Status: Phase 0 Draft v1

## 1. MVP Objective

Build one read-only application page that shows the end-to-end Odoo process as clickable stages and reuses the existing traceability views/APIs.

MVP must answer:

1. How many records are currently at each stage?
2. Which records are waiting, in progress, partial, blocked, completed, or exception?
3. Who owns the next action?
4. Which SOP rule applies?
5. What upstream/downstream documents are related?

## 2. Page Structure

### A. Header

- selected company;
- data refresh timestamp;
- SOP version;
- Rule Registry version;
- total open Critical/High exceptions;
- filters: date, owner, customer/project, source type, status.

### B. End-to-End Process Map

```text
Quotation
→ Sales Order
→ Approval
→ Fulfilment Decision
→ Internal Order / Manufacturing
→ RKB / ROP
→ RFQ / PO
→ Receipt
→ Material Transfer
→ Production / Finish Good
→ Delivery
→ Invoice
→ Payment
```

Every stage card shows:

- active count;
- waiting count;
- partial count;
- exception count;
- oldest age;
- highest severity;
- data-readiness badge.

### C. Stage Worklist

Clicking one stage opens a table with:

```text
Document Number
Root SO / IO
Customer / Project
Native Status
Canonical Status
Status Reason
Age
Owner
Related Documents
Open Exceptions
Highest Severity
SOP / Rule
Last Activity
```

### D. Record Journey Drawer/Page

Clicking one record opens:

- root identity and source classification;
- horizontal/vertical process journey;
- current stage;
- completed stages;
- waiting/blocked stages;
- related SO, IO, MO, ROP, PO, Receipt, Delivery, Invoice;
- anomaly/ticket history;
- related SOP sections and Rule IDs;
- data confidence and source timestamp.

## 3. MVP Live Scope

### Fully Live First

1. Sales Order;
2. Fulfilment Decision;
3. Internal Order / Manufacturing summary;
4. Delivery;
5. Invoice progress.

### Partially Live

1. RKB / ROP;
2. RFQ / Purchase Order;
3. Receipt;
4. WIP / Finish Good.

### Visible but Pending Mapping

1. Quotation;
2. full approval event history;
3. Payment / Collection;
4. formal ticketing.

Pending stages remain visible so the final process architecture is not hidden. They must show `Data Mapping Pending`, not zero records.

## 4. Proposed API Contracts

### `GET /api/control-tower/process-map`

Returns aggregate stage health:

```json
{
  "sop_version": "draft-v4",
  "rule_version": "v1",
  "source_updated_at": "timestamp",
  "nodes": [
    {
      "node_id": "CT-01",
      "name": "Sales Order",
      "readiness": "READY",
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

### `GET /api/control-tower/nodes/{node_id}/records`

Filters:

- canonical status;
- owner;
- severity;
- date range;
- customer/project;
- source type;
- page and page size.

### `GET /api/control-tower/journey/{root_type}/{root_id}`

Returns complete journey for one SO or IO.

### `GET /api/control-tower/rules/{rule_id}`

Returns business-facing rule metadata and SOP reference.

## 5. Proposed Data Views

```text
vw_ct_process_instances
vw_ct_stage_status
vw_ct_stage_summary
vw_ct_document_links
vw_ct_exception_worklist
vw_ct_order_journey
```

### `vw_ct_process_instances`

One row per root SO/IO.

### `vw_ct_stage_status`

One row per root and node.

### `vw_ct_stage_summary`

Aggregate counts used by the process map.

### `vw_ct_document_links`

Normalized upstream/downstream document graph.

### `vw_ct_exception_worklist`

Rule output linked to owner and SOP.

### `vw_ct_order_journey`

UI-ready root-level journey summary.

## 6. UI Behavior

- Stage click filters without navigating away where practical.
- Exception count opens the worklist prefiltered to `EXCEPTION`.
- Status reason must be readable, not only code.
- Raw technical diagnostics stay behind an expandable section.
- Existing Sales Order/Internal Order pages remain available as deep links.
- No write action to Odoo in MVP.
- No automatic ticket closure or SOP update in MVP.

## 7. Acceptance Criteria

MVP is acceptable when:

1. one SO can be traced to all currently available related documents;
2. each live stage count can be reconciled to its worklist;
3. one click from stage to record detail works;
4. each exception shows Rule ID, owner, severity, suggested action, and SOP reference;
5. source timestamp and data confidence are visible;
6. cancelled records are excluded from active counts but remain searchable;
7. mixed-source SO is represented at line and header level;
8. missing stages show `Data Mapping Pending`, not misleading zero values;
9. PT Nobi Putra Angkasa company scope is enforced in the data layer;
10. regression test cases pass for selected sample transactions.

## 8. Implementation Sequence

### Sprint 0 — Contract

- confirm node register;
- confirm canonical statuses;
- confirm root IDs;
- confirm initial rules;
- select sample records.

### Sprint 1 — Read Model

- build normalized document links;
- create stage status view;
- create stage summary API;
- add source timestamp and readiness.

### Sprint 2 — UI

- process map;
- stage worklist;
- journey detail;
- deep links to existing dashboards.

### Sprint 3 — Exceptions

- implement Priority 1 rules;
- add severity and owner;
- add SOP Rule Explorer.

### Sprint 4 — Active Loop

- ticket storage/link;
- human verification;
- AI SOP impact proposal;
- human approval workflow.

## 9. Explicit Non-Goals for MVP

- writing back to Odoo;
- replacing Odoo UI;
- automatic process correction;
- automatic SOP publication;
- profitability/COGS engine;
- payment conclusion before reconciliation mapping is confirmed.
