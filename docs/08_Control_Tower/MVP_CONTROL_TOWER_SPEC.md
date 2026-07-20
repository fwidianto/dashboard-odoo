# MVP Specification — Odoo Protocol Control Tower

**Status:** Phase 0 Draft v3 — post-validation, pre-implementation  
**Authority:** `docs/09_Odoo18_Validation/`

## 1. Product Objective

The first release is a read-only Control Tower that:

- traces SO/IO/MO/ROP/PO/Receipt/Delivery/Invoice/Payment relationships;
- shows native and canonical states without hiding uncertainty;
- identifies reset/cancellation downstream exposure;
- exposes owner, severity, evidence, confidence, and SOP rule;
- reuses validated dashboard assets only after data-contract reconciliation.

The MVP does not write to Odoo, close issues automatically, or publish unapproved Payment/IO KPIs.

## 2. Process Architecture

```text
Customer PO / Confirmed Quotation
→ Sales Order
→ line-level fulfilment: Stock / IO / New MO / Mixed
→ RKB / ROP when required
→ user-triggered RFQ / PO
→ Receipt and inspection
→ Material Transfer / WIP
→ Production / FG to Stock
→ Delivery
→ Invoice
→ Payment / Collection
```

Distribusi JO is displayed as a separate manual milestone/coverage indicator. It may occur while SO is Draft and is not a mandatory Odoo transition between Sales Order and fulfilment.

Cross-cutting overlays:

- approval;
- Reset/Unlock/Cancel exposure;
- exception severity;
- Log Note/manual evidence;
- rule/SOP version;
- owner and confidence.

## 3. MVP Pages

### 3.1 Header

- company/site;
- source refresh timestamp;
- SOP/rule/validation version;
- total Critical/High review items;
- filters: date, owner, customer/project, source, state, severity, confidence, coverage.

### 3.2 Process Map

Each node shows only data-valid counts:

- Open/Waiting;
- Ready/Reserved;
- Partial/Backorder;
- Done/Posted;
- Cancelled;
- Exception/Needs Review;
- oldest age;
- highest severity;
- owner;
- readiness/confidence/coverage.

Manual/provisional nodes return a reason and `counts_are_valid=false`, not fabricated zero.

### 3.3 Exception Worklist

Minimum columns:

```text
Rule ID
Severity
Root model/ID/reference
Related model/ID/reference
Native state
Canonical state
Status reason
Age
Process owner
Evidence/confidence
Suggested review
SOP reference
Source updated at
```

### 3.4 Record Journey

For one SO or IO show:

- customer-order evidence;
- line-level source;
- `MIXED_SOURCE` and `MO_SUPPRESSED_BY_IO` where relevant;
- all native upstream/downstream relations;
- open/reserved/partial/backorder exposure;
- Done/Posted historical evidence;
- manual/hybrid milestones;
- Invoice residual and reconciliation evidence where available;
- rule/evidence/confidence.

### 3.5 IO Panel

Display separately:

- administrative state;
- Production Status;
- Utilization Status;
- requested/planned/produced/utilized quantities;
- `DATA_EXCEPTION` reason.

Do not publish final KPI percentages before product/UoM/allocation approval.

### 3.6 Accounting Panel

Display transaction evidence first:

- invoice state/posting;
- residual;
- reconciliation status;
- payment records;
- reversal/Credit Note/adjustment evidence.

Business-facing Payment labels remain gated by Accounting approval.

## 4. Required Data Contract

1. native IDs for every root and related record;
2. direct SO–IO many-to-many extraction;
3. line-level fulfilment source;
4. stable company ID;
5. picking/move/move-line/reservation/backorder relations;
6. invoice/move-line/residual/reconciliation relations;
7. separate administrative, operational, derived, and manual states;
8. evidence/confidence and rule version;
9. explicit `UNKNOWN`/`DATA_EXCEPTION` behavior;
10. cancelled parents remain visible when downstream exposure exists.

## 5. Core Exception Scope

Initial worklist supports:

- `MO_SUPPRESSED_BY_IO` as valid informational state;
- `MIXED_SOURCE`;
- `RESET_TO_DRAFT_WITH_OPEN_DOWNSTREAM`;
- `CANCELLED_PO_WITH_OPEN_RECEIPT`;
- `CANCELLED_SO_WITH_ACTIVE_DOWNSTREAM`;
- reserved/partial/backorder/done downstream overlays;
- `IO_PRODUCTION_DATA_EXCEPTION`;
- `IO_UTILIZATION_DATA_EXCEPTION`;
- Accounting truth conflicts after taxonomy approval.

`CANCEL_BLOCKED_OR_FAILED` and `ACTION_APPLIED_WITH_RPC_ERROR` require runtime/action observability and may initially remain audit/manual evidence rather than continuously derived rules.

## 6. Proposed API Contracts

### `GET /api/control-tower/process-map`

Returns node readiness, coverage, confidence, valid counts, age, and severity.

### `GET /api/control-tower/nodes/{node_id}/records`

Server-side filters and pagination by state, owner, severity, date, source, company/site, confidence, and coverage.

### `GET /api/control-tower/journey/{root_model}/{root_id}`

Returns the normalized native-ID document graph and stage summary.

### `GET /api/control-tower/exceptions`

Returns rule outputs with owner, evidence, confidence, SOP reference, and suggested review.

### `GET /api/control-tower/rules/{rule_id}`

Returns versioned business/technical rule metadata and readiness.

No endpoint performs write-back in the MVP.

## 7. Proposed Read Models

```text
vw_ct_native_relations
vw_ct_process_instances
vw_ct_line_source
vw_ct_stage_status
vw_ct_document_links
vw_ct_parent_downstream_exposure
vw_ct_io_production_status
vw_ct_io_utilization_status
vw_ct_accounting_truth
vw_ct_exception_worklist
vw_ct_stage_summary
vw_ct_order_journey
```

Views are built in this order: native relations → transaction facts → canonical statuses → exceptions → aggregates.

## 8. UI Guardrails

- server-side pagination/filtering;
- no all-row client hydration;
- ERP, Derived, Hybrid, Manual, and Unknown states are visually distinct;
- Done/Posted history is not hidden because a parent is Cancel/Draft;
- raw diagnostics remain expandable;
- existing dashboard pages remain deep links until replaced;
- no direct Odoo write action;
- no auto-close or AI SOP publication.

## 9. Acceptance Criteria

The MVP is acceptable when:

1. counts reconcile to worklists and sampled Odoo records;
2. every join uses native IDs where available;
3. SO–IO many-to-many and mixed-source lines are represented correctly;
4. `MO_SUPPRESSED_BY_IO` is not counted as production failure;
5. Distribusi JO is shown as manual, not inferred from SO state;
6. reset/cancel downstream exposure remains visible;
7. manual/hybrid evidence is labelled honestly;
8. `DATA_EXCEPTION` is preserved rather than allocated by inference;
9. company scope uses stable ID;
10. Payment labels are not published before Accounting approval;
11. every exception has Rule ID, owner, severity, evidence/confidence, and SOP reference;
12. normal, partial, reset, cancelled, Done/Posted, manual, and accepted-exception tests pass;
13. performance uses server-side data access;
14. source timestamp and rule/SOP version are visible.

## 10. Implementation Sequence

1. stakeholder and SOP approval gate;
2. native relation extraction;
3. line source and stock/accounting truth contract;
4. canonical state and exception views;
5. reconciliation/regression tests;
6. server-side APIs;
7. process map, worklist, and journey UI;
8. IO panel after quantity-contract approval;
9. Accounting panel after taxonomy approval;
10. production-safe UAT and release.

Formal ticketing, write-back, and AI change proposal are later phases.
