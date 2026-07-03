# Order Material Tracking Review Signals

Last updated: 2026-07-03

## Purpose

Review Signals add a compact frontend review layer to the Order Material Tracking dashboard. The goal is to group currently loaded material lines into business-readable follow-up buckets without changing SQL, backend calculations, or the underlying data model.

Important business clarification:

The original Phase 1 rule mapping was too strict for several material/procurement cases. The rules below are the revised target for the next implementation pass. See the durable business rule source here:

```text
docs/04_Business_Rules/ORDER_MATERIAL_TRACKING_BUSINESS_RULES.md
```

## Page Scope

- Dashboard page: `/dashboard/internal-order-rekap`
- Frontend files:
  - `src/static/dashboard/internal-order-rekap.html`
  - `src/static/dashboard/internal-order-rekap.js`
  - `src/static/dashboard/internal-order-rekap.css`
- Phase 1 is derived in the browser from fields already returned by the existing dashboard API.

## Fields Used

- `materialStatusMeta(row)`
- `row.material_chain_source`
- `row.product_presence_status`
- `row.po_without_rop_flag`
- `row.rop_without_po_flag`
- `row.mixed_uom_flag`
- `row.product_trackability_class`
- `row.is_trackable_product`
- `row.rkb_actual_qty`
- `row.rkb_actual_subtotal`
- `row.rop_qty`
- `row.rop_subtotal`
- `row.po_qty`
- `row.po_subtotal`
- `row.po_received_qty`
- `row.po_invoiced_qty`
- `row.excess_rop_amount`
- `row.po_excess_amount`
- `row.has_sales_order_link`

## Business Rule Corrections

### RKB vs ROP

ROP does not need to exactly follow RKB.

Do not mark a row as Needs Review only because:

- ROP quantity differs from RKB quantity.
- ROP amount differs from RKB amount.
- RKB exists but ROP does not exist yet.

RKB-only rows are normally Watchlist/context for gross profit or kontribusi comparison.

### ROP vs PO

PO should follow ROP quantity, but may be higher than ROP because of Minimum Order Quantity (MOQ) or supplier packaging rules.

| Condition | Recommended Signal | Recommended Note |
| --- | --- | --- |
| PO Qty < ROP Qty | Supplier Follow-up | PO Qty is less than ROP; follow up with Purchasing. |
| PO Qty = ROP Qty | Healthy or Watchlist depending receipt status | PO Qty follows ROP. |
| PO Qty > ROP Qty | Watchlist / Notice | PO Qty is above ROP, possibly due to MOQ or supplier packaging. |

### PO Without ROP

PO without ROP is not automatically an error.

Possible normal reasons:

- Discount line.
- Service / jasa line.
- Additional charge.
- Manual or urgent purchase.
- Non-RKB / non-ROP item that still belongs to the transaction.

Recommended note:

```text
PO exists without ROP; may be service, discount, manual purchase, or non-RKB item.
```

### From Stock

From Stock should not automatically be Healthy, because the dashboard does not yet have reliable available-stock correlation per project/order.

Recommended signal:

```text
Watchlist
```

Recommended note:

```text
Planned from stock; stock availability is not yet project-correlated.
```

### Mixed UoM

Mixed UoM should be a prevention notice, not Needs Review by default.

Recommended note:

```text
UoM inconsistency detected; company rule expects same UoM.
```

## Product Classification Direction

Product classification should be separated from Review Signal severity.

Recommended business classes:

| Class | Meaning | Review Treatment |
| --- | --- | --- |
| Product Item | Real material/product item that can be followed through RKB, ROP, PO, and Receipt. | Eligible for material-readiness and supplier follow-up rules. |
| Non-Product / Service Item | Service or operational cost item, often represented in RKB as an Others product line. | Not a material error. Use operational/context note if needed. |
| Transactional Line | Discount, additional charge, admin charge, rounding, price adjustment, or similar transaction adjustment. | Exclude from material readiness exceptions. |
| Unknown / Unclassified | Row cannot yet be confidently classified. | Watchlist only; check only if it affects material review. |

Important:

- Unknown product classification should not automatically be Needs Review.
- Discount/additional-charge style rows should be classified as Transactional Line when possible.
- Non-product/service rows are not automatically errors.

## Revised Review Signal Target

Rules should be evaluated in priority order, but the priority is now less aggressive than the original implementation.

| Priority | Review Signal | Condition | Review Note |
|---:|---|---|---|
| 1 | Supplier Follow-up | `rop_without_po_flag` is true | ROP exists but PO is not created yet; follow up with Purchasing. |
| 2 | Supplier Follow-up | PO Qty is lower than ROP Qty | PO Qty is less than ROP; follow up with Purchasing. |
| 3 | Supplier Follow-up | PO exists and received quantity is zero | PO created but material has not been received. |
| 4 | Supplier Follow-up | PO is partially received | PO partially received; supplier follow-up may be needed. |
| 5 | Operational Follow-up | `has_sales_order_link` is false | Pre-SO Internal Order; monitor until sales order linkage is available. |
| 6 | Watchlist | `material_chain_source === "FROM_STOCK"` | Planned from stock; stock availability is not yet project-correlated. |
| 7 | Watchlist | PO Qty is above ROP Qty | PO Qty is above ROP, possibly due to MOQ or supplier packaging. |
| 8 | Watchlist | `po_without_rop_flag` is true | PO exists without ROP; may be service, discount, manual purchase, or non-RKB item. |
| 9 | Watchlist | `mixed_uom_flag` is true | UoM inconsistency detected; company rule expects same UoM. |
| 10 | Watchlist | RKB only | RKB only; monitor for contribution comparison and later procurement progress if purchasing is required. |
| 11 | Healthy | PO exists and received quantity is at least PO quantity | PO material received. |
| 12 | Watchlist | Fallback for rows not matched above | Material chain is in progress; monitor until complete. |

## Needs Review Usage

Needs Review should be kept very limited in Order Material Tracking.

Do not use Needs Review for normal business variance, including:

- ROP amount differs from RKB amount.
- ROP quantity differs from RKB quantity.
- PO amount differs from ROP amount.
- PO quantity is higher than ROP quantity.
- PO without ROP.
- Mixed UoM.
- From Stock.
- Unknown product classification.
- Discount/additional-charge/transactional rows.

Needs Review should only be reintroduced for truly broken material relationships after real examples are inspected and confirmed.

## Intentionally Not Included

- No SQL changes.
- No backend data-model changes.
- No changes to dashboard financial, quantity, or material-chain calculations.
- No fake data or confidential data.
- No invoice/payment accounting interpretation.
- No automatic exception from RKB/ROP/PO amount variance.
- No automatic exception from PO quantity higher than ROP.
- No automatic exception from transactional lines such as discount or additional charge.

## Phase 2 Suggestions

- Inspect examples for unknown product classification, unknown source path, and zero-quantity rows before treating them as exceptions.
- Add Transactional Line classification if discount/additional-charge rows can be identified safely.
- Add reliable procurement ownership or supplier contact fields if they become available from the API.
- Add age-based follow-up signals when trusted RKB, ROP, PO, and receipt dates are exposed.
- Add optional drill-down links from detection cards to pre-filtered table views.
- Add backend-provided review signal fields if the rule mapping becomes shared across dashboards or exports.
