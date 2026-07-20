# Rule Registry v2 — SOP and Dashboard Contract

**Status:** Phase 0 validated baseline  
**Scope:** PT Nobi Putra Angkasa  
**Authority:** `docs/09_Odoo18_Validation/DATA_HEALTH_RULE_CATALOG_V2.md`

This registry maps business rules to Control Tower nodes. Detailed technical readiness and exclusions remain in the validated catalog.

## 1. Rule Status

- `IMPLEMENTABLE`: relation and rule are sufficiently proven for coding after approval gate.
- `PROVISIONAL`: business allocation, threshold, UoM, or taxonomy is still pending.
- `MANUAL_EVIDENCE`: current Odoo state cannot prove the condition alone.
- `RUNTIME_OBSERVABILITY`: requires action/result logging rather than static transaction data.
- `BLOCKED`: trusted relation or owner decision is missing.
- `DEFERRED`: future workflow/ticketing scope.

## 2. Registered Rules

| Rule ID | Node | Business rule / output | Main source | Severity | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `DH2-SALES-001` | CT-00/01 | Confirmed SO from 2026 requires Customer Reference and Customer PO Date | `sale_order` | High | Marketing | IMPLEMENTABLE |
| `DIST-MANUAL-001` | CT-02 | Distribusi JO is outside Odoo and may occur while SO is Draft | external evidence | Review | Marketing / Operations | MANUAL_EVIDENCE |
| `DH2-SALES-002` | CT-03 | multiple line sources → `MIXED_SOURCE` | SO lines, SO–IO relation, MO, stock | Info/High | Marketing / PPIC | IMPLEMENTABLE after line contract |
| `DH2-SALES-003` | CT-03/05 | IO-linked SO MO auto-cancel → `MO_SUPPRESSED_BY_IO` | SO–IO relation, MO, automation condition | Info | PPIC | IMPLEMENTABLE |
| `DH2-SALES-004` | CT-01/X1 | Cancelled SO with active downstream | SO, MO, Delivery, PO, Invoice, Backorder | High/Critical | Multi-owner | IMPLEMENTABLE |
| `SO-QTY-001` | CT-01/X1 | SO quantity change requires downstream reconciliation | SO lines, MO, Delivery | High | Marketing / PPIC / WHD | PROVISIONAL exclusions |
| `LOG-001` | CT-X1 | Reset/Unlock/material correction/exceptional Cancel requires structured Log Note | chatter + action evidence | Medium/High | Process owner / approver | MANUAL_EVIDENCE / governance pending |
| `DH2-IO-001` | CT-04 | derived IO Production Status | IO lines, IO–MO relation, MO qty | Medium/High | PPIC | PROVISIONAL |
| `DH2-IO-002` | CT-04 | derived IO Utilization Status | SO–IO relation, SO lines, produced qty | Medium/High | PPIC / Operations | PROVISIONAL |
| `DH2-IO-003` | CT-04 | unsafe production calculation → `IO_PRODUCTION_DATA_EXCEPTION` | product/UoM/lifecycle/linkage | Medium/High | PPIC / Data owner | IMPLEMENTABLE safety class |
| `DH2-IO-004` | CT-04 | unsafe utilization allocation → `IO_UTILIZATION_DATA_EXCEPTION` | multi-IO SO/product/UoM/linkage | Medium/High | PPIC / Operations | IMPLEMENTABLE safety class |
| `MO-PLAN-001` | CT-05 | MO requires valid source/schedule/site/responsible and reviewed components | MO, moves, operation type | High | PPIC | PROVISIONAL detailed mandatory contract |
| `DH2-MRP-001` | CT-05/09/X1 | Cancelled MO with active/reserved material or WIP | MO, raw moves, picking, location | High | PPIC / WHD | IMPLEMENTABLE after relation contract |
| `DH2-MRP-002` | CT-10 | Done MO without required FG completion to Stock | MO, finished moves, transfer | High | PPIC / WHD | IMPLEMENTABLE |
| `DH2-MRP-003` | CT-09/10 | WIP without owner, active plan, return, consumption, or disposition | stock/WIP/MO/evidence | Medium/High | PPIC / WHD | CONTEXTUAL |
| `DH2-MRP-004` | CT-10 | Parent Done before Child | Parent–Child relation | High | PPIC | BLOCKED relation |
| `PROD-MANUAL-001` | CT-10 | Odoo Done alone does not prove all physical/QC completion | MO + external production/QC evidence | High | PPIC / Production | MANUAL_EVIDENCE |
| `ROP-001` | CT-06 | approved ROP without RFQ/PO after threshold | approval header/line, PO line | High | Procurement | PROVISIONAL threshold/header states |
| `ROP-002` | CT-06/07 | cancelled/refused ROP with active RFQ/PO | approval header, PO/line | High | Procurement | PROVISIONAL exact states/action |
| `PO-APPROVAL-001` | CT-07 | PO Confirmed/Purchase is operational approval | PO state | High | Procurement / VP Operations | IMPLEMENTABLE |
| `DH2-PROC-001` | CT-07/X1 | chatter-proven Reset PO with open Receipt/Move/Bill | PO, chatter state tracking, picking/move/bill | High | Procurement / WHD / Accounting | IMPLEMENTABLE |
| `DH2-PROC-002` | CT-07/08/X1 | Cancelled PO with open Receipt | PO, incoming picking/backorder | High/Critical | Procurement / WHD | IMPLEMENTABLE |
| `DH2-PROC-003` | CT-06/07 | approved ROP without generated RFQ/PO | approval/PO relation | High | Procurement | PROVISIONAL |
| `DH2-PROC-004` | CT-06/07/X1 | cancelled/refused ROP with active RFQ/PO | approval/PO relation | High | Procurement | PROVISIONAL |
| `DH2-INV-001` | CT-07/08 | PO ordered quantity differs from active Receipt demand | PO line, stock move | Critical/High | Procurement / WHD | PROVISIONAL UoM/exclusions |
| `RCV-EVID-001` | CT-08 | Receipt requires physical/service inspection evidence | picking + attachment/reference/Log Note/BAP | High | WHD / Requester | MANUAL_EVIDENCE |
| `DH2-INV-002` | CT-08/X1 | Receipt Cancelled while PO remains open; requires disposition | Receipt + PO | Review/Medium | Procurement / WHD | IMPLEMENTABLE |
| `LEGACY-LOC-001` | CT-09/10 | no new operational movement should use KRW/FG or FF5/FG | location/move | High | WHD / Data Health Owner | PROVISIONAL cut-off |
| `BON-001` | CT-09/10 | Bon is not consumption | internal move vs raw-material consumption | High | PPIC / WHD | IMPLEMENTABLE data-contract rule |
| `DEL-PARTIAL-001` | CT-11 | partial delivery requires Backorder or approved decision | Delivery/moves/backorder | High | WHD | IMPLEMENTABLE after exclusions |
| `DEL-EVID-001` | CT-11 | Delivery Done requires actual customer receipt evidence | Delivery + signed/manual evidence | Critical/High | WHD | MANUAL_EVIDENCE |
| `DO-MANUAL-001` | CT-11 | DO Manual/Internal Transfer must reconcile to normal Delivery | internal transfer, SO, Delivery | Critical/High | WHD | PROVISIONAL mapping |
| `DH2-DEL-001` | CT-11/X1 | Delivery Cancelled while SO remains open; requires disposition | Delivery + SO | Medium/High | WHD / Marketing | IMPLEMENTABLE |
| `DH2-CORR-001` | CT-X1 | error + unchanged final state → `CANCEL_BLOCKED_OR_FAILED` | action/result log + state | High | Process/technical owner | RUNTIME_OBSERVABILITY |
| `DH2-CORR-002` | CT-X1 | error + changed final state → `ACTION_APPLIED_WITH_RPC_ERROR` | action/result log + state | High technical | Process/technical owner | RUNTIME_OBSERVABILITY |
| `DH2-CORR-003` | CT-X1 | Cancel/Reset parent with Done/Posted downstream | direct relations/state | Review/High | Multi-owner | IMPLEMENTABLE |
| `DH2-CORR-004` | CT-X1 | Cancel/Reset parent with Reserved/Partial/Backorder downstream | relations/state/quantity | High/Critical | Multi-owner | IMPLEMENTABLE |
| `INV-PROGRESS-001` | CT-12 | invoice progress must match contract/milestone and SO invoiceable evidence | SO/invoice lines | Medium/High | Accounting | PROVISIONAL business contract |
| `DH2-ACC-001` | CT-13 | paid label conflicts with residual/reconciliation | invoice, AR lines, reconciliation | Critical/High | Accounting | PROVISIONAL taxonomy |
| `DH2-ACC-002` | CT-13 | payment posted but invoice not reconciled | payment, invoice residual, reconciliation | Medium/High | Accounting | PROVISIONAL label |
| `DH2-ACC-003` | CT-13 | settlement by Credit Note/adjustment/write-off/compensation | reconciliation/journal/reversal | Review | Accounting | PROVISIONAL journal list/label |
| `DH2-ACC-004` | CT-12/13 | Sales helper paid field differs from Accounting truth | Sales helper vs residual/reconciliation | High reporting | Accounting / Data owner | IMPLEMENTABLE after truth view |
| `TICKET-001` | CT-X2 | Critical/High exception has centralized issue lifecycle | future issue store | High | Data Health Owner | DEFERRED |

## 3. Rule Execution Output

Every implemented rule should return:

```text
rule_id
rule_version
sop_version
root_model
root_id
related_model
related_id
node_id
native_status
canonical_status
coverage_mode
is_exception
severity
confidence
status_reason
process_owner
evidence_required
suggested_review
detected_at
source_updated_at
```

Display document numbers are presentation fields; native IDs remain the join keys.

Rules marked `MANUAL_EVIDENCE`, `PROVISIONAL`, `RUNTIME_OBSERVABILITY`, or `BLOCKED` must not produce an unqualified confirmed-error label without human review.

## 4. Required Test Classes

- `VALID_NORMAL`;
- `INVALID_EXCEPTION`;
- `VALID_ACCEPTED_EXCEPTION`;
- `DRAFT_OR_RESET`;
- `CANCELLED`;
- `PARTIAL_BACKORDER`;
- `RESERVED_ASSIGNED`;
- `DONE_POSTED_HISTORY`;
- `MISSING_DATA`;
- `MANUAL_EVIDENCE`;
- `SOURCE_CONFLICT`;
- `MULTI_RELATION`;
- `BOUNDARY_DATE`.

## 5. Change Control

```text
Mismatch / false positive / new scenario
→ review Odoo data, direct relations, physical/manual evidence, and SOP
→ decide whether data, rule, or SOP changes
→ process-owner approval
→ update rule_version and/or sop_version
→ regression and reconciliation tests
→ publish
```

Do not weaken a rule only because it returns many exceptions. First determine whether the cause is data quality, relation extraction, business allocation, accepted exception, or an incorrect rule.
