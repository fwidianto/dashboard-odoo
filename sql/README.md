# Data Truth Layer SQL

This folder contains the first version of the Odoo manufacturing dashboard Data Truth Layer.

The current layer is traceability-only. It classifies source/fulfillment paths and exposes data-quality exceptions. It does not calculate final profitability and it does not overwrite raw Odoo extract tables.

## Run Order

Run the files in this order:

1. `sql/01_base_views.sql`
2. `sql/02_traceability_views.sql`
3. `sql/04_dashboard_traceability_views.sql`
4. `sql/03_validation_queries.sql`

## Views

Base views:
- `vw_sales_order_revenue`
- `vw_mrp_order_context`
- `vw_stock_movement_context`
- `vw_approval_product_line_context`
- `vw_rkb_planning_lines`
- `vw_internal_order_context`
- `vw_procurement_lines`
- `vw_accounting_sales_lines`
- `vw_sale_order_internal_order_bridge`
- `vw_manufacturing_flow_context`
- `vw_sales_order_line_source_context`
- `vw_sales_order_source_summary`

Traceability and exception views:
- `vw_so_traceability`
- `vw_data_quality_exceptions`

Dashboard-ready views:
- `vw_dashboard_internal_order_traceability`

`vw_dashboard_internal_order_traceability` is the v1 source for the Internal Order dashboard. It uses the parsed `sale_order.x_studio_io_1` bridge to find linked SOs, then measures sales delivery and invoicing from `sale_order_line.product_uom_qty`, `sale_order_line.qty_delivered`, `sale_order_line.qty_invoiced`, `sale_order_line.price_subtotal`, `sale_order.delivery_status`, and `sale_order.invoice_status`. It measures procurement receipt and billing progress from `purchase_order_line.product_qty`, `purchase_order_line.qty_received`, `purchase_order_line.qty_invoiced`, and `purchase_order_line.state` where PO lines are linked by Internal Order number. Stock movement counts remain available as optional/advanced diagnostics, but they are not required for v1 readiness status.

## Source Classification

## Approval Category Classification

`approval_product_line.x_studio_category` is used to split approval lines into planning, procurement request, Internal Order, and out-of-scope flows.

| Category | Business type |
| --- | --- |
| `RKB` | `RKB_PLANNING` |
| `ROP` / `PEMBELIAN` | `ROP_PROCUREMENT_REQUEST` |
| `MANUFACTURE` | `INTERNAL_ORDER` |
| `INTERNAL USE` | `OUT_OF_SCOPE_INTERNAL_USE` |
| empty / null / `New` / `{}` | `UNKNOWN_APPROVAL_CATEGORY` |
| any other value | `OTHER_APPROVAL_CATEGORY` |

RKB is internal PPIC material planning for comparison. RKB does not directly trigger purchasing. ROP/PEMBELIAN is an approval-based procurement request and should be approved before becoming purchasing input. MANUFACTURE is the v1 Internal Order source. For MANUFACTURE lines, `approval_request_id` displays the Internal Order number and `approval_request_numeric_id` stores the numeric `approval.request.id`. INTERNAL USE is out of current dashboard scope.

`vw_approval_product_line_context` contains all approval categories. `vw_rkb_planning_lines` is kept as a filtered compatibility view for RKB only.

## Stock Movement Classification

`stock_move_line.picking_type_id` is available as a text display label and is used to classify movement type:

| Keyword family | Movement type |
| --- | --- |
| OUT, Delivery, Customer, Keluar | `DELIVERY` |
| Receipt, Vendor, Terima | `RECEIPT` |
| Internal, INT, Transfer | `INTERNAL_TRANSFER` |
| Manufacturing, Production, Pick Components, MO, MRP | `MANUFACTURING` |
| Store Finished Product, Finished Goods, Finished Product | `FINISHED_GOODS_STORE` |
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
| `FROM_INTERNAL_ORDER` | Parsed `vw_sale_order_internal_order_bridge` has one or more IO references for the SO. Empty placeholder `{}`, null, and `New` are treated as empty. |
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
| SO to IO | Parse numeric IDs from `sale_order.x_studio_io_1` into `vw_sale_order_internal_order_bridge` | confirmed many-to-many bridge |
| Internal Order to SO | `vw_sale_order_internal_order_bridge.internal_order_id = approval_product_line.approval_request_numeric_id` | confirmed many-to-many bridge |
| SO line to IO | Not extracted | unavailable |
| SO to MO | `sale_order.name = mrp_production.origin` | inferred |
| Stock movement to MO | `stock_move_line.reference = mrp_production.name` | inferred |
| Stock movement to SO | `stock_move_line.x_studio_source_document = sale_order.name` | inferred |
| Stock movement to SO line | `stock_move_line.x_studio_sale_line = sale_order_line.id::text` | inferred where present |
| Accounting to SO | normalized `account_move_line.x_studio_sales_order = sale_order.name::text` | inferred |
| Approval line to IO/JO | `approval_product_line.x_studio_nomor_io` / normalized `x_studio_nomor_jo` | classified |
| Internal Order to MO | MANUFACTURE `approval_product_line.approval_request_id = mrp_production.x_studio_nomor_io`; valid JO is secondary | inferred |
| PO to IO/JO | `purchase_order_line.x_studio_many2one_field_ij0j0` / normalized `x_studio_jo` | classified |

## Exception View

`vw_data_quality_exceptions` surfaces records needing correction or review:
- PO line has both IO and JO.
- PO line has neither IO nor JO.
- RKB line has both IO and JO.
- RKB line has neither IO nor JO.
- Internal Order approval line has neither IO nor valid JO.
- Internal Order approval line is not linked to MO.
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
- `account_move.state` and `approval_request.state` are not extracted yet.
- Internal Order master data is not required for v1; Internal Order is represented by `approval_product_line.x_studio_category = MANUFACTURE`.
- Delivery Order header data is not extracted yet because `stock_picking` is missing. For v1 Internal Order traceability, delivery progress uses linked SO line delivered quantity instead.
- Invoice header data is not extracted yet because `account_move` is missing. For v1 Internal Order traceability, invoice progress uses linked SO line invoiced quantity, linked PO line invoiced quantity, and accounting lines where available.
- Stock movement remains optional operational traceability. It should not be used as the primary v1 KPI source for delivery, receipt, or invoice progress.
- Product master tables exist but currently have no rows.
- `account_move_line.x_studio_sales_order = 'New'` is treated as no SO reference.
- Final profitability must wait until estimator data, actual material valuation, and stronger IO-to-later-SO mapping are solved.
