# Dashboard Page 1 - Internal Order Traceability

## Page Name

Internal Order Traceability Dashboard

## Purpose

This page gives operations and management a single view of Internal Orders from manufacturing through later Sales Order, delivery progress, invoice progress, procurement receipt, procurement billing, and accounting linkage.

The page is traceability-only. It does not calculate profitability.

Primary source:

```text
vw_dashboard_internal_order_traceability
```

## Questions Answered

1. Which Internal Orders exist?
2. Which Internal Orders already have Manufacturing Orders?
3. Which Internal Orders already have Sales Orders?
4. How much customer quantity has been ordered?
5. How much customer quantity has been delivered?
6. How much customer quantity has been invoiced?
7. How much procurement has been received?
8. How much procurement has been billed?
9. Which Internal Orders require follow-up?

## Main Table Columns

| Column | Source Column | Display Format | Notes |
| --- | --- | --- | --- |
| Internal Order Number | `internal_order_number` | Text link | Primary row identifier. |
| Status | `status_summary` | Badge/list | Source approval/status summary. |
| Requester | `requester` | Text | Use blank/unknown state when null. |
| Need Date | `needed_date_from`, `needed_date_to` | Date or date range | If equal, show one date. |
| Product Count | `product_count` | Integer | Count of distinct products. |
| MO Count | `linked_mo_count` | Integer | Shows whether manufacturing exists. |
| SO Count | `linked_so_count` | Integer | Shows whether later SO exists. |
| SO Ordered Qty | `total_so_ordered_qty` | Decimal quantity | Customer ordered quantity. |
| SO Delivered Qty | `total_so_delivered_qty` | Decimal quantity | Customer delivered quantity from SO lines. |
| SO Invoiced Qty | `total_so_invoiced_qty` | Decimal quantity | Customer invoiced quantity from SO lines. |
| Delivery % | `so_delivery_progress_ratio` | Percentage | Use progress bar. |
| Invoice % | `so_invoice_progress_ratio` | Percentage | Use progress bar. |
| PO Ordered Qty | `total_po_ordered_qty` | Decimal quantity | Procurement ordered quantity. |
| PO Received Qty | `total_po_received_qty` | Decimal quantity | Procurement received quantity from PO lines. |
| PO Invoiced Qty | `total_po_invoiced_qty` | Decimal quantity | Procurement billed quantity from PO lines. |
| Receipt % | `po_receipt_progress_ratio` | Percentage | Use progress bar. |
| Billing % | `po_invoice_progress_ratio` | Percentage | Use progress bar. |
| Accounting Lines | `accounting_line_count` | Integer | Indicates accounting linkage through SO. |
| Traceability Status | `traceability_status` | Status badge | Main follow-up/status label. |

## Optional Row Detail / Diagnostic Panel

Show these only when a user expands a row or opens a detail drawer:

| Field | Source Column | Purpose |
| --- | --- | --- |
| Line Count | `line_count` | Shows number of Internal Order approval lines. |
| Linked SO Line Count | `linked_so_line_count` | Explains SO quantity aggregation. |
| Total SO Amount | `total_so_amount` | Sales value traceability, not profitability. |
| Delivery Status Summary | `delivery_status_summary` | Odoo delivery status context. |
| Invoice Status Summary | `invoice_status_summary` | Odoo invoice status context. |
| Linked PO Line Count | `linked_po_line_count` | Explains PO quantity aggregation. |
| Purchase Status Summary | `purchase_status_summary` | PO state context. |
| Manufacturing Movement Count | `manufacturing_movement_count` | Optional stock movement diagnostic. |
| Finished Goods Store Count | `finished_goods_store_count` | Optional stock movement diagnostic. |
| Delivery Movement Count | `delivery_movement_count` | Optional stock movement diagnostic. |

Stock movement counts must not be used to determine V1 readiness status.

## Traceability Status Behavior

Use `traceability_status` directly from the view.

Recommended display order:

| Status | Meaning | Suggested UI Treatment |
| --- | --- | --- |
| `HAS_ACCOUNTING_LINK` | Linked SO already has accounting lines. | Success/complete |
| `HAS_INVOICED_SO` | Linked SO has invoiced quantity but no accounting link yet. | Good/progress |
| `HAS_DELIVERED_SO` | Linked SO has delivered quantity but no invoice yet. | Good/progress |
| `HAS_LINKED_SO` | SO exists, but no delivered/invoiced quantity yet. | In progress |
| `HAS_MO_NO_SO_YET` | MO exists, but no later SO link yet. | Follow-up |
| `NEW_OR_TO_SUBMIT_NO_MO` | Internal Order exists but appears new/draft/to submit and has no MO. | Follow-up |
| `OLD_OR_UNLINKED_NO_MO` | Internal Order has no MO and is not clearly new/draft. | Review |
| `CANCELLED_RECORD` | Cancelled source record. | Muted/excluded from active KPI cards |

## KPI Cards

All KPI cards use `vw_dashboard_internal_order_traceability`.

| KPI Card | Formula | Display Format |
| --- | --- | --- |
| Active Internal Orders | `COUNT(*) WHERE traceability_status <> 'CANCELLED_RECORD'` | Integer |
| Internal Orders With MO | `COUNT(*) WHERE traceability_status <> 'CANCELLED_RECORD' AND linked_mo_count > 0` | Integer |
| Internal Orders With SO | `COUNT(*) WHERE traceability_status <> 'CANCELLED_RECORD' AND linked_so_count > 0` | Integer |
| Internal Orders Delivered | `COUNT(*) WHERE traceability_status <> 'CANCELLED_RECORD' AND has_delivered_so` | Integer |
| Internal Orders Invoiced | `COUNT(*) WHERE traceability_status <> 'CANCELLED_RECORD' AND has_invoiced_so` | Integer |
| Delivery Progress % | `SUM(total_so_delivered_qty) / SUM(total_so_ordered_qty)` for active rows; null if denominator is zero. | Percentage |
| Invoice Progress % | `SUM(total_so_invoiced_qty) / SUM(total_so_ordered_qty)` for active rows; null if denominator is zero. | Percentage |
| Procurement Receipt Progress % | `SUM(total_po_received_qty) / SUM(total_po_ordered_qty)` for active rows; null if denominator is zero. | Percentage |
| Procurement Billing Progress % | `SUM(total_po_invoiced_qty) / SUM(total_po_ordered_qty)` for active rows; null if denominator is zero. | Percentage |

Recommended default KPI behavior:

- Exclude `CANCELLED_RECORD`.
- Respect all active dashboard filters.
- Use weighted ratios from summed quantities, not average of row-level percentages.

## Filters

| Filter | Source Column | Behavior |
| --- | --- | --- |
| Date Range | `needed_date_from`, `needed_date_to` | Include rows whose needed date range overlaps the selected dashboard date range. |
| Internal Order Number | `internal_order_number` | Search/contains text filter. |
| Requester | `requester` | Multi-select from available requester values. |
| Product | `product_count` for V1 summary; product detail requires drill-down later. | For V1, product filter is limited unless product-level detail is added. Show as future/disabled or use detail view later. |
| Status | `status_summary` | Multi-select source status summary. |
| Traceability Status | `traceability_status` | Multi-select operational status. |

## Follow-Up Logic

Rows that require attention:

| Condition | Follow-Up Meaning |
| --- | --- |
| `traceability_status = 'HAS_MO_NO_SO_YET'` | Produced/planned internally but no later SO link yet. |
| `traceability_status = 'NEW_OR_TO_SUBMIT_NO_MO'` | New/draft/to submit Internal Order, no MO yet. |
| `traceability_status = 'OLD_OR_UNLINKED_NO_MO'` | Internal Order has no MO and may need review. |
| `linked_so_count > 0 AND NOT has_delivered_so` | SO exists but no delivered quantity yet. |
| `has_delivered_so AND NOT has_invoiced_so` | Delivered but not invoiced. |
| `linked_po_line_count > 0 AND po_receipt_progress_ratio < 1` | Procurement not fully received. |
| `linked_po_line_count > 0 AND po_invoice_progress_ratio < 1` | Procurement not fully billed. |

## Frontend Status

YES. Page 1 has been implemented as the first read-only Internal Order Traceability Dashboard.

The page is ready for business-user review because:

- The V1 Data Truth Layer is stable.
- The page has one primary source view.
- Required traceability, SO progress, PO progress, and accounting link fields exist.
- Stock movement diagnostics are optional and not required for readiness.
- Profitability is explicitly out of scope.

Remaining blockers:

- Product filtering is limited at the one-row-per-Internal-Order grain unless a product drill-down view is added later.
- Quantity ratios are V1 business progress metrics, not financial profitability.
- Accounting line count proves linkage, not payment/AR state.
- Cancelled records need clear UI treatment and should be excluded from active KPI cards.

Required backend changes before frontend:

- None for Page 1.

Recommended next milestone:

Review the working dashboard with business users, remove unused or confusing columns, then add the first drill-down. Start profitability only after the traceability page is accepted.
