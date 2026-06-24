# Data Truth Layer Review

Review date: 2026-06-23

## What Changed

The Data Truth Layer now classifies fulfillment/source at Sales Order line level first, then rolls that classification up to Sales Order header level.

Updated SQL files:
- `sql/01_base_views.sql`
- `sql/02_traceability_views.sql`
- `sql/03_validation_queries.sql`
- `sql/README.md`

Updated or created views:
- `vw_sales_order_revenue`
- `vw_mrp_order_context`
- `vw_stock_movement_context`
- `vw_approval_product_line_context`
- `vw_rkb_planning_lines`
- `vw_internal_order_context`
- `vw_procurement_lines`
- `vw_accounting_sales_lines`
- `vw_manufacturing_flow_context`
- `vw_sales_order_line_source_context`
- `vw_sales_order_source_summary`
- `vw_so_traceability`
- `vw_data_quality_exceptions`

## Implemented Business Rules

### Status Validity

Cancelled records are now excluded from active operational metrics, active traceability metrics, and future profitability inputs.

Cancelled records are still visible in audit/data-quality views with `CANCELLED_RECORD` labels.

Status fields found and used:

| Module | Status field | Cancel values |
| --- | --- | --- |
| Sales | `sale_order.state` | `cancel`, `cancelled` |
| Sales Order Line | inherits `sale_order.state` | `cancel`, `cancelled` |
| Manufacturing | `mrp_production.state` | `cancel`, `cancelled` |
| RKB / Approval | `approval_product_line.x_studio_status` | `cancel`, `cancelled` |
| Procurement | `purchase_order_line.state` | `cancel`, `cancelled` |
| Stock | `stock_move_line.state` | `cancel`, `cancelled` |
| Accounting | `account_move_line.parent_state` | `cancel`, `cancelled` |

Each module view exposes:
- `normalized_status`
- `is_cancelled`
- `is_valid_for_metrics`

### Sales Order / Sales Order Line

Line source classification is implemented in `vw_sales_order_line_source_context`.

Rules:
- `FROM_INTERNAL_ORDER`: `sale_order.x_studio_io_1` is filled.
- `MIXED_SOURCE`: line has both inferred stock movement and inferred MO.
- `MAKE_TO_ORDER`: line product has inferred MO from SO origin and product.
- `FROM_STOCK`: line has inferred delivery movement and no inferred MO.
- `NEEDS_MOVEMENT_CLASSIFICATION`: line has only unknown movement type evidence.
- `UNKNOWN_SOURCE`: no IO, MO, or stock movement link is available.

Header source classification is implemented in `vw_sales_order_source_summary`.

Rules:
- If all lines share one source type, the SO uses that source type.
- If multiple line source types exist, the SO is `MIXED_SOURCE`.

Important field note:
- `sale_order.x_studio_io_1` exists and is used.
- Empty `x_studio_io_1 = '{}'` is treated as no IO.
- `sale_order_line.x_studio_io_1` is not extracted, so line-level IO can only inherit from the SO header.

### Manufacturing Order

Implemented in `vw_mrp_order_context`.

Rules:
- `IO_BASED_MO`: IO is filled and origin does not match SO.
- `SO_BASED_MO`: origin matches SO and IO is empty.
- `INVALID_BOTH_SO_AND_IO`: origin matches SO and IO is filled.
- `INVALID_BOTH_IO_AND_JO`: IO and JO are both filled.
- `INVALID_JO_FORMAT`: JO is non-empty, not `New`, and not exactly 7 digits.
- `JO_BASED_MO`: only JO is filled.
- `UNKNOWN_OR_MANUAL_MO`: no clear source reference.

JO normalization:
- `New` is treated as no JO.
- valid JO must be exactly 7 digits.

### Approval Product Line

Implemented in `vw_approval_product_line_context`.

`vw_rkb_planning_lines` is retained as a compatibility view filtered to RKB-only rows.

Approval category rules:
- `RKB` -> `RKB_PLANNING`
- `ROP` / `PEMBELIAN` -> `ROP_PROCUREMENT_REQUEST`
- `MANUFACTURE` -> `INTERNAL_ORDER`
- `INTERNAL USE` -> `OUT_OF_SCOPE_INTERNAL_USE`
- empty/null/`New`/`{}` -> `UNKNOWN_APPROVAL_CATEGORY`
- other values -> `OTHER_APPROVAL_CATEGORY`

Rules:
- `IO_BASED_RKB`: only IO is filled.
- `JO_BASED_RKB`: only JO is filled.
- `INVALID_BOTH_IO_AND_JO`: both IO and JO are filled.
- `INVALID_JO_FORMAT`: JO is non-empty, not `New`, and not exactly 7 digits.
- `UNLINKED_RKB`: neither IO nor JO is filled.

Internal Order v1 rule:
- Internal Order is represented by `approval_product_line.x_studio_category = MANUFACTURE`.
- `vw_internal_order_context` exposes MANUFACTURE approval lines and links them to MO primarily by `approval_product_line.approval_request_id = mrp_production.x_studio_nomor_io`; valid JO remains secondary context.
- A separate Internal Order master table is not required for v1.

Manufacturing flow rule:
- `vw_manufacturing_flow_context` connects Internal Order approval lines -> MO -> stock movement classification -> later SO if inferable -> accounting if linked.
- SO is not forced; missing later SO is marked as no SO link yet.

### Purchase Order Line

Implemented in `vw_procurement_lines`.

Rules:
- `IO_BASED_PO`: only IO is filled.
- `JO_BASED_PO`: only JO is filled.
- `INVALID_BOTH_IO_AND_JO`: both IO and JO are filled.
- `INVALID_JO_FORMAT`: JO is non-empty, not `New`, and not exactly 7 digits.
- `UNLINKED_PO`: neither IO nor JO is filled.

The real extracted IO field is `purchase_order_line.x_studio_many2one_field_ij0j0`.

### Stock Movement

Implemented in `vw_stock_movement_context`.

`stock_move_line.picking_type_id` is a text display label and is classified into:
- `DELIVERY`
- `RECEIPT`
- `INTERNAL_TRANSFER`
- `MANUFACTURING`
- `UNKNOWN_MOVEMENT_TYPE`

## Detectable Exceptions

`vw_data_quality_exceptions` now detects:
- PO line has both IO and JO.
- PO line has neither IO nor JO.
- RKB line has both IO and JO.
- RKB line has neither IO nor JO.
- MO/RKB/PO has invalid JO format.
- MO has both SO source and IO source.
- MO has both IO and JO.
- SO is linked to IO but also appears to trigger a new MO.
- SO has mixed source types.
- SO line source cannot be determined.
- Possible double RKB where related MO keys have both IO-based and JO-based RKB.
- Cancelled SO/MO/RKB/PO/stock/accounting records as `CANCELLED_RECORD`.

## Current Validation Snapshot

Latest validation run after cancelled-record exclusion:

| Metric | Count |
| --- | ---: |
| total_so_active | 1,175 |
| total_so_cancelled | 26 |
| total_so_lines_active | 11,967 |
| total_so_lines_cancelled | 286 |
| active_so_with_mo | 790 |
| active_so_without_mo | 385 |
| active_so_with_stock_movement | 1,059 |
| active_so_with_accounting_line | 1,077 |
| active_so_mixed_source | 797 |
| active_so_unknown_source | 80 |
| active_so_line_from_internal_order | 1,026 |
| active_so_line_from_stock | 620 |
| active_so_line_make_to_order | 1,353 |
| active_so_line_mixed_source | 6,401 |
| active_so_line_unknown_source | 2,567 |
| active_so_line_needs_movement_classification | 0 |
| active_rkb_count | 27,374 |
| active_rop_count | 14,184 |
| active_internal_order_lines | 1,023 |
| active_internal_order_lines_with_io_number | 1,023 |
| active_internal_order_lines_with_valid_jo | 0 |
| active_internal_order_lines_linked_to_mo | 817 |
| active_internal_order_lines_not_linked_to_mo | 206 |
| active_out_of_scope_internal_use_count | 50 |
| unknown_approval_category_count | 24 |
| other_approval_category_count | 0 |
| active_mo_count | 10,048 |
| cancelled_mo_count | 763 |
| active_mo_with_io | 1,205 |
| active_mo_linked_to_internal_order | 1,204 |
| active_mo_not_linked_to_internal_order_or_so | 243 |
| active_mo_without_so | 1,609 |
| active_mo_invalid_both_so_and_io | 0 |
| active_mo_invalid_both_io_and_jo | 31 |
| active_mo_invalid_jo_format | 1 |
| cancelled_rkb_count | 59 |
| active_rkb_lines_with_io_or_jo | 26,973 |
| active_rkb_invalid_both_io_and_jo | 0 |
| active_rkb_invalid_jo_format | 0 |
| active_rkb_unlinked | 402 |
| active_po_count | 18,468 |
| cancelled_po_count | 2,488 |
| active_po_lines_with_io_or_jo | 10,836 |
| active_po_invalid_both_io_and_jo | 11 |
| active_po_invalid_jo_format | 0 |
| active_po_unlinked | 7,632 |
| active_stock_move_line_count | 225,420 |
| cancelled_stock_move_line_count | 340 |
| delivery_movement_count | 8,584 |
| finished_goods_store_movement_count | 8,110 |
| manufacturing_movement_count | 163,635 |
| active_accounting_line_count | 417,947 |
| active_accounting_lines_linked_to_so | 28,956 |
| accounting_lines_x_studio_sales_order_new | 390,172 |
| active_accounting_lines_unmatched_non_new_so_number | 26 |
| cancelled_accounting_line_count | 3,698 |

## Still Lacking

For accurate fulfillment and profitability, these fields/tables are still needed:
- `sale_order_line.x_studio_io_1` or another line-level IO field, if line-specific IO exists in Odoo.
- Stronger Internal Order to later Sales Order bridge after make-to-stock fulfillment.
- `approval_request.state` for header-level approval state.
- `stock_move`, `stock_picking`, and `stock_location` for reliable delivery and stock source classification.
- `account_move` for invoice header/payment state.
- Accounting SO mapping now uses normalized `account_move_line.x_studio_sales_order = sale_order.name`, not `sale_order.id`.
- `approval_request.state` and approval category for header-level approval status/category.
- Product master data in `product_product` and `product_template`.
- Stock valuation/unit cost for actual material cost.
- Estimator cost import from Excel or another controlled source.

## Not Implemented Yet

The Data Truth Layer still does not calculate final profitability. Revenue, RKB cost, procurement cost, actual material cost, labor, overhead, invoice, and AR should only be combined after the missing source and costing fields are resolved.
