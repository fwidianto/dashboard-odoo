# Business Flow — Odoo 18 Manufacturing and Operations Analytics

**Status:** authoritative business-flow baseline aligned on 20 July 2026  
**Authority:** `docs/09_Odoo18_Validation/SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md`

This document defines business meaning for analytics and Control Tower design. It does not authorize production configuration changes.

---

## 1. Objective

The system must trace operational demand, production, procurement, inventory, delivery, invoicing, and payment while answering:

- where each order is in the process;
- which source fulfils each SO line;
- whether related documents are open, reserved, partial, done, posted, or cancelled;
- whether cancellation/reset leaves downstream exposure;
- whether IO production and utilization can be calculated safely;
- whether revenue, cost, invoice, and payment evidence are consistent.

---

## 2. Glossary

| Term | Meaning |
| --- | --- |
| SO | Sales Order; system root for customer demand and revenue. |
| JO | Factory/operational reference to customer work or SO-related production demand; not a separate entity competing with SO. |
| Distribusi JO | Manual operational handover outside Odoo; may occur while SO is still Draft. |
| IO | Internal Order; production for stock/future utilization stored in the Approvals structure. |
| MO | Manufacturing Order; recorded production execution. |
| RKB | PPIC material planning/comparison; does not directly start purchasing. |
| ROP / PEMBELIAN | Procurement request that can create RFQ/PO through a custom user-triggered Server Action. |
| Receipt | Incoming stock picking and moves related to PO. |
| Delivery | Outgoing picking and moves related to SO. |
| WIP / Pre-Production | Physical/internal holding area before recorded consumption. |
| Virtual Production | Odoo virtual location used for consumption/output accounting; not a physical warehouse. |

---

## 3. End-to-End Flow

```text
Customer PO / Confirmed Quotation
→ Distribusi JO outside Odoo when operationally needed
→ Sales Order
→ VP Operations Confirm SO
→ Fulfilment per line: Stock / Internal Order / New MO / Mixed
→ RKB when required
→ ROP / PEMBELIAN
→ user-triggered RFQ / PO creation
→ PO Confirmed
→ Receipt and external inspection
→ Bon: Stock → Pre-Production/WIP
→ Consumption: Pre-Production/WIP → Virtual Production
→ Output: Virtual Production → Post-Production
→ WHD transfer: Post-Production → Stock
→ Delivery
→ Invoice
→ Payment / Reconciliation
```

Important:

- Distribusi JO is not an Odoo stage and must not be inferred from SO state.
- SO may remain Draft while waiting for IO production, technical clarification, or management considerations.
- Production remains Hybrid Odoo–Manual.
- Payment status requires accounting residual and reconciliation evidence.

---

## 4. Sales Order

### 4.1 Customer evidence

For confirmed SOs from 2026 onward, Customer Reference and Customer PO Date are mandatory controls. The closure audit found both fields complete for all 357 confirmed SOs in scope.

### 4.2 Approval

VP Operations confirmation in Odoo is the official system approval. The confirmed `sale` state is the operational system evidence; physical signatures may remain external.

### 4.3 Fulfilment source

Source is classified per SO line:

| Source | Meaning |
| --- | --- |
| `FROM_STOCK` | fulfilled from available stock without a new production requirement. |
| `FROM_INTERNAL_ORDER` | fulfilled using stock produced under one or more IOs. |
| `MAKE_TO_ORDER` | requires a new MO linked to customer demand. |
| `MIXED_SOURCE` | the SO contains lines from more than one source. |
| `SOURCE_DATA_EXCEPTION` | source cannot be proven safely. |

Do not flatten mixed SOs to an IO-first header rule.

### 4.4 Internal Order suppression behavior

An SO linked to IO may still create a new MO that is immediately cancelled by active automation. This is valid `MO_SUPPRESSED_BY_IO`, not ordinary production cancellation or failure.

### 4.5 Cancellation

Cancel is successful only when final SO state becomes `cancel`. Done/posted downstream records remain historical evidence; open downstream documents require explicit resolution or approved exception.

---

## 5. Internal Order

IO is represented in the approval module, including MANUFACTURE-category approval lines. Use native relation IDs and relation tables as the source of truth.

The direct SO–IO relationship is many-to-many. One SO may reference multiple IOs and one IO may be used by multiple SOs. The relation table must be extracted directly; display/set text is secondary evidence.

Administrative approval status is not reliable operational progress. Production and utilization are separate derived dimensions.

### 5.1 Proposed Production Status

- `NOT_STARTED`;
- `IN_PROGRESS`;
- `PARTIALLY_PRODUCED`;
- `FULLY_PRODUCED`;
- `OVER_PRODUCED`;
- `CANCELLED`;
- `DATA_EXCEPTION`.

### 5.2 Proposed Utilization Status

- `NOT_UTILIZED`;
- `PARTIALLY_UTILIZED`;
- `FULLY_UTILIZED`;
- `OVER_UTILIZED`;
- `DATA_EXCEPTION`.

Use `DATA_EXCEPTION` for incompatible/mixed product or UoM, missing direct relations, contradictory lifecycle evidence, or multi-IO SO quantity without approved allocation.

---

## 6. Manufacturing

MO may originate from:

1. customer/JO production demand;
2. Internal Order;
3. valid special processes such as conversion or stock production.

Production movement:

```text
Bon: Stock → Pre-Production/WIP
Consumption: Pre-Production/WIP → Virtual Production
Output: Virtual Production → Post-Production
WHD transfer: Post-Production → Stock
```

`KRW/FG` and `FF5/FG` are legacy Scala locations and are not used in the current flow.

Odoo MO and stock records prove recorded execution, but do not alone prove every shop-floor, QC, signature, or external-document step.

Parent–Child MO business dependency exists, but exact genealogy must not be published until a trusted persistent relation is available.

---

## 7. RKB, ROP, and Purchase Order

### 7.1 RKB

RKB is planning/comparison. It does not directly trigger purchasing.

### 7.2 ROP / PEMBELIAN

ROP is the procurement request. RFQ/PO creation is performed through a custom, user-triggered Server Action, not a fully automatic standard Odoo transition.

### 7.3 PO approval

PO state Confirmed/Purchase is accepted as official operational approval. Approver/sign helper fields are supporting metadata.

### 7.4 Reset to Draft

Reset to Draft is correction, not cancellation. Runtime evidence proved a PO can change `purchase → draft` while Draft Vendor Bill, Receipt, and Stock Moves remain active and linked.

Therefore analytics must expose `RESET_TO_DRAFT_WITH_OPEN_DOWNSTREAM` rather than assuming cascade cleanup.

### 7.5 PO cancellation

Cancel PO may be blocked or fail when downstream is active. A cancelled PO with an open Receipt is a Data Health anomaly. No such case was found among 348 cancelled POs in the audited 2026 scope.

---

## 8. Receipt, Inventory, and Delivery

WHD validates Receipt after physical/documentary inspection. The Odoo Quality module is not part of the current operational flow.

Service Receipt may require BAP/BAST or contract evidence.

Cancel Receipt can cancel related stock movements but does not automatically cancel the PO.

WHD validates Delivery after customer receipt/evidence. Cancel Delivery does not automatically cancel the SO.

DO Manual/Internal Transfer is an exception and must be reconciled against normal SO/MO/Delivery flow.

---

## 9. Invoice and Payment

Invoice and accounting evidence must use native accounting relationships.

A Draft Invoice cancellation can change state even when the runtime/API response returns an error. Final state must be checked before retrying; classify as `ACTION_APPLIED_WITH_RPC_ERROR` where applicable.

Payment technical truth uses:

- posted invoice;
- amount residual;
- receivable journal items;
- partial/full reconciliation;
- payment entries;
- reversal, Credit Note, write-off, compensation, or adjustment evidence.

Sales helper/copied paid fields are not the accounting source of truth.

Final business labels, DP allocation, overpayment, adjustment treatment, and management payment date remain pending Accounting approval.

---

## 10. Correction and Cancellation Vocabulary

| Code | Meaning |
| --- | --- |
| `RESET_TO_DRAFT_WITH_OPEN_DOWNSTREAM` | parent returned to Draft while operational/accounting downstream remains active. |
| `CANCEL_BLOCKED_OR_FAILED` | action returned an error and target state did not change. |
| `ACTION_APPLIED_WITH_RPC_ERROR` | action returned an error but target state changed. |
| `CANCELED_PARENT_WITH_OPEN_DOWNSTREAM` | cancelled/reset parent with open child records. |
| `CANCELED_PARENT_WITH_DONE_DOWNSTREAM` | cancelled/reset parent with completed historical evidence. |
| `CANCELED_PARENT_WITH_RESERVED_STOCK` | cancelled/reset parent with reserved/assigned movement. |
| `CANCELED_PARENT_WITH_PARTIAL_BACKORDER` | cancelled/reset parent with partial quantity or open backorder. |
| `CANCELLED_PO_WITH_OPEN_RECEIPT` | cancelled PO with incoming Receipt not Cancel/Done. |
| `CANCELLED_SO_WITH_ACTIVE_DOWNSTREAM` | cancelled SO with active MO, Delivery, PO, Invoice, or Backorder. |
| `AUTOMATION_EFFECT_UNCONFIRMED` | trigger shape matches but exact execution/effect is not proven. |

---

## 11. Data Contract Principles

1. Preserve native Odoo IDs alongside display values.
2. Use direct foreign keys and relation tables before text matching.
3. Extract SO–IO many-to-many directly.
4. Classify fulfilment per SO line.
5. Use stable company ID, not display name.
6. Keep administrative, operational, and derived statuses separate.
7. Keep helper automation fields secondary to transaction truth.
8. Expose stock picking/move/backorder evidence.
9. Expose invoice residual and reconciliation before Payment KPIs.
10. Return `UNKNOWN`/`DATA_EXCEPTION` rather than infer unresolved allocation.
11. Keep cancelled parents visible when downstream exposure exists.
12. Link rule version to SOP version and effective date.

---

## 12. Dashboard Hierarchy

1. **Sales Order Control** — demand, line source, commitment, delivery/invoice exposure.
2. **Internal Order Control** — requested, produced, utilized, remaining, and data exceptions.
3. **Manufacturing Control** — MO lifecycle, components, WIP, output, and site movement.
4. **Procurement and Receipt Control** — ROP, PO, Receipt, backorder, and quantity mismatch.
5. **Delivery Control** — readiness, partial/backorder, evidence, and cancellation exposure.
6. **Accounting Control** — invoice, residual, reconciliation, and payment taxonomy after approval.
7. **Exception Worklist** — severity, owner, age, evidence, SOP reference, and resolution status.
8. **Profitability Analytics** — estimator, RKB, actual production, procurement, and final SO cost/revenue.

Implementation must begin with extraction and data-contract integrity before UI redesign.
