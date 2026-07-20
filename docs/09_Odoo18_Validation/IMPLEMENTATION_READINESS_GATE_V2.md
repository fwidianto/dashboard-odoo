# Implementation Readiness Gate v2

**Project:** Dashboard Odoo / Odoo Protocol Control Tower  
**Authority:** `SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md`  
**Purpose:** prevent SQL/API/UI or production changes from starting before the related business decision, source evidence, and acceptance criteria are ready.

## Gate Status

- `READY_NOW` - documentation and non-production technical preparation may proceed.
- `READY_AFTER_OWNER_DECISION` - blocked by a named decision.
- `READY_AFTER_DATA_FIX` - business rule is known but source extraction/linkage must be corrected first.
- `VALIDATION_ONLY` - may be investigated/read-only, but not published as a business conclusion.
- `DEFERRED` - outside current implementation scope.

## Workstream Gate Matrix

| Workstream | Current gate | What may proceed now | Blocking decision/evidence | Production implementation allowed? |
| --- | --- | --- | --- | --- |
| Native-ID extraction | READY_NOW | design and implement IDs/relation tables on a feature branch with regression tests | stable company ID and existing schema evidence | No, until reviewed/merged |
| SO-IO many-to-many extraction | READY_NOW | direct relation extraction and data reconciliation | relation table already validated | No, until reviewed/merged |
| Line-level fulfilment | READY_NOW | data contract, SQL design, fixtures for Stock/IO/MO/Mixed | representative samples and current dashboard reconciliation | No, until acceptance review |
| `MO_SUPPRESSED_BY_IO` | READY_NOW | classifier design and non-production tests | automation evidence already validated | No, until acceptance review |
| Cancellation/reset exposure | READY_NOW | read-only exception views and test data design | final owner sequence for corrective actions | Detection only; no write-back |
| Customer PO completeness | READY_NOW | reference/date completeness checks for 2026+ | attachment policy remains open | Reference/date rule only |
| IO production status | READY_AFTER_OWNER_DECISION | prototype exact product/UoM rule and retain `DATA_EXCEPTION` | `DEC-IO-001/002/003/006` | No final KPI |
| IO utilization status | READY_AFTER_OWNER_DECISION | relationship diagnostics and exception counts | `DEC-IO-004` allocation method | No final KPI |
| Parent-Child MO genealogy | READY_AFTER_OWNER_DECISION | document current limitation and candidate field design | `DEC-IO-005` | No deterministic rule |
| Receipt/PO correction | READY_AFTER_OWNER_DECISION | detection and exposure matrix | `DEC-PRC-001..004` | No workflow/write action |
| SO/Delivery correction | READY_AFTER_OWNER_DECISION | detection and exposure matrix | `DEC-SAL-001/002` | No workflow/write action |
| Log Note governance | READY_AFTER_OWNER_DECISION | schema/interface proposal and link-only display | `DEC-GOV-003/004/005` | No mandatory parsing/enforcement |
| Data Health ownership | READY_AFTER_OWNER_DECISION | worklist field contract | `DEC-GOV-001/002` | No SLA/escalation automation |
| Invoice traceability | READY_NOW | posted/draft/cancel/reversal traceability and SO linkage | Accounting rules for final labels | Traceability only |
| Payment/collection KPI | VALIDATION_ONLY | read-only residual/reconciliation diagnostics | `DEC-ACC-001..007` | No management KPI |
| Formal ticketing | DEFERRED | documentation only | future platform/owner decision | No |
| Dashboard write-back to Odoo | DEFERRED | none | future security/governance approval | No |
| AI-generated SOP updates | DEFERRED | proposal workflow documentation only | validated tickets and version governance | No autonomous publishing |

## Ready-Now Engineering Package

The following may be prepared on a feature branch without changing production behavior:

1. preserve native IDs and company ID;
2. extract SO-IO relation table directly;
3. create line-level fulfilment contract;
4. distinguish `MIXED_SOURCE`, `MO_SUPPRESSED_BY_IO`, and source data exceptions;
5. add read-only cancellation/reset exposure columns;
6. add invoice/residual/reconciliation traceability fields without final payment labels;
7. add fixtures and reconciliation reports;
8. keep existing frontend edits isolated and untouched.

## Mandatory Acceptance Evidence

Every implementation item must include:

- related SOP section and Decision ID;
- source model/field/relation;
- company and state filters;
- null, duplicate, cancel, partial, backorder, and mixed-source behavior;
- valid normal, valid exception, invalid, and missing-data cases;
- before/after reconciliation against Odoo samples;
- statement that no production write or configuration change occurred;
- rollback or disable path.

## Hard Stops

Do not:

- infer multi-IO allocation;
- publish `Paid` from helper fields or payment record alone;
- treat `DATA_EXCEPTION` as business failure;
- make Distribusi JO an Odoo state transition;
- cancel/reset documents through raw state write;
- implement ticketing, write-back, SLA, or autonomous SOP changes;
- merge unrelated frontend edits into the validation work.
