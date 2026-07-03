# Order Material Tracking Review Signals

## Purpose

Review Signals add a compact frontend review layer to the Order Material Tracking dashboard. The goal is to group currently loaded material lines into business-readable follow-up buckets without changing SQL, backend calculations, or the underlying data model.

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

## Rule Mapping

Rules are evaluated in priority order. The first matching signal becomes the row's `review_signal`, and the matching message becomes `review_note`.

| Priority | Review Signal | Condition | Review Note |
|---:|---|---|---|
| 1 | Needs Review | `po_without_rop_flag` is true | PO exists without linked ROP; check procurement chain. |
| 1 | Needs Review | `mixed_uom_flag` is true | Mixed UoM detected; quantity comparison may need review. |
| 1 | Needs Review | `product_trackability_class === "UNKNOWN_PRODUCT_CLASS"` | Product classification is unclear. |
| 1 | Needs Review | `materialStatusMeta(row).label === "Needs Review"` | Material chain status needs checking. |
| 1 | Needs Review | `Math.abs(excess_rop_amount) > 0` | ROP amount differs from RKB reference; review variance. |
| 1 | Needs Review | `Math.abs(po_excess_amount) > 0` | PO amount differs from ROP reference; review variance. |
| 2 | Supplier Follow-up | `rop_without_po_flag` is true | ROP exists but no PO is linked yet. |
| 2 | Supplier Follow-up | PO exists and received quantity is zero | PO created but material has not been received. |
| 2 | Supplier Follow-up | PO is partially received | PO partially received; supplier follow-up may be needed. |
| 3 | Operational Follow-up | `has_sales_order_link` is false | Pre-SO Internal Order; monitor until sales order linkage is available. |
| 3 | Operational Follow-up | `material_chain_source === "UNKNOWN_SOURCE"` | Material source path is unclear. |
| 3 | Operational Follow-up | `product_trackability_class !== "TRACKABLE_PRODUCT"` | Non-product/service row; review operational meaning if needed. |
| 4 | Healthy | `material_chain_source === "FROM_STOCK"` | Material is covered from stock. |
| 4 | Healthy | PO exists, received quantity is at least PO quantity, and no mismatch flag exists | PO material received; no immediate material follow-up. |
| 5 | Watchlist | Material status is RKB Only, ROP Created, or PO Created without a stronger signal | Material chain is in progress; monitor until complete. |
| 5 | Watchlist | Fallback for active rows not matched above | Monitor material chain until completion. |

## Priority Order

1. Needs Review
2. Supplier Follow-up
3. Operational Follow-up
4. Healthy
5. Watchlist

## Intentionally Not Included

- No SQL changes.
- No backend data-model changes.
- No changes to dashboard financial, quantity, or material-chain calculations.
- No fake data or confidential data.
- No invoice/payment accounting interpretation.
- Non-product/service rows are not automatically treated as errors. They only become Operational Follow-up when no higher-priority procurement or data issue is present.

## Phase 2 Suggestions

- Add reliable procurement ownership or supplier contact fields if they become available from the API.
- Add age-based follow-up signals when trusted RKB, ROP, PO, and receipt dates are exposed.
- Add optional drill-down links from detection cards to pre-filtered table views.
- Add backend-provided review signal fields if the rule mapping becomes shared across dashboards or exports.