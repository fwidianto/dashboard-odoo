# Data Readiness Matrix — Odoo Protocol Control Tower

**Status:** Phase 0 Draft v3 — post-validation readiness  
**Authority:** `docs/09_Odoo18_Validation/`

## 1. Readiness Scale

- `READY_FOR_DESIGN`: business meaning and direct data path are sufficiently proven for data-contract design.
- `PARTIAL`: data exists but relation, exclusion, evidence, or business rule remains incomplete.
- `PROVISIONAL`: calculation can be drafted but owner decisions are still required.
- `MANUAL`: current process/evidence is outside Odoo.
- `HYBRID`: Odoo proves recorded execution while actual completion needs external evidence.
- `RUNTIME_ONLY`: static data cannot prove action attempt/result behavior.
- `BLOCKED`: trusted source/relation/decision is unavailable.
- `DEFERRED`: future workflow scope.

## 2. Stage Readiness

| Node | Stage | Primary data | Readiness | Confirmed position | Main remaining gap |
| --- | --- | --- | --- | --- | --- |
| `CT-00` | Customer PO / Confirmed Quotation | SO reference/date + manual evidence | READY_FOR_DESIGN / MANUAL | 357 confirmed SOs in 2026 had both fields | attachment/evidence policy |
| `CT-01` | Sales Order & Approval | SO/lines/state/chatter | READY_FOR_DESIGN | confirmed `sale` state is system approval | detailed reset action and cancellation owner policy |
| `CT-02` | Distribusi JO | external communication | MANUAL | outside Odoo; may occur while SO Draft | future evidence/recording design |
| `CT-03` | Fulfilment Classification | SO lines, SO–IO relation, MO, stock | PARTIAL | line-level source; header may `MIXED_SOURCE` | extraction currently loses/flatttens some relations |
| `CT-04` | Internal Order | approval request/line, IO–MO, SO–IO | PROVISIONAL | administrative state is not production progress | product/UoM and multi-IO allocation |
| `CT-05` | Manufacturing Planning | MO, components, schedule, source | PARTIAL / HYBRID | MO suppression by IO is known | component completeness and source contract |
| `CT-06` | RKB / ROP | approval header/line, PO-line links | PARTIAL | ROP→RFQ/PO is custom user-triggered action | exact header states, thresholds, cancel/refuse action |
| `CT-07` | RFQ / Purchase Order | PO/lines/state/ROP links | READY_FOR_DESIGN / PARTIAL | PO Confirmed is approval; Reset may leave downstream | quantity/UoM mismatch exclusions; review governance |
| `CT-08` | Receipt & Inspection | picking/move/move line + evidence | READY_FOR_DESIGN / HYBRID | Cancel Receipt does not cancel PO | inspection/BAP evidence contract |
| `CT-09` | Material Transfer / WIP | picking/move/location | PARTIAL / HYBRID | Bon is separate from consumption | operation/site mapping and WIP disposition |
| `CT-10` | Production / FG | MO raw/finished moves + external docs | HYBRID | movement path and legacy locations confirmed | shop-floor coverage and Parent–Child relation |
| `CT-11` | Delivery | outgoing picking/moves + signed evidence | READY_FOR_DESIGN / HYBRID | Cancel Delivery does not cancel SO | signed evidence and replacement-delivery policy |
| `CT-12` | Invoice | account move/lines, SO linkage | READY_FOR_DESIGN | Draft Cancel final state must be verified after errors | DP/final business rules |
| `CT-13` | Payment / Collection | residual, AR lines, reconciliation, payments | PROVISIONAL | technical truth basis confirmed | Accounting taxonomy and accepted adjustments |
| `CT-X1` | Reset / Cancellation Exposure | parent/child states, chatter, action logs | PARTIAL / RUNTIME_ONLY | final-state and downstream review required | persistent action/result observability and Log Note enforcement |
| `CT-X2` | Exception Worklist | rule outputs | READY_FOR_DESIGN | validated exception vocabulary available | owner/cadence/status workflow |

## 3. Confirmed Data Assets

Reusable assets include:

- Internal Order Traceability;
- Manufacturing Traceability;
- Sales Order Traceability;
- Delivery and Invoice Progress Tracking;
- Procurement Receipt/Billing Tracking;
- JSON APIs and dashboard pages;
- Odoo 18 validation scripts and reports.

These assets require v2 relation and rule corrections before production Control Tower use.

## 4. Highest-Priority Data Gaps

1. direct SO–IO many-to-many extraction;
2. line-level fulfilment source rather than header IO precedence;
3. stable company ID rather than display-name filter;
4. stock reservation/backorder and parent/downstream exposure;
5. accounting residual/reconciliation truth layer;
6. product/UoM and multi-IO allocation contract;
7. Parent–Child MO persistent relation;
8. manual evidence contract for Distribusi JO, inspection, production, and signed Delivery;
9. action/result observability for blocked/error actions.

## 5. Confidence and Coverage

### Confidence

| Value | Meaning |
| --- | --- |
| `HIGH` | direct relation and confirmed rule |
| `MEDIUM` | derived but approved logic |
| `LOW` | unresolved inference; human review required |
| `MANUAL` | cannot be determined from ERP alone |

### Coverage

| Value | Meaning |
| --- | --- |
| `ODOO` | main state/evidence is in Odoo |
| `DERIVED` | calculated from trusted Odoo relationships |
| `HYBRID` | Odoo plus external evidence |
| `MANUAL` | outside Odoo |
| `RUNTIME_ONLY` | requires action/log instrumentation |

Low/manual/provisional records must be displayed as `Needs Review` or `DATA_EXCEPTION`, not confirmed faults.

## 6. Current Priority Sequence

### Priority A — Stakeholder gate

- Data Health Owner/cadence;
- Log Note/reason-code governance;
- Accounting taxonomy;
- IO product/UoM/allocation;
- cancellation/replacement procedure by owner.

### Priority B — Extraction integrity

- native IDs;
- relation tables;
- SO line source;
- stock lifecycle;
- accounting reconciliation;
- stable company scope.

### Priority C — Canonical and exception views

- canonical state groups;
- reset/cancel exposure;
- `MO_SUPPRESSED_BY_IO`;
- `MIXED_SOURCE`;
- IO provisional statuses and data exceptions.

### Priority D — API/UI

- server-side exception API;
- end-to-end trace;
- parent/downstream exposure;
- Exception Worklist;
- IO and Accounting panels after gates.

## 7. Validation Evidence Completed

Completed technical validation includes:

- 12-model dataset identity gate;
- 1,236 SO, 6,087 PO, 11,330 MO, and 39,490 picking scope;
- 34 active automation/runtime configuration review;
- controlled cancellation/reset runtime scenarios;
- 348 cancelled-PO closure audit with zero open Receipt anomaly;
- 357 confirmed-SO evidence audit with zero missing reference/date;
- 39 IO production/utilization classifications with explicit Data Exceptions.

## 8. Production Readiness Gate

A node/rule is not production-ready until:

1. process owner approves business meaning;
2. direct models/fields/relations are documented;
3. company/state/date filters are explicit;
4. null, duplicate, mixed, partial, reset, cancel, done/posted, and manual cases are tested;
5. exclusion and accepted-exception logic is approved;
6. severity and owner are assigned;
7. results reconcile to sampled Odoo records and operational evidence;
8. rule and SOP versions are linked;
9. no unresolved allocation is inferred.
