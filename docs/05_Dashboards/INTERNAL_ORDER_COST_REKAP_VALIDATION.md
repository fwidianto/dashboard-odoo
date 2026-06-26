# Internal Order Cost Rekap Validation

## SQL Execution Status

Passed.

Executed:
- `sql/07_internal_order_cost_rekap_views.sql`

No existing SO/JO Rekap views were modified.

## Validation Summary

- `vw_internal_order_rekap_summary` row count: `87`
- `426IO026` summary row: present
- `vw_sale_order_internal_order_bridge` link for `426IO026`: none found
- `mixed_uom_count` for `426IO026`: `0`

## `426IO026` Summary Values

- `company_name`: `Nobi Putra Angkasa, PT`
- `has_sales_order_link`: `false`
- `product_count`: `418`
- `rkb_actual_product_count`: `414`
- `rop_product_count`: `179`
- `po_product_count`: `172`
- `rkb_actual_amount`: `9,078,236,100.61`
- `rop_amount`: `6,428,714,005.63`
- `po_amount`: `6,111,147,209.98`
- `not_yet_rop_amount`: `2,873,734,605.26`
- `excess_rop_amount`: `223,771,394.36`
- `po_received_qty`: `3,940.00`
- `po_invoiced_qty`: `8,446.00`
- `comparison_basis`: `ODOO_RKB_ACTUAL_BASELINE`

## Trackable vs Non-Trackable Breakdown

The Odoo approval screen for `RKB - 426IO026` confirms the full RKB Actual total is `9,078,236,100.61`.
That full total is preserved in the SQL summary.

- full `rkb_actual_amount`: `9,078,236,100.61`
- trackable `rkb_actual_trackable_amount`: `7,476,666,216.61`
- non-trackable `rkb_actual_non_trackable_amount`: `1,601,569,884.00`
- unknown-class `rkb_actual_unknown_class_amount`: `0.00`

Product counts by class:
- `TRACKABLE_PRODUCT`: `413`
- `NON_TRACKABLE_OTHERS`: `2`
- `BUDGET_SERVICE_ADJUSTMENT`: `1`
- `UNKNOWN_PRODUCT_CLASS`: `1`

Sample non-trackable rows:
- `!! - OTHERS (RKB)` -> `NON_TRACKABLE_OTHERS` -> `1,601,569,884.00`
- `[!! - 630411] !! - S.Part & Jasa Untuk Mesin 630411` -> `NON_TRACKABLE_OTHERS` -> `18,976,835.00` in PO scope
- `Jasa Transport [PRC]` -> `BUDGET_SERVICE_ADJUSTMENT` -> `6,600.00` in PO scope
- `Discount [PRC]` -> `UNKNOWN_PRODUCT_CLASS` -> `-1,155,743.15` in PO scope

Sample unknown rows:
- `Discount [PRC]` -> `UNKNOWN_PRODUCT_CLASS` -> `-1,155,743.15` in PO scope

Interpretation:
- The earlier ~`7.477B` figure was likely a trackable/product-only comparison
- The full Odoo RKB total is `9.078B`
- Both numbers are explainable depending on whether non-trackable budget/service rows are included
- The stricter 5-digit rule does not change the current `426IO026` totals; it only prevents non-standard bracketed rows from being treated as trackable
- Non-trackable rows are valid and should not be treated as data errors

## Product Presence Distribution for `426IO026`

- `PO_ONLY`: `2`
- `RKB_ONLY`: `236`
- `RKB_PO`: `1`
- `RKB_ROP`: `9`
- `RKB_ROP_PO`: `168`
- `ROP_ONLY`: `1`
- `ROP_PO`: `1`

## Top IOs by Amount

- `426IO026` remains the largest IO in the current summary view
- next highest examples include `325IO078`, `425IO016`, `125IO076`, and `226IO003`

## Known Limitations

- No UoM conversion is performed
- Mixed UoM is only flagged, not resolved
- Product matching is conservative and prefers bracketed product code extraction
- RKB PPIC is still outside PostgreSQL and remains a future upload/import workflow
- This layer is operational reconciliation only, not profitability, margin, COGS, or accounting profit

## Recommended Next Step

Validate the PO rows for the few unmatched or weakly matched items in `426IO026`, then keep the Internal Order Rekap layer separate from the SO/JO Rekap layer.
