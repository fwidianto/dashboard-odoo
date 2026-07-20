# Process–SOP–Dashboard Validation and Approval Plan

**Status:** technical validation completed; stakeholder closure pending  
**Scope:** PT Nobi Putra Angkasa  
**Authority:** `docs/09_Odoo18_Validation/`

## 1. Objective

Maintain consistency between:

```text
Actual operating process
↕
SOP / Odoo Protocol
↕
Odoo source data and active automation
↕
Dashboard data contract and output
```

The technical discovery phase is complete. The current work is to close remaining owner decisions, approve SOP Draft v2, and convert validated rules into implementation acceptance criteria.

## 2. Completed Validation Outputs

The project has completed:

1. restored Odoo 18 schema and dataset identity validation;
2. model/field and direct-relation mapping;
3. transaction journey and SOP/dashboard gap review;
4. automation, Server Action, Studio, and scheduler mapping;
5. staging API smoke test;
6. controlled cancellation/reset runtime testing;
7. final read-only closure audit;
8. final SOP–System Alignment Matrix;
9. confirmed process-decision register;
10. validated Process Node Register, Rule Registry, Data Readiness Matrix, and MVP specification;
11. Data Health Rule Catalog v2 and Dashboard Implementation Backlog v2.

## 3. Confirmed Findings

- Distribusi JO is manual outside Odoo and may occur while SO is Draft.
- Customer Reference and Customer PO Date were complete for all 357 confirmed SOs in the 2026 closure scope.
- SO fulfilment is line-level and may roll up to `MIXED_SOURCE`.
- IO-linked SO may create an MO that auto-cancels as `MO_SUPPRESSED_BY_IO`.
- ROP→RFQ/PO is custom and user-triggered.
- PO Confirmed/Purchase is operational approval.
- Reset PO to Draft can leave Draft Vendor Bill, Receipt, and Stock Move active.
- Cancel Receipt does not automatically cancel PO; Cancel Delivery does not automatically cancel SO.
- final state must be checked after action errors.
- no open Receipt anomaly existed among 348 cancelled POs in the 2026 scope.
- IO Production/Utilization can be classified only with explicit `DATA_EXCEPTION` handling.
- Payment technical truth uses residual and reconciliation; final taxonomy remains Accounting-owned.

## 4. Remaining Stakeholder Decision Packs

### VP Operations / Governance

- Data Health Owner;
- review cadence and escalation;
- structured Log Note template and reason codes;
- approver matrix for Reset/Unlock and high-risk exceptions.

### Accounting

- fully/partially paid labels;
- payment registered but unreconciled;
- Credit Note/adjustment/write-off/compensation treatment;
- Down Payment allocation;
- overpayment;
- management payment date;
- reversal/cancel treatment.

### PPIC / Production / Operations

- IO requested quantity basis;
- product matching;
- UoM conversion/rounding;
- multi-IO SO allocation;
- over-production tolerance;
- persistent Parent–Child MO relation.

### Procurement / WHD

- Reset PO sequence with open Receipt;
- Cancel PO blocked/failed corrective path;
- partial Receipt/backorder disposition;
- replacement Receipt procedure;
- service inspection evidence.

### Marketing / WHD / Operations

- Cancel SO policy with done/open downstream;
- replacement Delivery procedure;
- Customer PO attachment/evidence policy;
- future Distribusi JO evidence design.

## 5. Decision Recording Template

```text
Decision ID:
Topic:
Current condition:
Decision:
Effective date:
Owner:
Approver:
Evidence required:
Exception allowed:
SOP impact:
Data-rule impact:
Dashboard impact:
Test cases:
Review date:
```

Every approved decision updates:

- Personal OS SOP Draft v2;
- SOP–System Alignment addendum if needed;
- Process Node Register;
- Rule Registry;
- Data Readiness Matrix;
- MVP specification;
- control-tower planning config;
- test and acceptance criteria.

## 6. Implementation Acceptance Pack

Before Codex implementation, each scoped task requires:

1. approved business rule;
2. model/field/direct relation path;
3. inclusion/exclusion logic;
4. stable company ID and date scope;
5. quantity/UoM basis;
6. canonical state mapping;
7. manual evidence/confidence behavior;
8. severity and owner;
9. positive, negative, partial, reset, cancel, done/posted, and exception tests;
10. aggregate and sampled-record reconciliation queries;
11. performance constraints;
12. rollback boundary.

## 7. Implementation Order

```text
Stakeholder decisions
→ SOP Draft v2 approval
→ freeze data contract and tests
→ native relation extraction
→ line-level source and stock/accounting truth
→ canonical status and exception views
→ server-side API
→ Control Tower UI
→ production-safe UAT
→ release
```

Detailed tasks are in `docs/09_Odoo18_Validation/DASHBOARD_IMPLEMENTATION_BACKLOG_V2.md`.

## 8. Validation to Continue During Implementation

Although discovery is closed, regression validation remains mandatory:

- aggregate counts match Odoo/source tables;
- native relation counts match relation tables;
- sampled SO/IO/PO journeys reconcile end-to-end;
- cancelled/reset records and downstream exposure remain searchable;
- mixed-source lines do not flatten;
- `MO_SUPPRESSED_BY_IO` is not treated as failure;
- `DATA_EXCEPTION` is retained;
- Payment remains gated until Accounting approval;
- manual/hybrid stages never show fabricated certainty;
- client performance avoids all-row hydration.

## 9. Current Exclusions

Until later approval, do not:

- change production Odoo configuration;
- infer multi-IO allocation;
- publish final Payment KPI;
- implement dashboard write-back;
- auto-close exceptions;
- build formal ticketing;
- automate SOP publication;
- hard-code SLA without owner approval.

## 10. Closure Criteria

The stakeholder gate is complete when:

- all decision packs have recorded outcomes or explicit deferred status;
- SOP Draft v2 is approved;
- Data Health Owner and cadence are assigned;
- Accounting and IO contracts are frozen enough for their respective scope;
- cancellation/replacement procedures are approved;
- implementation acceptance pack is signed off.

At that point, the project may create scoped Codex prompts beginning with native relation extraction—not frontend redesign.
