# Data Quality Investigation

Investigation date: 2026-06-23

## JO Placeholder Discovery

Odoo JO fields often contain the value `New`.

This value is a placeholder/default value and must not be treated as a real Job Order number.

Affected fields:
- `mrp_production.x_studio_nomor_jo`
- `approval_product_line.x_studio_nomor_jo`
- `purchase_order_line.x_studio_jo`

Observed `New` counts:

| Field | `New` count |
| --- | ---: |
| `mrp_production.x_studio_nomor_jo` | 2,183 |
| `approval_product_line.x_studio_nomor_jo` | 13,200 |
| `purchase_order_line.x_studio_jo` | 12,091 |

## Correct JO Rule

A valid JO must:
- not be null
- not be empty
- not equal `New`
- be exactly 7 digits
- contain no text

The Data Truth Layer now exposes:
- `raw_job_order_number`
- `normalized_jo_number`
- `has_valid_jo`
- `invalid_jo_format`

## Impact On Previous Counts

Previous invalid IO+JO counts were inflated because `New` was treated as a real JO.

Corrected validation:

| Metric | Previous count | Corrected count |
| --- | ---: | ---: |
| `mo_invalid_both_io_and_jo` | 1,260 | 33 |
| `rkb_invalid_both_io_and_jo` | 8,401 | 16 |
| `po_invalid_both_io_and_jo` | 3,437 | 12 |

## Current Invalid JO Format Counts

Rows with non-empty JO values that are not `New` and not exactly 7 digits:

| Metric | Count |
| --- | ---: |
| `mo_invalid_jo_format` | 1 |
| `rkb_invalid_jo_format` | 23 |
| `po_invalid_jo_format` | 0 |

## Business Meaning

After this correction:
- `New` means no JO.
- only 7-digit JO values are treated as real JO.
- `INVALID_BOTH_IO_AND_JO` now means the record has an IO and a valid JO.
- `INVALID_JO_FORMAT` is separated from invalid IO+JO conflicts.

This makes the exception queue much closer to the real business correction workload.

## Cancelled Record Handling

Cancelled records are not deleted and raw tables are not modified.

The Data Truth Layer now keeps cancelled rows visible for audit while excluding them from active traceability and future profitability metrics.

Current cancelled counts:

| Metric | Count |
| --- | ---: |
| total_so_cancelled | 26 |
| total_so_lines_cancelled | 286 |
| cancelled_mo_count | 763 |
| cancelled_rkb_count | 270 |
| cancelled_po_count | 2,488 |
| cancelled_stock_move_line_count | 340 |
| cancelled_accounting_line_count | 3,695 |

Cancelled rows appear in `vw_data_quality_exceptions` as `CANCELLED_RECORD`, but they are not treated as missing or invalid business data unless they also have a separate structural issue.

## Accounting Sales Order Mapping Correction

Discovery:
- `account_move_line.x_studio_sales_order` stores `sale_order.name`, not `sale_order.id`.
- `x_studio_sales_order = 'New'` is a placeholder and is treated as null.

Implemented normalization:

```sql
CASE
  WHEN x_studio_sales_order IS NULL THEN NULL
  WHEN trim(x_studio_sales_order::text) IN ('', '{}', 'New') THEN NULL
  ELSE trim(x_studio_sales_order::text)
END
```

The Data Truth Layer now joins accounting to SO using:

```sql
normalized_sales_order_number = sale_order.name::text
```

Current accounting validation:

| Metric | Count |
| --- | ---: |
| active_so_with_accounting_line | 1,074 |
| active_accounting_lines_linked_to_so | 28,759 |
| accounting_lines_x_studio_sales_order_new | 389,197 |
| active_accounting_lines_unmatched_non_new_so_number | 26 |

The previous `sale_order.id` join severely undercounted accounting traceability.

## New Approval Category And Picking Type Fields

New fields confirmed:
- `approval_product_line.x_studio_category`
- `stock_move_line.picking_type_id`

`picking_type_id` is extracted as a text display label, not a numeric ID.

Business category mapping:
- `RKB` is internal PPIC planning.
- `ROP` and `PEMBELIAN` are the same business category and represent procurement request flow.
- `MANUFACTURE` is Internal Order for dashboard v1.
- `INTERNAL USE` is out of current dashboard scope.

`MANUFACTURE` was previously counted as `OTHER_APPROVAL_CATEGORY`. Fauzan clarified that this is the Internal Order source in the approval module, so the Data Truth Layer now maps it to `INTERNAL_ORDER`.

Current validation highlights:

| Metric | Count |
| --- | ---: |
| active_rkb_count | 27,375 |
| active_rop_count | 14,184 |
| active_internal_order_lines | 1,023 |
| active_internal_order_lines_with_io_number | 1,023 |
| active_internal_order_lines_with_valid_jo | 0 |
| active_internal_order_lines_linked_to_mo | 817 |
| active_internal_order_lines_not_linked_to_mo | 206 |
| active_out_of_scope_internal_use_count | 50 |
| unknown_approval_category_count | 24 |
| other_approval_category_count | 0 |
| active_so_line_from_stock | 620 |
| active_so_line_needs_movement_classification | 0 |
| stock_movement_type_delivery | 8,584 |
| stock_movement_type_finished_goods_store | 8,110 |
| stock_movement_type_manufacturing | 163,635 |
| stock_movement_type_unknown_movement_type | 23,521 |

Manufacturing flow highlights:

| Metric | Count |
| --- | ---: |
| active_mo_linked_to_internal_order | 1,204 |
| active_mo_not_linked_to_internal_order_or_so | 243 |
| finished_goods_store_movement_count | 8,110 |
| delivery_movement_count | 8,584 |

Remaining stock blocker:
- `stock_picking_type` or `stock_picking` should still be extracted later for stable movement classification by operation type, warehouse, and route.
