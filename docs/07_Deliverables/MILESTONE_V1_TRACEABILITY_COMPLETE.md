# Milestone V1 Traceability Complete

## 1. Scope

V1 closes the Internal Order Traceability Dashboard milestone.

Completed scope:

- Internal Order Traceability
- Manufacturing Traceability
- Sales Order Traceability
- Delivery Progress Tracking
- Invoice Progress Tracking
- Procurement Receipt Tracking
- Procurement Billing Tracking
- Dashboard Page 1

Out of scope for V1:

- Profitability Engine
- Estimator vs Actual
- Cost Variance Analysis
- Material Costing
- Margin Analysis
- Revenue Classification
- COGS Classification

## 2. Business Flow

Business glossary:

| Term | Meaning |
| --- | --- |
| SO | Sales Order |
| JO | Job Order. Factory terminology for a production-required Sales Order. Every JO is an SO, but not every SO is a JO. |
| IO | Internal Order. Internal make-to-stock production before customer SO exists. |
| RKB | PPIC material planning |
| ROP / PEMBELIAN | Procurement request |

Confirmed V1 traceability flow:

```text
Internal Order
-> Manufacturing Order
-> Sales Order
-> Delivery Progress
-> Invoice Progress
-> Accounting
```

Sales Order linkage:

```text
sale_order.x_studio_io_1
-> approval_request.id
-> approval_request.name
-> approval_product_line
```

Progress source rules:

- Delivery progress uses `sale_order_line.qty_delivered`.
- Invoice progress uses `sale_order_line.qty_invoiced`.
- Procurement receipt progress uses `purchase_order_line.qty_received`.
- Procurement billing progress uses `purchase_order_line.qty_invoiced`.
- Stock movements remain optional diagnostics only.

## 3. Data Truth Layer Summary

Primary dashboard view:

```text
vw_dashboard_internal_order_traceability
```

Supporting V1 views:

- `vw_approval_product_line_context`
- `vw_internal_order_context`
- `vw_mrp_order_context`
- `vw_sale_order_internal_order_bridge`
- `vw_manufacturing_flow_context`
- `vw_sales_order_revenue`
- `vw_procurement_lines`
- `vw_accounting_sales_lines`

Key confirmed rules:

- IO is represented by `approval_product_line` where category = `MANUFACTURE`.
- For MANUFACTURE approval lines, `approval_request_id` is the Internal Order number.
- `approval_request_numeric_id` maps to numeric `approval.request.id`.
- SO to IO is many-to-many through parsed `sale_order.x_studio_io_1`.
- JO is a production-required SO reference, not a separate entity from SO.
- Cancelled records are visible for audit but excluded from active metrics.

## 4. Dashboard Summary

Dashboard page:

```text
Internal Order Traceability Dashboard
```

Local route:

```text
http://127.0.0.1:8000/dashboard/internal-orders
```

JSON API:

```text
/api/dashboard/internal-orders
```

Implemented dashboard features:

- KPI cards
- Date, IO, requester, status, and traceability filters
- Traceability status chips
- Main Internal Order table
- SO delivery and invoice progress
- PO receipt and billing progress
- Expandable diagnostic rows

Diagnostic-only fields:

- `manufacturing_movement_count`
- `finished_goods_store_count`
- `delivery_movement_count`

## 5. Validation Results

Dashboard implementation verification:

| Check | Result |
| --- | --- |
| HTML route `/dashboard/internal-orders` | HTTP 200 |
| JSON route `/api/dashboard/internal-orders` | HTTP 200 |
| API row count | 116 |
| Active IO KPI | 115 |
| With MO KPI | 101 |
| With SO KPI | 88 |
| Browser check | Chrome/Playwright fallback loaded page successfully |
| Detail row interaction | First row diagnostics expanded successfully |
| Desktop screenshot | `reports/internal-order-dashboard.png` |
| Mobile screenshot | `reports/internal-order-dashboard-mobile.png` |

Focused tests:

```text
.\venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_startup_validation.py tests/test_transform_path_resolver.py -q
```

Result:

```text
46 passed
```

Dashboard data snapshot:

| Metric | Count |
| --- | ---: |
| internal_order_count | 116 |
| active_internal_orders | 115 |
| linked_mo_count | 1,205 |
| linked_so_count | 222 |
| linked_so_line_count | 1,079 |
| internal_orders_with_later_so | 88 |
| internal_orders_without_later_so | 28 |
| total_so_ordered_qty | 82,767 |
| total_so_delivered_qty | 80,137 |
| total_so_invoiced_qty | 80,161 |
| so_delivery_progress_ratio | 96.82% |
| so_invoice_progress_ratio | 96.85% |
| linked_po_line_count | 3,023 |
| total_po_ordered_qty | 3,101,397.42 |
| total_po_received_qty | 2,993,590.72 |
| total_po_invoiced_qty | 3,020,218.42 |
| po_receipt_progress_ratio | 96.52% |
| po_invoice_progress_ratio | 97.38% |
| accounting_line_count | 3,449 |

## 6. Known Limitations

- Product filtering is limited at the one-row-per-Internal-Order dashboard grain.
- Accounting line count proves accounting linkage, not AR collection or payment state.
- Quantity progress is not profitability.
- Stock movement counts are optional diagnostics and should not be treated as readiness criteria.
- Some old/new/abandoned Internal Orders may have no MO or SO and should be reviewed as follow-up statuses, not invalid data.

## 7. Deferred Work

- Remove unused dashboard columns after business-user review.
- Add drill-downs after the V1 column set is confirmed.
- Add product-level detail only after deciding the required drill-down grain.
- Add profitability only after business review of traceability.

Not yet implemented:

- Profitability Engine
- Estimator vs Actual
- Cost Variance Analysis
- Material Costing
- Margin Analysis
- Revenue Classification
- COGS Classification

## 8. Next Phase

Next phase:

```text
Profitability Engine
```

Planned future flow:

```text
Estimator
-> RKB
-> Procurement Actual
-> Manufacturing
-> Revenue
-> Margin
```

Do not start the profitability phase until the V1 dashboard has been reviewed with business users, unused columns have been removed, and the first drill-down has been defined.
