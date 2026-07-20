# Phase 0 Decision Register — Control Tower

**Status:** validation completed; stakeholder approval gate remains  
**Authority:** `docs/09_Odoo18_Validation/SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md`

## 1. Confirmed Decisions

| ID | Decision | Status |
| --- | --- | --- |
| `CTD-001` | Business-facing term is **Tahap Proses**; technical term may remain `Process Node`. | Confirmed |
| `CTD-002` | Odoo Protocol defines expected process; Dashboard Odoo checks actual data and exceptions. | Confirmed |
| `CTD-003` | Human process owners and VP Operations retain approval authority. | Confirmed |
| `CTD-004` | Customer PO / Confirmed Quotation is the business start; Sales Order is the technical customer root. | Confirmed |
| `CTD-005` | Confirmed SO from 2026 requires Customer Reference and Customer PO Date. | Confirmed by closure audit |
| `CTD-006` | Distribusi JO is outside Odoo and may occur while SO is Draft. | Confirmed correction |
| `CTD-007` | SO state must not be used to infer Distribusi JO completion. | Confirmed |
| `CTD-008` | Approvals remain inside the relevant document node, not a generic Approval node. | Confirmed structure |
| `CTD-009` | SO fulfilment is classified per line and rolled up to `MIXED_SOURCE` when needed. | Confirmed |
| `CTD-010` | IO-linked SO may create an MO that auto-cancels as `MO_SUPPRESSED_BY_IO`. | Confirmed custom behavior |
| `CTD-011` | ROP→RFQ/PO is a custom user-triggered Server Action. | Confirmed custom behavior |
| `CTD-012` | PO Confirmed/Purchase is the official operational approval state. | Confirmed |
| `CTD-013` | Reset to Draft is correction and may leave open/reserved/accounting downstream. | Confirmed runtime behavior |
| `CTD-014` | Cancel success is determined by final state; error may coexist with successful state change. | Confirmed runtime behavior |
| `CTD-015` | Done/Posted downstream remains historical evidence. | Confirmed governance |
| `CTD-016` | Production is Hybrid Odoo–Manual. | Confirmed current condition |
| `CTD-017` | Native IDs and relation tables take precedence over display text. | Confirmed data contract |
| `CTD-018` | IO administrative state is separate from derived Production and Utilization statuses. | Confirmed |
| `CTD-019` | Unresolved IO product/UoM/multi-IO allocation remains `DATA_EXCEPTION`. | Confirmed safety rule |
| `CTD-020` | Payment truth uses residual and reconciliation; final labels need Accounting. | Confirmed technical basis / owner decision pending |
| `CTD-021` | Initial Control Tower remains read-only. | Confirmed guardrail |
| `CTD-022` | Missing/manual/provisional data is shown explicitly, never fabricated as zero. | Confirmed guardrail |
| `CTD-023` | PT Nobi Putra Angkasa is the initial business scope; technical design should remain extensible. | Confirmed |
| `CTD-024` | Formal ticketing, write-back, and AI SOP proposals remain future scope. | Confirmed deferral |

The earlier statement that Distribusi JO must follow SO Confirm is superseded.

## 2. Approval Placement

| Approval / Review | Control Tower placement |
| --- | --- |
| SO Confirm by VP Operations | `CT-01 Sales Order & Approval` |
| ROP approval | `CT-06 RKB / ROP` |
| PO Confirm | `CT-07 RFQ / Purchase Order` |
| Reset/Unlock request and approval | `CT-X1 Correction / Reset / Cancellation Exposure` overlay |
| exception approval | related exception/root document |
| Accounting correction approval | Invoice/Payment node and Accounting procedure |

## 3. Decisions Still Required

| ID | Decision | Why it matters | Owner |
| --- | --- | --- | --- |
| `CTV-001` | Data Health Owner and review cadence | required for worklist ownership/escalation | VP Operations |
| `CTV-002` | structured Log Note format, reason codes, and approvers | required for correction audit trail | VP Operations / process owners |
| `CTV-003` | payment/reconciliation labels and accepted adjustments | required before CT-13 KPI publication | Accounting |
| `CTV-004` | DP, overpayment, Credit Note/write-off/compensation treatment | required for settlement classification | Accounting |
| `CTV-005` | management payment date | required for aging/reporting | Accounting |
| `CTV-006` | IO product matching and UoM conversion | required for production KPI | PPIC / Operations |
| `CTV-007` | multi-IO SO quantity allocation | required for utilization KPI | PPIC / Operations |
| `CTV-008` | Parent–Child MO persistent relation | required for genealogy rules | PPIC / Odoo technical owner |
| `CTV-009` | cancellation/replacement procedure for PO/Receipt and SO/Delivery | required for corrective SOP | Procurement/WHD/Marketing/Operations |
| `CTV-010` | customer commercial attachment/evidence policy | reference/date already confirmed; attachment policy remains open | Marketing |
| `CTV-011` | aging/SLA thresholds | required for Waiting/Blocked severity | process owners / VP Operations |
| `CTV-012` | deep-link access by role | required for production UI | Odoo Admin |

## 4. Deferred

| ID | Topic | Reason |
| --- | --- | --- |
| `CTF-001` | centralized ticket tool | governance owner/status model must be approved first |
| `CTF-002` | write-back from dashboard | read-only first release |
| `CTF-003` | AI-generated SOP change workflow | requires trusted closed issues and version governance |
| `CTF-004` | production configuration automation | outside current documentation/analytics scope |

## 5. Completed Validation Evidence

- Odoo 18 dataset identity and schema/relationship audit;
- automation/server-action mapping;
- controlled runtime cancellation/reset audit;
- final read-only closure audit;
- 348 cancelled POs with zero open Receipt anomalies in 2026 scope;
- 357 confirmed SOs with complete reference/date in 2026 scope;
- 39 IO production/utilization classifications with explicit Data Exceptions;
- final SOP–System Alignment Matrix;
- validated Rule Catalog and Dashboard Backlog.

## 6. Current Gate Order

1. stakeholder decisions in Section 3;
2. SOP Draft v2 approval;
3. freeze data contract and acceptance tests;
4. native relation extraction;
5. canonical/exception SQL views;
6. API;
7. Control Tower UI;
8. production-safe UAT and release.

Every approved decision must update:

- Process Node Register;
- Rule Registry;
- Data Readiness Matrix;
- MVP Specification;
- relevant SOP section;
- tests and evidence;
- rule/SOP version.
