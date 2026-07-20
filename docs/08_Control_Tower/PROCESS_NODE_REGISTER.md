# Process Node Register — Odoo Protocol Control Tower

**Status:** Phase 0 Draft v3 — aligned with final Odoo 18 validation  
**Business authority:** `docs/09_Odoo18_Validation/SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md`  
**Technical implementation:** Dashboard Odoo

## 1. Purpose

This register defines business-facing process nodes for record counts, states, aging, anomalies, owner, evidence, and SOP references.

Nodes represent traceable process concepts. A manual milestone is not forced into an Odoo sequence when no reliable Odoo event exists.

## 2. Root Flow Instances

1. **Customer flow root:** `sale_order.id`.
2. **Internal production root:** `approval_request.id` for Internal Order.
3. **Procurement root:** approval/ROP and related `purchase_order.id`.
4. **Accounting root:** `account_move.id` and reconciliation graph.

Customer PO / confirmed quotation is the business start. Sales Order remains the technical dashboard root.

## 3. Canonical Process Nodes

| Node ID | Process stage | Type | Primary owner | Entry | Exit / completion | Main evidence | Coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CT-00` | Customer PO / Confirmed Quotation | Business evidence | Marketing | customer commitment exists | SO created with required reference/date | Customer Reference, Customer PO Date, attachment/manual evidence | Odoo reference + manual evidence |
| `CT-01` | Sales Order & Approval | Document / Control | Marketing; VP Operations | SO created | confirmed, cancelled, or retained Draft with reason | `sale_order`, lines, Log Note | Odoo |
| `CT-02` | Distribusi JO / Operational Handover | Manual communication milestone | Marketing / Operations | business information available | relevant internal parties receive handover | external communication/manual evidence | Manual outside Odoo |
| `CT-03` | Fulfilment Classification | Derived decision | Marketing / PPIC | SO lines exist and source evidence is available | each line classified Stock/IO/New MO or Data Exception | SO line, SO–IO relation, MO, stock evidence | Partial / Derived |
| `CT-04` | Internal Order | Document / Process | PPIC | IO created for stock/future demand | production and utilization status derived | approval request/line, IO–MO and SO–IO relations | Odoo + Derived |
| `CT-05` | Manufacturing Planning | Document / Process | PPIC | production need/MO exists | MO confirmed/cancelled and material plan known | `mrp_production`, components, schedule | Odoo / Hybrid |
| `CT-06` | RKB / ROP Purchase Request | Planning / Approval | PPIC / Requester | material/service need recorded | ROP approved/refused/cancelled; RFQ action outcome reviewed | approval request/line | Custom / Partial |
| `CT-07` | RFQ / Purchase Order | Document / Approval | Procurement | RFQ/PO created by user-triggered action/manual procurement | PO confirmed/cancelled/closed and downstream exposure known | PO/lines, ROP links, Log Note | Odoo / Custom |
| `CT-08` | Receipt & Inspection | Document / Control | WHD / requester | incoming picking exists | Done, Cancel, Return, Backorder, or approved exception | picking/move/move line + external inspection evidence | Odoo + Manual evidence |
| `CT-09` | Material Transfer / Pre-Production | Process | PPIC / WHD | material is issued from Stock | material available in Pre-Production/WIP or corrective disposition complete | internal picking/moves | Odoo / Hybrid |
| `CT-10` | Production / Finish Good | Hybrid process | PPIC / Production / WHD | production execution starts | consumption/output recorded and FG transferred to Stock | MO, component/finished moves, external production evidence | Hybrid |
| `CT-11` | Delivery | Document / Process | WHD / Marketing | outgoing picking exists | Done, Cancel, Backorder, Return, or approved exception | delivery picking/moves + signed evidence | Odoo + Manual evidence |
| `CT-12` | Invoice | Document / Process | Accounting | invoiceable condition exists | Posted, Cancelled/Reversed, or exception explained | invoice/move lines, SO linkage | Odoo |
| `CT-13` | Payment / Collection | Accounting process | Accounting | posted receivable exists | residual/reconciliation/settlement basis explained | invoice residual, receivable lines, payment and reconciliation | Investigation pending taxonomy |
| `CT-X1` | Correction / Reset / Cancellation Exposure | Cross-cutting control | respective process owner | Reset/Cancel/action attempt occurs | final state and all downstream exposure verified | chatter, states, relations, Log Note, runtime evidence if available | Partial / Manual + Odoo |
| `CT-X2` | Exception Worklist | Cross-cutting control | Data Health Owner | a rule detects review condition | Closed, Accepted Exception, or False Positive with verifier | rule output + owner evidence | Future Control Tower |

## 4. Critical Sequencing Clarifications

### 4.1 Distribusi JO is not a mandatory Odoo sequence node

Distribusi JO:

- occurs outside Odoo;
- may happen while SO is Draft;
- may precede or follow SO Confirm depending on operational need;
- must not be inferred from SO state, chatter, followers, activities, or MO state.

Therefore `CT-02` is displayed as a manual milestone/coverage indicator, not a required database transition between `CT-01` and `CT-03`.

### 4.2 Fulfilment is line-level

Each SO line is classified separately:

- `FROM_STOCK`;
- `FROM_INTERNAL_ORDER`;
- `MAKE_TO_ORDER`;
- `SOURCE_DATA_EXCEPTION`.

SO header becomes `MIXED_SOURCE` when multiple valid sources coexist.

### 4.3 IO-based SO and MO suppression

An IO-linked SO may create a new MO that is immediately cancelled by automation. The node output is `MO_SUPPRESSED_BY_IO`; it is not a failed production node.

### 4.4 Reset to Draft and Cancel are cross-cutting controls

Reset/Cancel is not treated as a simple terminal state. `CT-X1` checks:

- final root state;
- open/reserved/partial/backorder downstream;
- Done/Posted historical evidence;
- deleted/unlinked relationships;
- required Log Note and owner closure.

## 5. Valid Flow Patterns

### 5.1 Stock fulfilment

```text
CT-00 → CT-01
CT-02 may occur independently
CT-03 = FROM_STOCK
→ CT-11 → CT-12 → CT-13
```

### 5.2 Internal Order production before customer demand

```text
CT-04 IO
→ CT-05 MO
→ CT-09 Material Transfer
→ CT-10 Production / FG to Stock
```

Later customer flow:

```text
CT-00 → CT-01
CT-02 may occur independently
CT-03 = FROM_INTERNAL_ORDER
→ optional MO_SUPPRESSED_BY_IO evidence
→ CT-11 → CT-12 → CT-13
```

Do not represent a cancelled suppressed SO-based MO as new required production.

### 5.3 Make to Order

```text
CT-00 → CT-01
CT-02 may occur independently
CT-03 = MAKE_TO_ORDER
→ CT-05
→ CT-06 when material/service purchase is required
→ CT-07 → CT-08
→ CT-09 → CT-10
→ CT-11 → CT-12 → CT-13
```

### 5.4 Mixed source

One SO may branch across Stock, IO, and new MO by line. Node summaries must preserve line detail and show `MIXED_SOURCE`.

## 6. Status Dimensions

Every node should preserve separate dimensions:

- **Native Odoo status**;
- **Canonical operational status**;
- **Manual/evidence status**;
- **Coverage mode:** Odoo, Hybrid, Manual, Derived;
- **Data confidence:** High, Medium, Low, Manual;
- **Exception overlays**;
- **Rule and SOP version**.

Odoo Done does not automatically prove every physical/QC/manual activity is complete.

## 7. Click Contract

Clicking a node should show:

1. active and total record count;
2. native and canonical state;
3. line/source detail where relevant;
4. aging and commitment date;
5. blocked, partial, reserved, backorder, Done/Posted, and Cancel exposure;
6. upstream/downstream native IDs and business references;
7. evidence and confidence;
8. process owner/approver;
9. Rule ID and SOP section;
10. source timestamp and rule version.

## 8. Confirmed Decisions Used

- Customer PO/confirmed quotation is the business start.
- Sales Order is the technical customer root.
- Customer Reference and PO Date are mandatory controls for confirmed SOs from 2026.
- Distribusi JO is manual outside Odoo and may occur while SO is Draft.
- source is line-level; header can be `MIXED_SOURCE`.
- IO-linked MO cancellation may be valid suppression.
- ROP→RFQ/PO is custom and user-triggered.
- PO Confirmed is operational approval.
- Reset to Draft is correction and may leave downstream active.
- Cancel success is determined from final state.
- native IDs and relation tables are primary.
- production is Hybrid.
- payment needs residual/reconciliation and Accounting taxonomy.

## 9. Open Decisions

1. Accounting payment labels and settlement treatment.
2. IO product/UoM matching and multi-IO allocation.
3. persistent Parent–Child MO relation.
4. Data Health Owner, review cadence, and escalation.
5. structured Log Note reason codes and enforcement.
6. manual evidence design for Distribusi JO and physical/QC activities.

These open decisions do not change the confirmed node sequencing rules above.
