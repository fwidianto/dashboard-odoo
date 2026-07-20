# Dashboard Implementation Backlog v2

**Status:** prepared; implementation not yet authorized  
**Authority:** SOP–System Alignment Matrix Final and Data Health Rule Catalog v2

The order below prevents UI work from masking incorrect joins or unresolved business allocation.

## Phase 0 — Approval and Freeze

| Item | Owner | Acceptance |
| --- | --- | --- |
| Approve SOP Draft v2 | VP Operations / process owners | confirmed flow, correction/cancel controls, ownership, and exception vocabulary |
| Freeze Accounting taxonomy | Accounting | payment labels, reconciliation, adjustment/Credit Note/DP/overpayment, payment date |
| Freeze IO quantity contract | PPIC / Operations / Data Owner | product matching, UoM conversion, multi-IO allocation, tolerance |
| Assign Data Health governance | VP Operations | owner, cadence, severity escalation, reason codes, accepted exception process |

## Phase 1 — Extraction Integrity

### P1-01 Preserve native IDs

Add stable IDs for company, SO/line, IO request/line, MO, ROP, PO/line, picking/move/move line, invoice/move line, payment, and reconciliation records.

### P1-02 Extract SO–IO many-to-many directly

Support one SO to many IOs and one IO to many SOs. Do not use display/set text as the primary relation and do not infer quantity allocation.

### P1-03 Extract line-level fulfilment evidence

For each SO line expose Stock, IO, and new-MO evidence, quantities, source confidence, and reason. Do not flatten mixed SOs to IO-first.

### P1-04 Stable company scope

Replace display-name filtering with company ID/configuration.

### P1-05 Stock lifecycle

Extract picking, move, move line, reservation, backorder, source/destination, and completion evidence.

### P1-06 Accounting truth layer

Extract invoice/posting state, residual, receivable lines, partial/full reconciliation, payment, reversal/Credit Note, and adjustment evidence.

Payment KPI remains gated by Accounting approval.

## Phase 2 — Canonical Data Contract

### P2-01 SO source classifier

Outputs:

- `FROM_STOCK`;
- `FROM_INTERNAL_ORDER`;
- `MAKE_TO_ORDER`;
- `MIXED_SOURCE`;
- `SOURCE_DATA_EXCEPTION`.

### P2-02 MO suppression classifier

Detect `MO_SUPPRESSED_BY_IO` and exclude it from ordinary production-cancellation failure metrics.

### P2-03 Canonical state groups

- Draft;
- Open/Waiting;
- Ready/Assigned/Reserved;
- Partial/Backorder;
- Done/Posted;
- Cancelled;
- Unknown.

### P2-04 Reset/cancellation exposure

Implement:

- `RESET_TO_DRAFT_WITH_OPEN_DOWNSTREAM`;
- `CANCELLED_PO_WITH_OPEN_RECEIPT`;
- `CANCELLED_SO_WITH_ACTIVE_DOWNSTREAM`;
- reserved, partial, backorder, and done/posted overlays.

### P2-05 IO provisional views

Calculate only safe exact-match cases and retain `DATA_EXCEPTION` for unresolved product/UoM/allocation. Administrative, production, and utilization states remain separate.

### P2-06 Evidence and confidence

Every node/rule exposes relation path, evidence source, confidence, manual-evidence requirement, refresh time, and rule version.

## Phase 3 — SQL and API

### P3-01 Truth-layer sequence

1. native relation staging;
2. transaction fact views;
3. canonical status views;
4. exception views;
5. dashboard aggregates.

### P3-02 Incremental synchronization

Require idempotency, watermark/checkpoint, relation-table refresh, cancellation/deletion handling, retry/failure logs, and no browser-side all-row hydration.

### P3-03 Exception API

Return rule ID, root/related IDs, severity, owner, age, evidence/confidence, suggested review, SOP reference, and future workflow status placeholder.

### P3-04 Reconciliation tests

- aggregate count reconciliation;
- sampled end-to-end journeys;
- Draft/Open/Partial/Done/Cancel coverage;
- multi-company scope;
- null/unknown behavior;
- zero display-name joins.

## Phase 4 — Control Tower UI

### P4-01 Exception Worklist

Filters: severity, area, owner, rule, status, age, company/site, and evidence confidence.

### P4-02 End-to-end trace

Show SO/IO/MO/ROP/PO/Receipt/Delivery/Invoice/Payment relationships using native IDs and business references.

### P4-03 Parent/downstream exposure

Visually separate Open, Reserved, Partial, Done/Posted history, Cancelled, and Data Exception.

### P4-04 IO panel

Show administrative, production, and utilization statuses separately; never hide `DATA_EXCEPTION`.

### P4-05 Accounting panel

Implement only after Accounting taxonomy approval and accounting truth extraction.

### P4-06 Performance

Use server-side pagination/filtering and aggregated endpoints. Avoid hydrating all records client-side.

## Phase 5 — Governance and Release

### P5-01 Rule version registry

Link rule version to SOP version and effective date.

### P5-02 UAT

Test normal, partial, reset, cancelled, manual-evidence, and accepted-exception samples.

### P5-03 Production-safe release

Use a fresh read-only validation snapshot, configuration comparison, rollback plan, and post-release count reconciliation. Do not assume neutralized staging configuration represents production.

### P5-04 Future workflow

Ticketing, write-back, and AI change proposal remain future scope. Initial Control Tower can remain read-only.

## Priority Summary

1. owner decisions and SOP approval;
2. native relationships and extraction;
3. line-level source and cancellation/reset data contract;
4. SQL/API truth and exception views;
5. Control Tower UI;
6. Payment and IO KPI publication after approval;
7. ticketing, write-back, and AI proposal workflow.

Frontend redesign must not begin before Phase 1–2 acceptance.
