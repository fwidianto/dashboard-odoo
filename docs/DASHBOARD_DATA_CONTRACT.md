# Dashboard Data Contract - V1

## Purpose

This document defines the data contract for the first dashboard page: Internal Order Traceability Dashboard.

The V1 dashboard uses existing validated Data Truth Layer views only. It does not calculate profitability, does not introduce new relationships, and does not use stock movement counts as readiness criteria.

Primary dashboard source:

```text
vw_dashboard_internal_order_traceability
```

Business truth for V1:

- Sales delivery/invoice progress comes from Sales Order line quantities.
- Procurement receipt/billing progress comes from Purchase Order line quantities.
- Stock movement counts are optional operational diagnostics only.

## Glossary

| Term | Meaning |
| --- | --- |
| SO | Sales Order. Customer demand and revenue document. |
| JO | Job Order. Factory terminology for an SO that requires new production. Every JO is an SO, but not every SO is a JO. |
| IO | Internal Order. Internal make-to-stock demand used to produce finished goods before customer SO exists. |
| RKB | PPIC material planning for comparison. |
| ROP / PEMBELIAN | Procurement request / Request of Purchase. |

V1 source interpretation:

| Source | Meaning |
| --- | --- |
| FROM_INTERNAL_ORDER | SO is linked to IO and uses finished goods already produced from Internal Order. |
| MAKE_TO_ORDER / JO | SO requires new production and creates or links to MO. |
| FROM_STOCK | SO is delivered from available stock without IO/MO. |

JO should not be shown as a separate object beside SO. If JO is shown in future drill-downs, label it as a production-required SO/job-order reference.

## Required V1 Fields

| Field Name | Business Meaning | Source View | Source Column | Calculation Rule | Display Format |
| --- | --- | --- | --- | --- | --- |
| `internal_order_number` | Internal Order identifier shown to users. | `vw_dashboard_internal_order_traceability` | `internal_order_number` | Direct field. | Text |
| `traceability_status` | Current lifecycle/follow-up status for the Internal Order. | `vw_dashboard_internal_order_traceability` | `traceability_status` | Derived by status priority: accounting, invoiced SO, delivered SO, linked SO, MO without SO, no MO follow-up, cancelled. | Status badge |
| `status_summary` | Approval/Internal Order status summary from source lines. | `vw_dashboard_internal_order_traceability` | `status_summary` | Distinct statuses aggregated per Internal Order. | Text badge/list |
| `requester` | Person/requester associated with the Internal Order. | `vw_dashboard_internal_order_traceability` | `requester` | Distinct requester names aggregated per Internal Order. | Text |
| `needed_date_from` | Earliest need/planning date for the Internal Order. | `vw_dashboard_internal_order_traceability` | `needed_date_from` | Minimum planned/needed date across lines. | Date |
| `needed_date_to` | Latest need/planning date for the Internal Order. | `vw_dashboard_internal_order_traceability` | `needed_date_to` | Maximum planned/needed date across lines. | Date |
| `line_count` | Number of approval product lines under the Internal Order. | `vw_dashboard_internal_order_traceability` | `line_count` | Count distinct Internal Order approval lines. | Integer |
| `product_count` | Number of distinct products on the Internal Order. | `vw_dashboard_internal_order_traceability` | `product_count` | Count distinct product names. | Integer |
| `linked_mo_count` | Number of Manufacturing Orders linked to the Internal Order. | `vw_dashboard_internal_order_traceability` | `linked_mo_count` | Count distinct valid MOs linked by Internal Order number. | Integer |
| `linked_so_count` | Number of Sales Orders linked to the Internal Order. | `vw_dashboard_internal_order_traceability` | `linked_so_count` | Count distinct SOs from parsed `sale_order.x_studio_io_1` bridge. | Integer |
| `linked_so_line_count` | Number of Sales Order lines linked through the Internal Order's SOs. | `vw_dashboard_internal_order_traceability` | `linked_so_line_count` | Count distinct valid SO lines. | Integer |
| `total_so_amount` | Sales value of linked SO lines. Not profitability. | `vw_dashboard_internal_order_traceability` | `total_so_amount` | Sum linked SO line `price_subtotal`. | Currency/decimal |
| `total_so_ordered_qty` | Total customer ordered quantity. | `vw_dashboard_internal_order_traceability` | `total_so_ordered_qty` | Sum linked SO line `product_uom_qty`. | Decimal quantity |
| `total_so_delivered_qty` | Total delivered quantity to customer. | `vw_dashboard_internal_order_traceability` | `total_so_delivered_qty` | Sum linked SO line `qty_delivered`. | Decimal quantity |
| `total_so_invoiced_qty` | Total invoiced quantity to customer. | `vw_dashboard_internal_order_traceability` | `total_so_invoiced_qty` | Sum linked SO line `qty_invoiced`. | Decimal quantity |
| `so_delivery_progress_ratio` | Delivery completion ratio based on SO lines. | `vw_dashboard_internal_order_traceability` | `so_delivery_progress_ratio` | `total_so_delivered_qty / total_so_ordered_qty`; null if ordered qty is zero. | Percentage |
| `so_invoice_progress_ratio` | Invoice completion ratio based on SO lines. | `vw_dashboard_internal_order_traceability` | `so_invoice_progress_ratio` | `total_so_invoiced_qty / total_so_ordered_qty`; null if ordered qty is zero. | Percentage |
| `has_delivered_so` | Whether linked SO lines have any delivered quantity. | `vw_dashboard_internal_order_traceability` | `has_delivered_so` | `total_so_delivered_qty > 0`. | Boolean/icon |
| `has_invoiced_so` | Whether linked SO lines have any invoiced quantity. | `vw_dashboard_internal_order_traceability` | `has_invoiced_so` | `total_so_invoiced_qty > 0`. | Boolean/icon |
| `delivery_status_summary` | Odoo SO delivery status summary. | `vw_dashboard_internal_order_traceability` | `delivery_status_summary` | Distinct linked SO `delivery_status` values. | Text badge/list |
| `invoice_status_summary` | Odoo SO invoice status summary. | `vw_dashboard_internal_order_traceability` | `invoice_status_summary` | Distinct linked SO `invoice_status` values. | Text badge/list |
| `linked_po_line_count` | Number of linked PO lines by Internal Order number. | `vw_dashboard_internal_order_traceability` | `linked_po_line_count` | Count distinct valid PO lines where PO line IO equals Internal Order number. | Integer |
| `total_po_ordered_qty` | Total purchased quantity ordered. | `vw_dashboard_internal_order_traceability` | `total_po_ordered_qty` | Sum linked PO line `product_qty`. | Decimal quantity |
| `total_po_received_qty` | Total purchased quantity received. | `vw_dashboard_internal_order_traceability` | `total_po_received_qty` | Sum linked PO line `qty_received`. | Decimal quantity |
| `total_po_invoiced_qty` | Total purchased quantity billed/invoiced by vendor. | `vw_dashboard_internal_order_traceability` | `total_po_invoiced_qty` | Sum linked PO line `qty_invoiced`. | Decimal quantity |
| `po_receipt_progress_ratio` | Procurement receipt completion ratio. | `vw_dashboard_internal_order_traceability` | `po_receipt_progress_ratio` | `total_po_received_qty / total_po_ordered_qty`; null if ordered qty is zero. | Percentage |
| `po_invoice_progress_ratio` | Procurement billing completion ratio. | `vw_dashboard_internal_order_traceability` | `po_invoice_progress_ratio` | `total_po_invoiced_qty / total_po_ordered_qty`; null if ordered qty is zero. | Percentage |
| `purchase_status_summary` | PO line state summary. | `vw_dashboard_internal_order_traceability` | `purchase_status_summary` | Distinct linked PO line `state` values. | Text badge/list |
| `accounting_line_count` | Number of accounting lines linked through Sales Orders. | `vw_dashboard_internal_order_traceability` | `accounting_line_count` | Count distinct valid accounting lines linked to linked SOs. | Integer |

## Optional Diagnostic Fields

These fields may be shown in an expandable diagnostic panel. They must not drive V1 readiness status.

| Field Name | Business Meaning | Source View | Source Column | Calculation Rule | Display Format |
| --- | --- | --- | --- | --- | --- |
| `manufacturing_movement_count` | Operational count of stock movements linked to Manufacturing Orders. | `vw_dashboard_internal_order_traceability` | `manufacturing_movement_count` | Sum movement counts from manufacturing flow context. | Integer |
| `finished_goods_store_count` | Optional count of finished-goods store movements. | `vw_dashboard_internal_order_traceability` | `finished_goods_store_count` | Sum finished-goods movement counts from stock movement classification. | Integer |
| `delivery_movement_count` | Optional count of delivery stock movements. | `vw_dashboard_internal_order_traceability` | `delivery_movement_count` | Sum delivery movement counts from stock movement classification. | Integer |
| `later_so_count` | Backward-compatible alias for linked SO count. | `vw_dashboard_internal_order_traceability` | `later_so_count` | Same value as `linked_so_count`. | Integer |
| `total_ordered_qty` | Backward-compatible alias for SO ordered quantity. | `vw_dashboard_internal_order_traceability` | `total_ordered_qty` | Same value as `total_so_ordered_qty`. | Decimal quantity |
| `total_delivered_qty` | Backward-compatible alias for SO delivered quantity. | `vw_dashboard_internal_order_traceability` | `total_delivered_qty` | Same value as `total_so_delivered_qty`. | Decimal quantity |
| `total_invoiced_qty` | Backward-compatible alias for SO invoiced quantity. | `vw_dashboard_internal_order_traceability` | `total_invoiced_qty` | Same value as `total_so_invoiced_qty`. | Decimal quantity |
| `delivery_progress_ratio` | Backward-compatible alias for SO delivery progress. | `vw_dashboard_internal_order_traceability` | `delivery_progress_ratio` | Same value as `so_delivery_progress_ratio`. | Percentage |
| `invoice_progress_ratio` | Backward-compatible alias for SO invoice progress. | `vw_dashboard_internal_order_traceability` | `invoice_progress_ratio` | Same value as `so_invoice_progress_ratio`. | Percentage |
| `has_delivery_from_so_line` | Backward-compatible alias for SO delivery flag. | `vw_dashboard_internal_order_traceability` | `has_delivery_from_so_line` | Same value as `has_delivered_so`. | Boolean/icon |
| `has_invoice_from_so_line` | Backward-compatible alias for SO invoice flag. | `vw_dashboard_internal_order_traceability` | `has_invoice_from_so_line` | Same value as `has_invoiced_so`. | Boolean/icon |

## Future Profitability Fields

These fields are intentionally not part of V1 traceability. They should be introduced only after profitability rules are confirmed.

| Field Name | Business Meaning | Source View | Source Column | Calculation Rule | Display Format |
| --- | --- | --- | --- | --- | --- |
| `estimator_cost` | Expected cost from estimator file. | Not available in V1 | Not available | Requires controlled Excel/import source. | Currency |
| `rkb_cost` | PPIC/RKB planned material cost. | Future RKB costing view | Not available | Requires RKB quantity, unit cost, and costing rule. | Currency |
| `actual_material_cost` | Actual consumed/issued material cost. | Future actual cost view | Not available | Requires stock valuation/material consumption source. | Currency |
| `labor_cost` | Labor cost assigned to MO/IO/SO. | Not available in V1 | Not available | Requires labor source and allocation rule. | Currency |
| `overhead_cost` | Overhead cost assigned to MO/IO/SO. | Not available in V1 | Not available | Requires overhead source and allocation rule. | Currency |
| `gross_profit` | Revenue minus agreed cost components. | Future profitability view | Not available | Do not calculate until cost rules are approved. | Currency |
| `gross_margin_pct` | Profit percentage. | Future profitability view | Not available | `gross_profit / revenue`; blocked until gross profit exists. | Percentage |

## Contract Notes

- Frontend should use `vw_dashboard_internal_order_traceability` directly for Page 1.
- Exclude or visually separate `traceability_status = CANCELLED_RECORD` from active KPI cards.
- Use quantity-based progress ratios for V1.
- Do not treat missing SO or missing MO as invalid by default; use `traceability_status` as follow-up context.
- Do not use stock movement counts as dashboard readiness criteria.
