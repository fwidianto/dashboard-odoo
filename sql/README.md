# Data Truth Layer SQL

This folder contains the first version of the Odoo manufacturing dashboard Data Truth Layer.

The current layer is traceability-only. It classifies source/fulfillment paths and exposes data-quality exceptions. It does not calculate final profitability and it does not overwrite raw Odoo extract tables.

## Run Order

Run the files in this order:

1. `sql/01_base_views.sql`
2. `sql/02_traceability_views.sql`
3. `sql/03_validation_queries.sql`

## Views

Base views:
- `vw_sales_order_revenue`
- `vw_mrp_order_context`
- `vw_stock_movement_context`
- `vw_rkb_planning_lines`
- `vw_procurement_lines`
- `vw_accounting_sales_lines`
- `vw_sales_order_line_source_context`
- `vw_sales_order_source_summary`

Traceability and exception views:
- `vw_so_traceability`
- `vw_data_quality_exceptions`

## Source Classification

## Approval Category Classification

`approval_product_line.x_studio_category` is used to split approval lines into planning vs procurement request flows.

| Category | Business type |
| --- | --- |
| `RKB` | `RKB_PLANNING` |
| `ROP` / `PEMBELIAN` | `ROP_PROCUREMENT_REQUEST` |
| empty / null / `New` / `{}` | `UNKNOWN_APPROVAL_CATEGORY` |
| any other value | `OTHER_APPROVAL_CATEGORY` |

RKB is internal PPIC material planning for comparison. RKB does not directly trigger purchasing. ROP/PEMBELIAN is an approval-based procurement request and should be approved before becoming purchasing input.

## Stock Movement Classification

`stock_move_line.picking_type_id` is available as a text display label and is used to classify movement type:

| Keyword family | Movement type |
| --- | --- |
| OUT, Delivery, Customer, Keluar | `DELIVERY` |
| Receipt, Vendor, Terima | `RECEIPT` |
| Internal, INT, Transfer | `INTERNAL_TRANSFER` |
| Manufacturing, Production, Pick Components, MO, MRP | `MANUFACTURING` |
| otherwise | `UNKNOWN_MOVEMENT_TYPE` |

SO line `FROM_STOCK` now uses delivery movements only, not receipts or internal transfers.

## Status Validity

Cancelled records remain visible in audit views but are excluded from active operational, traceability, and future profitability metrics.

Each module view exposes:
- `normalized_status`
- `is_cancelled`
- `is_valid_for_metrics`

Status fields currently used:

| Module | Source status field |
| --- | --- |
| Sales Order | `sale_order.state` |
| Sales Order Line | inherits `sale_order.state` |
| Manufacturing Order | `mrp_production.state` |
| RKB / Approval line | `approval_product_line.x_studio_status` |
| Purchase Order line | `purchase_order_line.state` |
| Stock movement line | `stock_move_line.state` |
| Accounting line | `account_move_line.parent_state` |

`cancel` and `cancelled` are treated as cancelled.

Sales Order line source is classified in `vw_sales_order_line_source_context`:

| Source type | Rule |
| --- | --- |
| `FROM_INTERNAL_ORDER` | `sale_order.x_studio_io_1` is filled. Empty placeholder `{}` is treated as empty. |
| `MIXED_SOURCE` | Line has both inferred MO and stock movement. |
| `MAKE_TO_ORDER` | Line product has inferred MO through SO origin and product. |
| `FROM_STOCK` | Line has inferred stock movement but no inferred MO. |
| `UNKNOWN_SOURCE` | No extracted IO, MO, or stock movement link can determine source. |

Sales Order header source is classified in `vw_sales_order_source_summary`:
- If all lines share one source, the SO uses that source.
- If line sources differ, the SO is `MIXED_SOURCE`.

## JO Normalization

JO fields often contain the placeholder value `New`. This is not a real JO and is treated as null.

A valid JO must:
- not be null
- not be empty
- not equal `New`
- be exactly 7 digits
- contain no text

The SQL exposes:
- `raw_job_order_number`
- `normalized_jo_number`
- `has_valid_jo`
- `invalid_jo_format`

This rule applies to:
- `mrp_production.x_studio_nomor_jo`
- `approval_product_line.x_studio_nomor_jo`
- `purchase_order_line.x_studio_jo`

## Inferred And Confirmed Links

| Link | Rule | Status |
| --- | --- | --- |
| SO line to SO | `sale_order.name = sale_order_line.order_id` | inferred |
| SO to IO | `sale_order.x_studio_io_1` | confirmed when non-empty |
| SO line to IO | Not extracted | unavailable |
| SO to MO | `sale_order.name = mrp_production.origin` | inferred |
| Stock movement to MO | `stock_move_line.reference = mrp_production.name` | inferred |
| Stock movement to SO | `stock_move_line.x_studio_source_document = sale_order.name` | inferred |
| Stock movement to SO line | `stock_move_line.x_studio_sale_line = sale_order_line.id::text` | inferred where present |
| Accounting to SO | normalized `account_move_line.x_studio_sales_order = sale_order.name::text` | inferred |
| RKB to IO/JO | `approval_product_line.x_studio_nomor_io` / normalized `x_studio_nomor_jo` | classified |
| PO to IO/JO | `purchase_order_line.x_studio_many2one_field_ij0j0` / normalized `x_studio_jo` | classified |

## Exception View

`vw_data_quality_exceptions` surfaces records needing correction or review:
- PO line has both IO and JO.
- PO line has neither IO nor JO.
- RKB line has both IO and JO.
- RKB line has neither IO nor JO.
- MO has both SO source and IO source.
- MO has both IO and JO.
- MO/RKB/PO has invalid JO format.
- SO is linked to IO but also appears to trigger a new MO.
- SO has mixed source types.
- SO line source cannot be determined.
- Possible double RKB through both IO-based and JO-based RKB on related MO keys.
- Cancelled records as `CANCELLED_RECORD` audit rows.

## Important Caveats

- `sale_order.x_studio_io_1` is available and used, but `sale_order_line.x_studio_io_1` is not extracted.
- `account_move.state`, `approval_request.state`, and `approval_request.category` are not extracted yet.
- RKB category is not confirmed because `approval_request` / approval category is not extracted yet.
- Internal Order master data is not extracted yet.
- Delivery Order header data is not extracted yet because `stock_picking` is missing.
- Invoice header data is not extracted yet because `account_move` is missing.
- Product master tables exist but currently have no rows.
- `account_move_line.x_studio_sales_order = 'New'` is treated as no SO reference.
- Final profitability must wait until estimator data, RKB category, actual material valuation, and stronger IO-to-SO mapping are solved.
