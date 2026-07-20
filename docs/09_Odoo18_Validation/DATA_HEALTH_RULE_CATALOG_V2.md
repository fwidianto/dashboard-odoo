# Data Health Rule Catalog v2

**Status:** validated rule baseline for future Control Tower  
**Date:** 20 July 2026  
**Authority:** `SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md`

No rule in this catalog may automatically mutate Odoo records.

## 1. Rule Contract

Every implemented rule must expose:

- stable Rule ID;
- area and process owner;
- root and related native Odoo IDs;
- direct relation path;
- business and technical conditions;
- exclusions/accepted exceptions;
- severity and age basis;
- evidence/confidence;
- SOP reference and rule version;
- positive, negative, and exception test cases.

## 2. Confirmed Rules

| Rule ID | Output / Condition | Default severity | Status |
| --- | --- | --- | --- |
| `DH2-SALES-001` | Confirmed SO from 2026 missing Customer Reference or Customer PO Date | High | Implementable |
| `DH2-SALES-002` | More than one line fulfilment source → `MIXED_SOURCE` | Info/High if unresolved | Implementable after line contract |
| `DH2-SALES-003` | IO-linked SO MO auto-cancel → `MO_SUPPRESSED_BY_IO` | Informational | Implementable |
| `DH2-SALES-004` | Cancelled SO with open MO/Delivery/PO/Invoice/Backorder | High/Critical | Implementable |
| `DH2-PROC-001` | Chatter-proven reset PO with open Receipt/Move/Bill | High | Implementable |
| `DH2-PROC-002` | Cancelled PO with incoming Receipt not Cancel/Done | High/Critical | Implementable |
| `DH2-PROC-003` | Approved ROP without related RFQ/PO after threshold | High | Threshold pending |
| `DH2-PROC-004` | Cancelled/refused ROP with active RFQ/PO | High | Header state contract pending |
| `DH2-INV-001` | PO ordered quantity differs from active Receipt demand | Critical/High | UoM contract required |
| `DH2-INV-002` | Receipt Cancelled while PO remains open | Review Signal | Implementable |
| `DH2-DEL-001` | Delivery Cancelled while SO remains open | Medium/High | Implementable |
| `DH2-CORR-001` | Error and unchanged final state → `CANCEL_BLOCKED_OR_FAILED` | High | Runtime log required |
| `DH2-CORR-002` | Error but target state changed → `ACTION_APPLIED_WITH_RPC_ERROR` | High technical | Runtime log required |
| `DH2-CORR-003` | Cancel/Reset parent with Done/Posted downstream | Review/High | Implementable |
| `DH2-CORR-004` | Cancel/Reset parent with Reserved/Partial/Backorder downstream | High/Critical | Implementable |

Audit anchors:

- 357 confirmed SOs in 2026 scope; zero missing Customer Reference/PO Date;
- 348 cancelled POs in 2026 scope; zero open Receipt anomalies;
- one chatter-proven reset PO exposure with assigned Receipt;
- runtime evidence for MO cancellation cascade, Receipt/Delivery partial cascade, and Draft Invoice state change with RPC error.

## 3. Provisional IO Rules

### `DH2-IO-001` — Production Status

Compare requested IO quantity with active MO planned quantity, Done-MO planned quantity, and actual produced quantity.

Outputs:

- `NOT_STARTED`;
- `IN_PROGRESS`;
- `PARTIALLY_PRODUCED`;
- `FULLY_PRODUCED`;
- `OVER_PRODUCED`;
- `CANCELLED`;
- `DATA_EXCEPTION`.

### `DH2-IO-002` — Utilization Status

Compare produced quantity with direct SO utilization evidence.

Outputs:

- `NOT_UTILIZED`;
- `PARTIALLY_UTILIZED`;
- `FULLY_UTILIZED`;
- `OVER_UTILIZED`;
- `DATA_EXCEPTION`.

### Safety classifications

- `IO_PRODUCTION_DATA_EXCEPTION` for incompatible product/UoM, contradictory lifecycle, or missing direct IO–MO relation.
- `IO_UTILIZATION_DATA_EXCEPTION` for multi-IO SO without trusted allocation, mismatch, or missing relation.

Publication of final KPIs requires approved product matching, UoM conversion, rounding, allocation, and tolerance rules.

## 4. Manufacturing and WIP Rules

| Rule ID | Condition | Status |
| --- | --- | --- |
| `DH2-MRP-001` | Cancelled MO with active/reserved raw-material or WIP evidence | Implementable after relation contract |
| `DH2-MRP-002` | Done MO without required FG completion to Stock | Implementable |
| `DH2-MRP-003` | WIP without active MO, future plan, return, consumption, owner, or disposition | Contextual |
| `DH2-MRP-004` | Parent Done before Child | Blocked until trusted Parent–Child relation |

WIP age alone is a review signal, not an automatic violation until an SLA is approved.

## 5. Accounting Rules

| Rule ID | Condition | Status |
| --- | --- | --- |
| `DH2-ACC-001` | Payment label conflicts with residual/reconciliation | Taxonomy pending |
| `DH2-ACC-002` | Payment posted but invoice not reconciled | Label pending |
| `DH2-ACC-003` | Invoice settled by Credit Note/adjustment/write-off/compensation | Journal list/label pending |
| `DH2-ACC-004` | Sales helper paid field differs from accounting truth | Implementable after truth view |

Accounting source of truth must use posted invoice, residual, receivable journal items, reconciliation, payment entries, and adjustment evidence.

## 6. Manual Evidence Rules

Current Odoo state alone cannot prove:

- Distribusi JO completion;
- physical inspection/QC;
- signed Delivery acceptance;
- service BAP/BAST;
- complete production external documentation;
- physical WIP condition;
- external approval not recapped into Odoo;
- action error followed by successful state transition without runtime logs.

Use attachment, reference number, structured Log Note, checklist, or manual verification.

## 7. Implementation Gate

A rule is ready for coding only when:

1. model/field/relation paths are known;
2. inclusion and exclusion logic are approved;
3. company scope uses stable ID;
4. quantity/UoM basis is explicit;
5. severity and owner are assigned;
6. false-positive handling is defined;
7. test cases exist;
8. unresolved allocation is not inferred.
