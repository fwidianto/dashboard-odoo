# Order Material Tracking Plan

**Date:** 2026-07-01
**Status:** Phase 2A.4 Sales Order Perspective implemented on the current page
**Current next step:** LAN/hotspot demo validation, VP prep, then Material Search planning
**Primary base:** Internal Order Rekap
**Goal:** Track material/procurement chain from either Internal Order or Sales Order perspective.

---

## 1. Agreed Page Direction

The current `Internal Order Rekap` continues to evolve into:

```text
Order Material Tracking
```

The page should stay order-based, but business-friendly.

It should still support two order perspectives:

```text
1. Internal Order Perspective
2. Sales Order Perspective
```

The intention is to answer:

```text
For this order, where are the related materials now?
Are they still at RKB, ROP, PO, receipt, production, stock, or delivery?
```

---

## 2. Perspective A - Internal Order

Flow:

```text
IO -> RKB IO -> ROP -> PO -> Receipt -> MO / Finished Goods -> Linked SO
```

This perspective is useful when:

```text
- IO exists before Sales Order
- IO is used to produce stock first
- We want to know what has been planned, purchased, received, produced, and later sold
```

Core questions:

```text
For this IO:
- What items were planned in RKB?
- Which items already have ROP?
- Which items already have PO?
- Which PO items have been received?
- Which items are already produced?
- Which Sales Orders are linked later?
```

---

## 3. Perspective B - Sales Order

Flow:

```text
SO -> approved SO-to-IO bridge -> linked IO material chain -> RKB -> ROP -> PO -> Receipt
```

This perspective is useful when:

```text
- Sales Order is the starting question
- VP or operations asks why an SO is delayed
- We need to identify whether the bottleneck is RKB, ROP, PO, receipt, production, or delivery
```

Core questions:

```text
For this SO:
- Which linked Internal Order(s) support it?
- What RKB / ROP / PO material chain is related through those Internal Orders?
- Which materials are still RKB only?
- Which materials already have ROP or PO?
- Which materials are partially or fully received?
- What needs review?
```

Important limitation:

```text
Sales Order Perspective is IO-level linked material chain context only.
It is not product-level allocation, COGS, accounting gross profit, margin, AR/payment, or final profitability.
```

---

## 4. Current Page Scope

This page is order-based.

Included:

```text
- Internal Order
- Sales Order status
- RKB
- ROP / Procurement Request
- Purchase Order
- Receipt status
- Production / finished-good context where available
```

Not included for now:

```text
- Full universal material search
- Supplier-wide procurement search
- Inventory valuation
- Accounting COGS
- AR/payment
- Final gross profit
```

---

## 5. UI Improvements Agreed

### 5.1 Use compact numbers

Cards should use compact number display.

Examples:

```text
1,250,000,000 -> 1.25B
845,000,000 -> 845M
12,500,000 -> 12.5M
```

Tables may still show full numbers or formatted IDR where useful.

---

### 5.2 Rename confusing labels

Use business-friendly labels.

| Current Label | New Label |
|---|---|
| Trackable RKB Actual | Product Item RKB |
| Non-Trackable RKB | Non-Product / Service Item RKB |
| Trackable Product | Product Item |
| Mixed UOM Count | Hide from main UI |
| Not Yet ROP Amount | Hide from main UI |
| RKB_ONLY | RKB Only |
| ROP_ONLY | ROP Only |
| PO_ONLY | PO Only |
| RKB_ROP_PO | RKB, ROP, and PO |

---

### 5.3 Hide confusing diagnostics from main cards

Hide these from visible dashboard cards:

```text
- Mixed UOM Count
- Not Yet ROP Amount
```

Reason:

```text
The intention is valid, but both are easy to misunderstand.
Mixed UOM is only a diagnostic flag.
Not Yet ROP Amount can be misleading because not every RKB item must become ROP.
```

If needed later, these can move to an Audit / Diagnostic mode.

---

### 5.4 Remove underscores from displayed values

Do not show raw enum labels in UI.

Bad:

```text
RKB_ROP_PO
NON_TRACKABLE_OTHERS
UNKNOWN_PRODUCT_CLASS
```

Good:

```text
RKB, ROP, and PO
Non-Product / Service Item
Unclassified Item
```

---

### 5.5 Cards should act as filters

Summary cards should remain clickable filters, similar to Sales Order dashboard.

Examples:

```text
Click Product Item RKB -> filter table to Product Item rows
Click Non-Product / Service Item RKB -> filter table to service/non-product rows
Click RKB Only -> filter table to RKB-only rows
Click ROP Only -> filter table to ROP-only rows
Click PO Only -> filter table to PO-only rows
```

---

## 6. Table Fields Agreed

The table should show document relationships clearly.

Important fields:

```text
- Internal Order Number
- Sales Order Number or Sales Order Status
- Product Name
- Product Item / Non-Product Service Item
- RKB Number
- RKB Qty
- RKB Amount
- ROP Number / Approval Number
- ROP Qty
- ROP Amount
- Related PO Number
- PO Qty
- PO Amount
- Received Qty
- Receipt Status
- Current Material Status
```

Purpose:

```text
Users should be able to see the chain per item without opening many systems.
```

---

## 7. Suggested Status Logic

Simple operational statuses:

```text
RKB Only
ROP Created
PO Created
Partially Received
Fully Received
Ready for Production
Production In Progress
Finished Good Available
Linked to SO
Delivered
Needs Review
```

Avoid overly technical statuses on the main screen.

---

## 8. Progress Checklist

### Phase 1 - Stabilize current page

- [x] Confirm `vw_internal_order_rekap_summary` loads
- [x] Confirm `vw_internal_order_rekap_lines` loads
- [x] Confirm current Internal Order Rekap API loads
- [x] Confirm selected IO example works, such as `426IO026`

### Phase 2 - UI label cleanup

- [x] Rename Trackable RKB Actual to Product Item RKB
- [x] Rename Non-Trackable RKB to Non-Product / Service Item RKB
- [x] Rename Trackable Product to Product Item
- [x] Remove underscores from visible labels
- [x] Hide Mixed UOM Count from main cards
- [x] Hide Not Yet ROP Amount from main cards

### Phase 3 - Card filtering

- [x] Make summary cards clickable
- [x] Add active filter indicator
- [x] Add clear filter button
- [x] Ensure behavior matches Sales Order dashboard card filters

### Phase 4 - Table relationship fields

- [x] Show Internal Order Number
- [x] Show actual linked Sales Order Number
- [x] Show Sales Order Status as Linked / Pre-SO
- [x] Show RKB Number
- [x] Show ROP Number / Approval Number
- [x] Show Related PO Number
- [x] Show Product Name
- [x] Show RKB / ROP / PO / Receipt quantities
- [x] Show current material status

Note: linked Sales Order display is IO-level bridge context only, not product allocation.

### Phase 5 - Interactive table controls

- [x] Add sortable table headers
- [x] Add combined filters
- [x] Add clear all filters
- [x] Add clear sort
- [x] Keep document references inline and comma-separated

### Phase 6 - Sales Order Perspective

- [x] Add Internal Order / Sales Order perspective toggle
- [x] Search by Sales Order number
- [x] Resolve linked Internal Orders through the approved SO-to-IO bridge
- [x] Return linked IO material/procurement chain rows from existing Internal Order Rekap lines
- [x] Show no-linked-IO empty state without inferring from MO
- [x] Keep labels as context, not allocation or profitability

### Phase 7 - VP readiness

- [x] Compact numbers on cards
- [x] Clear labels
- [x] No confusing diagnostics on main screen
- [x] No accounting profit claims
- [x] No raw technical enum labels
- [ ] Ready for VP review demo

---

## 9. Next Work

Suggested next prompt:

```text
Table readability and unified theme polish are postponed for now.
Sales Order Perspective is implemented as approved bridge context.
Keep Material Search as a future separate page.

Current next step: finish LAN/hotspot demo validation and VP prep, then plan Material Search separately.
```
