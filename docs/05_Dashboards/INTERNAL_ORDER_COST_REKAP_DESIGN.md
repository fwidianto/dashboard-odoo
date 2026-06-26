# Internal Order Cost Rekap Design

## Why This Report Mode Exists

`426IO026` is a pre-Sales-Order Internal Order case.
The related Sales Order does not exist yet, so the case must not be forced into the existing SO/JO Rekap grain.

This design introduces a separate Internal Order Rekap mode for cases where RKB Actual, ROP / PEMBELIAN, and PO already exist before the Sales Order is created.

## Scope

Phase 1 is operational reconciliation only:
- RKB Actual
- ROP / PEMBELIAN
- PO

Out of scope:
- RKB PPIC import/upload workflow
- profitability
- margin
- COGS
- accounting profit
- AR/payment
- UI/API

## Source Views

The SQL layer uses existing Odoo traceability views only:
- `vw_rkb_planning_lines`
- `vw_approval_product_line_context`
- `vw_procurement_lines`
- `vw_sale_order_internal_order_bridge`

No existing SO/JO Rekap view is modified.

## New Views

- `vw_internal_order_rekap_scope`
- `vw_internal_order_rkb_actual_agg`
- `vw_internal_order_rop_agg`
- `vw_internal_order_po_agg`
- `vw_internal_order_product_universe`
- `vw_internal_order_rekap_lines`
- `vw_internal_order_rekap_summary`

## Grain

- Scope view: one row per `internal_order_number`
- Aggregate views: one row per `internal_order_number + product_key`
- Line view: one row per `internal_order_number + product_key`
- Summary view: one row per `internal_order_number`

## Product Matching Strategy

The SQL layer is conservative.

Preferred product key order:
1. Exact product code extracted from bracketed product names like `[43809] ...`
2. Normalized product name when no bracketed code exists

This is intentionally non-fuzzy.
It reflects Odoo data truth rather than trying to mimic the Excel workbook.

Risk:
- normalized product-name fallback can still miss a manual workbook synonym or label variant

## UoM Limitation

No unit conversion is performed.

The SQL layer only flags mixed UoM situations.
Quantity comparison is reliable only when the UoM is consistent.

## View Behavior

### `vw_internal_order_rekap_scope`
- one row per internal order
- includes company name when available
- includes source counts and flags for RKB Actual, ROP, and PO
- includes `has_sales_order_link` from `vw_sale_order_internal_order_bridge`

### `vw_internal_order_rkb_actual_agg`
- built from `vw_rkb_planning_lines`
- filters to valid internal orders
- excludes cancelled / rejected rows
- computes qty, subtotal, derived unit price, line count, and status summaries

### `vw_internal_order_rop_agg`
- built from `vw_approval_product_line_context`
- filters `approval_business_type = 'ROP_PROCUREMENT_REQUEST'`
- filters to valid internal orders
- excludes cancelled / rejected rows
- computes qty, subtotal, derived unit price, date-of-need range, and status summaries

### `vw_internal_order_po_agg`
- built from `vw_procurement_lines`
- filters to valid internal orders
- excludes cancelled rows
- computes ordered qty, received qty, invoiced qty, subtotal, derived unit price, and purchase-state summaries

### `vw_internal_order_product_universe`
- unions product rows from RKB Actual, ROP, and PO
- keeps product matching conservative
- flags mixed UoM without converting units

### `vw_internal_order_rekap_lines`
- joins the product universe to the three aggregates
- computes not-yet-ROP, excess ROP, PO-vs-ROP flags, and product presence status

### `vw_internal_order_rekap_summary`
- summarizes the line view by internal order
- includes amount totals, product counts, mixed UoM count, and Sales Order link flag

## Validation Case

Use `426IO026` as the primary test case.

Expected interpretation:
- Internal Order exists
- Sales Order link is absent in the current bridge view
- RKB Actual and ROP should be present
- PO may be present but does not need to match the workbook exactly at phase 1

## Validation Queries

```sql
SELECT COUNT(*) FROM vw_internal_order_rekap_summary;
SELECT * FROM vw_internal_order_rekap_summary WHERE internal_order_number = '426IO026';
SELECT * FROM vw_internal_order_rekap_lines WHERE internal_order_number = '426IO026' ORDER BY product_key LIMIT 50;
SELECT COUNT(*) FROM vw_internal_order_rekap_lines WHERE internal_order_number = '426IO026' AND mixed_uom_flag = true;
SELECT product_presence_status, COUNT(*) FROM vw_internal_order_rekap_lines WHERE internal_order_number = '426IO026' GROUP BY product_presence_status ORDER BY product_presence_status;
SELECT * FROM vw_internal_order_rekap_summary WHERE internal_order_number = '426IO026';
SELECT internal_order_number, product_count, rkb_actual_amount, rop_amount, po_amount, not_yet_rop_amount, excess_rop_amount FROM vw_internal_order_rekap_summary ORDER BY COALESCE(rkb_actual_amount, 0) DESC LIMIT 20;
```

## Next Steps

- Validate `426IO026` against the new IO-first views
- Review the remaining PO gaps
- Keep SO/JO Rekap separate
- Build UI only after the IO-first SQL mapping is confirmed
