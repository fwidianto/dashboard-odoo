# Odoo 18 Validation Authority

Last updated: 2026-07-20

This folder contains the validated technical and SOP-alignment baseline for the Odoo 18 dashboard project.

## Current Authority

1. `SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md` - authoritative business/system alignment baseline.
2. `CONFIRMED_SOP_DECISIONS_2026-07-20.md` - concise confirmed decisions and exception vocabulary.
3. `FULL_RUNTIME_CANCELLATION_AND_OUTSTANDING_MATRIX.md` - controlled runtime evidence.
4. `FINAL_SOP_SYSTEM_CLOSURE_AUDIT.md` - final read-only anomaly and IO classification audit.
5. `DATA_HEALTH_RULE_CATALOG_V2.md` - implementable, provisional, manual-evidence, and blocked rules.
6. `DASHBOARD_IMPLEMENTATION_BACKLOG_V2.md` - ordered post-approval extraction, data-contract, SQL/API, UI, and release backlog.
7. `IMPLEMENTATION_READINESS_GATE_V2.md` - workstream-by-workstream authorization boundary.
8. `DECISION_TO_DATA_CONTRACT_MAP_V2.md` - exact effect of each open owner decision on the future data contract.

The alignment baseline supersedes earlier working assumptions wherever they conflict.

## Confirmed Documentation Changes

- `docs/04_Business_Rules/BUSINESS_FLOW.md` has been reconciled to the final Odoo 18 findings.
- Distribusi JO is outside Odoo and may occur while SO is Draft.
- SO fulfilment source is line-level and may be `MIXED_SOURCE`.
- IO-linked MO auto-cancellation is `MO_SUPPRESSED_BY_IO`.
- ROP -> RFQ/PO is a custom user-triggered Server Action.
- Reset to Draft is correction and may leave active downstream records.
- Payment truth requires residual and reconciliation evidence.

## Implementation Boundary

The current documents authorize:

- SOP Draft v2 review;
- data-health rule definition;
- extraction/data-contract design;
- acceptance criteria and test-case preparation;
- implementation sequencing;
- feature-branch preparation for native-ID, relation, and fixture work that does not change production behavior.

They do not yet authorize:

- production Odoo configuration changes;
- direct SQL/API/UI changes on the active production/dashboard branch;
- Payment KPI publication;
- inferred multi-IO SO allocation;
- write-back or automated issue closure;
- mixing unrelated frontend edits into validation work.

Implementation starts after VP Operations/process-owner approval, Accounting taxonomy approval, IO allocation decisions, and Data Health governance assignment. Detection-only and extraction-integrity work must still follow the readiness gate and acceptance criteria.

## Required Data-Contract Changes

1. preserve native Odoo IDs and direct relation paths;
2. extract SO-IO many-to-many directly;
3. classify fulfilment per SO line;
4. use stable company ID;
5. add stock picking/move/reservation/backorder evidence;
6. add invoice residual and reconciliation evidence;
7. expose cancellation/reset downstream exceptions;
8. keep administrative, operational, and derived statuses separate;
9. treat helper automation fields as secondary evidence;
10. retain `UNKNOWN`/`DATA_EXCEPTION` instead of inference.

## Next Gate

Use the Personal OS stakeholder review pack, decision register, and meeting-minutes template to close:

- Data Health owner and cadence;
- structured Log Note policy;
- Accounting payment/reconciliation taxonomy;
- IO product/UoM and multi-IO allocation;
- Parent-Child MO relation;
- Procurement/WHD and Sales/Operations cancellation policies.

Meanwhile, technical preparation is limited to the items marked `READY_NOW` in `IMPLEMENTATION_READINESS_GATE_V2.md` and must remain isolated on a feature branch with reconciliation tests.
