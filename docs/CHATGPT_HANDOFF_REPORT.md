# ChatGPT Handoff Report

## 1. Task Summary

Fauzan clarified the approval-module business roles for the Odoo manufacturing dashboard:

- `approval_product_line.x_studio_category = RKB` means material planning / PPIC comparison.
- `PEMBELIAN` means ROP / Request of Purchase.
- `ROP` and `PEMBELIAN` have the same business meaning.
- `MANUFACTURE` means Internal Order.
- `INTERNAL USE` is out of current dashboard scope.

The Data Truth Layer was updated so Internal Order is no longer treated as a missing master table for v1. Instead, Internal Order is represented by `approval_product_line` rows where `x_studio_category = MANUFACTURE`.

Correction applied after validation: for MANUFACTURE approval lines, `approval_request_id` displays the Internal Order number. The primary bridge to Manufacturing Order is now:

```text
approval_product_line.approval_request_id = mrp_production.x_studio_nomor_io
```

`approval_product_line.x_studio_nomor_io` remains visible as secondary/raw context but is not the primary Internal Order bridge.

New traceability views were added to connect:

Internal Order approval lines -> Manufacturing Orders -> stock movements -> later Sales Order if inferable -> accounting if linked.

No frontend was built. No profitability calculation was added. Raw Odoo tables were not overwritten.

Latest addition: created `vw_dashboard_internal_order_traceability` in `sql/04_dashboard_traceability_views.sql`. It is dashboard-ready traceability at one row per Internal Order number.

Latest v1 dashboard correction:

- Do not use `stock_move_line` as the primary source for delivery, receipt, or invoice progress.
- Once an Internal Order links to Sales Order through parsed `sale_order.x_studio_io_1`, delivery and invoicing progress should be measured from linked SO lines:
  - `sale_order_line.product_uom_qty`
  - `sale_order_line.qty_delivered`
  - `sale_order_line.qty_invoiced`
  - `sale_order_line.price_subtotal`
  - `sale_order.delivery_status`
  - `sale_order.invoice_status`
- Where PO lines are linked by Internal Order number, procurement receipt and billing progress should be measured from linked PO lines:
  - `purchase_order_line.product_qty`
  - `purchase_order_line.qty_received`
  - `purchase_order_line.qty_invoiced`
  - `purchase_order_line.state`
- Stock movement counts are kept as optional/advanced diagnostics only.

Dashboard contract/design pass completed:

- Created `docs/DASHBOARD_DATA_CONTRACT.md`.
- Created `docs/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md`.
- Confirmed frontend development can start for Page 1 using `vw_dashboard_internal_order_traceability`.
- Page 1 remains traceability-only. No profitability calculation and no frontend code were added.

First dashboard page build completed:

- Added a read-only Internal Order Traceability Dashboard page.
- Added a JSON API endpoint backed by `vw_dashboard_internal_order_traceability`.
- Added KPI cards, filters, traceability status chips, main table, and expandable diagnostic rows.
- SO and PO line quantities remain the primary progress source.
- Stock movement counts are shown only in optional diagnostics.
- Profitability was not calculated.

Local page:

```text
http://127.0.0.1:8000/dashboard/internal-orders
```

Business confirmation from Fauzan:

- Internal Orders without MO are acceptable for v1.
- Most are old migration records, still new/to submit, or abandoned draft work.
- `INTERNAL_ORDER_WITHOUT_MO` is a traceability status / follow-up item, not invalid data.
- Stop investigating MO -> SO linkage for Internal Order flow.
- Sales Orders produced from Internal Orders are linked by `sale_order.x_studio_io_1`.
- `sale_order.x_studio_io_1` is stored as set/list text, such as `{1081}` or `{1361,1578}`.
- One SO may link to multiple Internal Orders and one Internal Order may link to multiple SOs.
- A many-to-many bridge view now parses this field into individual IDs.
- Extraction-level fix completed: `approval.product.line.approval_request_id.id` is now synced to PostgreSQL as `approval_request_numeric_id`.
- `approval.request` is now synced, giving a numeric ID to display-name mapping.

## 2. Files Changed

| File | Change |
| --- | --- |
| `config/models.yaml` | Added `approval_request_id.id` as `approval_request_numeric_id` on `approval.product.line`, and added `approval.request` sync config. |
| `src/utils/config_loader.py` | Allowed dict-style column overrides so nested fields can define `postgres_column`, `postgres_type`, and `display_name`. |
| `src/transform/path_resolver.py` | Optimized nested `.id` resolution for Odoo many2one values like `[14, '225IO001']`, avoiding one related-record read per row. |
| `src/api.py` | Added static dashboard serving, the `/dashboard/internal-orders` page route, the `/api/dashboard/internal-orders` JSON endpoint, and KPI summary helpers. |
| `src/static/dashboard/internal-orders.html` | Added the first read-only dashboard page structure. |
| `src/static/dashboard/internal-orders.css` | Added dashboard styling for KPI cards, filters, status chips, table, progress bars, and responsive layout. |
| `src/static/dashboard/internal-orders.js` | Added client-side data loading, filters, KPI recalculation, table rendering, and expandable diagnostics. |
| `requirements.txt` | Enabled FastAPI dashboard/API runtime dependencies: `fastapi`, `uvicorn`, and `python-multipart`. |
| `tests/test_dashboard_api.py` | Added KPI summary tests for cancelled-record exclusion and zero-denominator ratios. |
| `sql/01_base_views.sql` | Added `vw_approval_product_line_context`, changed `vw_rkb_planning_lines` to an RKB-only compatibility view, added `vw_internal_order_context`, added `vw_manufacturing_flow_context`, added `vw_sale_order_internal_order_bridge`, added finished-goods store movement classification, and corrected Internal Order/SO linkage to use numeric approval request IDs. |
| `sql/02_traceability_views.sql` | Updated data-quality exceptions to use all approval categories, added Internal Order exceptions, kept RKB-specific checks RKB-only. |
| `sql/03_validation_queries.sql` | Added validation counts for approval categories, Internal Order lines, IO-to-MO coverage, MO without IO/SO, manufacturing movements, finished-goods store movements, delivery movements, out-of-scope Internal Use, SO-line dashboard delivery/invoice metrics, and PO-line receipt/billing metrics. |
| `sql/04_dashboard_traceability_views.sql` | Added dashboard-ready `vw_dashboard_internal_order_traceability`, one row per Internal Order number, updated SO linkage to use the parsed many-to-many bridge, changed v1 delivery/invoice readiness to use linked SO line quantities, and added linked PO line receipt/billing progress. |
| `sql/README.md` | Documented the new approval category mapping, new views, Internal Order v1 source, SO-line delivery/invoice rule, PO-line receipt/billing rule, and updated caveats. |
| `docs/BUSINESS_FLOW.md` | Updated business flow to define Internal Order as `approval_product_line` category `MANUFACTURE` for v1 and clarified RKB vs ROP/PEMBELIAN. |
| `docs/DATA_TRUTH_LAYER_REVIEW.md` | Updated implemented rules, view list, validation snapshot, and missing-field assessment. |
| `docs/DATA_QUALITY_INVESTIGATION.md` | Documented why `MANUFACTURE` is no longer `OTHER_APPROVAL_CATEGORY` and added current Internal Order / movement counts. |
| `docs/INTERNAL_ORDER_TRACEABILITY_INVESTIGATION.md` | Documents Odoo metadata, extractor behavior, sync changes, bridge fix, recalculated counts, and remaining notes. |
| `docs/DASHBOARD_DATA_CONTRACT.md` | Defines the V1 dashboard data contract, separating required V1 fields, optional diagnostics, and future profitability fields. |
| `docs/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md` | Defines Page 1 layout, table columns, KPI cards, filters, follow-up logic, and frontend readiness. |
| `docs/CHATGPT_HANDOFF_REPORT.md` | Rewritten as this self-contained review handoff. |

## 3. Business Rule Changes

### Approval Category Mapping

| Raw category | Data Truth Layer type | Business meaning |
| --- | --- | --- |
| `RKB` | `RKB_PLANNING` | PPIC material planning and comparison. Does not directly trigger purchasing. |
| `ROP` | `ROP_PROCUREMENT_REQUEST` | Request of Purchase / procurement request. |
| `PEMBELIAN` | `ROP_PROCUREMENT_REQUEST` | Same business meaning as ROP. |
| `MANUFACTURE` | `INTERNAL_ORDER` | Internal Order source for make-to-stock manufacturing flow. |
| `INTERNAL USE` | `OUT_OF_SCOPE_INTERNAL_USE` | Excluded from current dashboard scope. |
| null, empty, `{}`, `New` | `UNKNOWN_APPROVAL_CATEGORY` | Needs data review. |
| anything else | `OTHER_APPROVAL_CATEGORY` | Needs business confirmation. |

`vw_approval_product_line_context` now contains all approval product lines and exposes:

- `approval_category_raw`
- `approval_category_normalized`
- `approval_business_type`
- `is_rkb`
- `is_rop`
- `is_internal_order`
- `is_out_of_scope`
- `is_valid_for_rkb_planning`
- `is_valid_for_procurement_request`
- `is_valid_for_internal_order_flow`

`vw_rkb_planning_lines` is retained as a compatibility view filtered to RKB rows only.

### Internal Order / Manufacturing Flow

Internal Order v1 is:

```text
approval_product_line
where x_studio_category = 'MANUFACTURE'
```

Updated flow:

```text
Internal Order approval line
-> Manufacturing Order
-> Finished Goods / stock movement
-> later Sales Order / Delivery / Invoice if linked or inferable
```

New views:

| View | Purpose |
| --- | --- |
| `vw_internal_order_context` | One row per Internal Order approval line. Includes IO number, JO number, product, quantity, status, requester, needed date, and MO link readiness. |
| `vw_manufacturing_flow_context` | Connects Internal Order approval lines to MO, stock movement classification, later SO if inferable, and accounting if linked. |
| `vw_dashboard_internal_order_traceability` | One row per Internal Order number for dashboard use. Summarizes line count, status, requester, needed date range, product count, MO count, optional movement diagnostics, linked SO count, linked SO line count, SO amount, SO ordered/delivered/invoiced quantities, SO delivery/invoice progress ratios, linked PO line count, PO ordered/received/invoiced quantities, PO receipt/invoice progress ratios, accounting count, and traceability status. |
| `vw_sale_order_internal_order_bridge` | Many-to-many parser bridge from `sale_order.x_studio_io_1`. Produces one row per SO and parsed approval request / Internal Order reference ID. |

Linking rule:

- For MANUFACTURE approval lines, use `approval_request_id` as the primary Internal Order number.
- Use `approval_request_numeric_id` as the numeric `approval.request.id`.
- Link to MO with `approval_product_line.approval_request_id = mrp_production.x_studio_nomor_io`.
- Link later SO through `vw_sale_order_internal_order_bridge.internal_order_id = approval_product_line.approval_request_numeric_id`.
- Do not infer SO directly from MO for Internal Order flow.
- Valid JO remains secondary/fallback context.
- Do not force an SO link.
- If later SO is not available, mark the flow as no SO link yet instead of guessing.
- Exclude cancelled rows from active metrics.
- Keep cancelled rows visible in data-quality exceptions.
- Internal Orders without MO are follow-up statuses, not invalid data.

### Internal Order Dashboard V1 Sales / Procurement Progress Rule

For v1, the Internal Order dashboard does not use `stock_move_line` as the primary source for finished-goods, delivery, receipt, or invoice progress.

Once an Internal Order links to one or more Sales Orders through `vw_sale_order_internal_order_bridge`, dashboard delivery and invoice progress is measured from linked SO lines:

| Metric | Source |
| --- | --- |
| `linked_so_count` | distinct linked `sale_order` rows |
| `linked_so_line_count` | linked `sale_order_line` rows |
| `total_so_amount` | sum of `sale_order_line.price_subtotal` |
| `total_so_ordered_qty` | sum of `sale_order_line.product_uom_qty` |
| `total_so_delivered_qty` | sum of `sale_order_line.qty_delivered` |
| `total_so_invoiced_qty` | sum of `sale_order_line.qty_invoiced` |
| `so_delivery_progress_ratio` | SO delivered quantity / SO ordered quantity |
| `so_invoice_progress_ratio` | SO invoiced quantity / SO ordered quantity |
| `has_delivered_so` | SO delivered quantity > 0 |
| `has_invoiced_so` | SO invoiced quantity > 0 |

Where linked PO lines exist, procurement receipt and invoice progress is measured from linked PO lines:

| Metric | Source |
| --- | --- |
| `linked_po_line_count` | linked `purchase_order_line` rows |
| `total_po_ordered_qty` | sum of `purchase_order_line.product_qty` |
| `total_po_received_qty` | sum of `purchase_order_line.qty_received` |
| `total_po_invoiced_qty` | sum of `purchase_order_line.qty_invoiced` |
| `po_receipt_progress_ratio` | PO received quantity / PO ordered quantity |
| `po_invoice_progress_ratio` | PO invoiced quantity / PO ordered quantity |

`manufacturing_movement_count`, `finished_goods_store_count`, and `delivery_movement_count` remain available in the dashboard view as optional diagnostic fields only.

Traceability status priority is now:

1. `CANCELLED_RECORD`
2. `HAS_ACCOUNTING_LINK`
3. `HAS_INVOICED_SO`
4. `HAS_DELIVERED_SO`
5. `HAS_LINKED_SO`
6. `HAS_MO_NO_SO_YET`
7. `NEW_OR_TO_SUBMIT_NO_MO`
8. `OLD_OR_UNLINKED_NO_MO`

### Source Classification

Sales Order source classification remains line-first:

| Rule | Source type |
| --- | --- |
| `sale_order.x_studio_io_1` is filled | `FROM_INTERNAL_ORDER` |
| line has both inferred MO and delivery movement | `MIXED_SOURCE` |
| line/product has inferred MO from SO origin and product | `MAKE_TO_ORDER` |
| line has delivery movement and no inferred MO | `FROM_STOCK` |
| line has only unknown movement evidence | `NEEDS_MOVEMENT_CLASSIFICATION` |
| no IO, MO, or delivery evidence | `UNKNOWN_SOURCE` |

Header SO source is rolled up from line source:

- all lines same type -> same SO type
- multiple line types -> `MIXED_SOURCE`

### Status / Cancelled Logic

Cancelled records are excluded from active operational metrics, active traceability metrics, and future profitability inputs.

Cancelled records stay visible in audit/data-quality views as `CANCELLED_RECORD`.

Status fields currently used:

| Module | Field |
| --- | --- |
| Sales | `sale_order.state` |
| Sales line | inherits `sale_order.state` |
| Manufacturing | `mrp_production.state` |
| Approval line | `approval_product_line.x_studio_status` |
| Procurement | `purchase_order_line.state` |
| Stock | `stock_move_line.state` |
| Accounting | `account_move_line.parent_state` |

### JO Normalization

JO fields often contain `New`, which is a placeholder and must be treated as null.

Valid JO:

- not null
- not empty
- not `New`
- exactly 7 digits
- no text

Applies to:

- `mrp_production.x_studio_nomor_jo`
- `approval_product_line.x_studio_nomor_jo`
- `purchase_order_line.x_studio_jo`

### Accounting / SO Mapping

Accounting-to-SO mapping uses SO number, not SO numeric ID:

```text
normalized account_move_line.x_studio_sales_order = sale_order.name::text
```

`x_studio_sales_order = 'New'` is treated as null.

### Stock Movement Classification

`stock_move_line.picking_type_id` is a text/display label and is classified by keyword:

| Picking type contains | Movement type |
| --- | --- |
| `Store Finished Product`, `Finished Goods`, `Finished Product` | `FINISHED_GOODS_STORE` |
| `OUT`, `Delivery`, `Customer`, `Keluar` | `DELIVERY` |
| `Receipt`, `Vendor`, `Terima` | `RECEIPT` |
| `Internal`, `INT`, `Transfer` | `INTERNAL_TRANSFER` |
| `Manufacturing`, `Production`, `Pick Components`, `MO`, `MRP` | `MANUFACTURING` |
| otherwise | `UNKNOWN_MOVEMENT_TYPE` |

`FROM_STOCK` uses delivery movement evidence only. Receipts, internal transfers, and manufacturing movements are not treated as customer fulfillment.

## 4. Validation Results

### Dashboard Contract Summary

The first dashboard page should use one primary view:

```text
vw_dashboard_internal_order_traceability
```

Required V1 field groups:

| Group | Fields |
| --- | --- |
| Internal Order identity | `internal_order_number`, `status_summary`, `requester`, `needed_date_from`, `needed_date_to`, `line_count`, `product_count` |
| Manufacturing traceability | `linked_mo_count` |
| Sales traceability | `linked_so_count`, `linked_so_line_count`, `total_so_amount` |
| Sales progress | `total_so_ordered_qty`, `total_so_delivered_qty`, `total_so_invoiced_qty`, `so_delivery_progress_ratio`, `so_invoice_progress_ratio`, `has_delivered_so`, `has_invoiced_so` |
| Procurement progress | `linked_po_line_count`, `total_po_ordered_qty`, `total_po_received_qty`, `total_po_invoiced_qty`, `po_receipt_progress_ratio`, `po_invoice_progress_ratio` |
| Accounting traceability | `accounting_line_count` |
| Follow-up status | `traceability_status` |

Optional diagnostic fields:

| Group | Fields |
| --- | --- |
| Stock movement diagnostics | `manufacturing_movement_count`, `finished_goods_store_count`, `delivery_movement_count` |
| Compatibility aliases | `later_so_count`, `total_ordered_qty`, `total_delivered_qty`, `total_invoiced_qty`, `delivery_progress_ratio`, `invoice_progress_ratio`, `has_delivery_from_so_line`, `has_invoice_from_so_line` |

Future profitability fields are documented but intentionally not implemented: estimator cost, RKB cost, actual material cost, labor cost, overhead cost, gross profit, and margin percentage.

### Dashboard Page 1 Design Summary

Page name:

```text
Internal Order Traceability Dashboard
```

Main table columns:

| Area | Columns |
| --- | --- |
| Identity | Internal Order Number, Status, Requester, Need Date, Product Count |
| Traceability | MO Count, SO Count, Accounting Line Count, Traceability Status |
| Sales Progress | SO Ordered Qty, SO Delivered Qty, SO Invoiced Qty, Delivery %, Invoice % |
| Procurement Progress | PO Ordered Qty, PO Received Qty, PO Invoiced Qty, Receipt %, Billing % |

KPI cards:

| KPI | Formula |
| --- | --- |
| Active Internal Orders | `COUNT(*) WHERE traceability_status <> 'CANCELLED_RECORD'` |
| Internal Orders With MO | active rows with `linked_mo_count > 0` |
| Internal Orders With SO | active rows with `linked_so_count > 0` |
| Internal Orders Delivered | active rows with `has_delivered_so` |
| Internal Orders Invoiced | active rows with `has_invoiced_so` |
| Delivery Progress % | `SUM(total_so_delivered_qty) / SUM(total_so_ordered_qty)` |
| Invoice Progress % | `SUM(total_so_invoiced_qty) / SUM(total_so_ordered_qty)` |
| Procurement Receipt Progress % | `SUM(total_po_received_qty) / SUM(total_po_ordered_qty)` |
| Procurement Billing Progress % | `SUM(total_po_invoiced_qty) / SUM(total_po_ordered_qty)` |

Filters:

| Filter | Field |
| --- | --- |
| Date Range | `needed_date_from`, `needed_date_to` |
| Internal Order Number | `internal_order_number` |
| Requester | `requester` |
| Product | limited in V1 at summary grain; product drill-down can come later |
| Status | `status_summary` |
| Traceability Status | `traceability_status` |

Can frontend start?

YES for Page 1. No backend changes are required before building the first read-only Internal Order Traceability Dashboard. Profitability and product-level drill-down remain later milestones.

Frontend Page 1 has now started and the first read-only implementation is working locally.

Implemented screen areas:

| Area | Implemented |
| --- | --- |
| KPI cards | Active IO, With MO, With SO, Delivered, Invoiced, Delivery Progress, Invoice Progress, PO Receipt, PO Billing |
| Filters | Date range, Internal Order number, requester, status, traceability status |
| Status chips | Counts by traceability status |
| Main table | IO identity, status, requester, need date, product count, MO/SO counts, SO progress, PO progress, accounting count, traceability status |
| Diagnostics | Expandable row detail with SO lines, SO amount, delivery/invoice status, PO lines, purchase status, IO lines, and stock movement diagnostic counts |

Latest validation was run after applying:

1. `sql/01_base_views.sql`
2. `sql/02_traceability_views.sql`
3. `sql/04_dashboard_traceability_views.sql`
4. focused dashboard validation queries

`sql/03_validation_queries.sql` was updated and parse-checked successfully with PostgreSQL `PREPARE`. A full execution attempt exceeded 120 seconds because the report includes broad stock/accounting groupings, so the dashboard counts below come from focused validation queries against `vw_dashboard_internal_order_traceability`.

### Sales / SO Traceability

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

### Approval Categories

| Metric | Count |
| --- | ---: |
| approval_category_rkb_planning | 27,375 |
| approval_category_rop_procurement_request | 14,184 |
| approval_category_internal_order | 1,023 |
| approval_category_out_of_scope_internal_use | 50 |
| approval_category_unknown_approval_category | 24 |
| other_approval_category_count | 0 |

### Internal Order / Manufacturing Flow

| Metric | Count |
| --- | ---: |
| active_internal_order_lines | 1,023 |
| active_internal_order_lines_with_io_number | 1,023 |
| active_internal_order_lines_with_valid_jo | 0 |
| active_internal_order_lines_linked_to_mo | 817 |
| active_internal_order_lines_not_linked_to_mo | 206 |
| active_mo_count | 10,048 |
| active_mo_with_io | 1,205 |
| active_mo_linked_to_internal_order | 1,204 |
| active_mo_without_so | 1,609 |
| active_mo_not_linked_to_internal_order_or_so | 243 |
| active_mo_invalid_both_so_and_io | 0 |
| active_mo_invalid_both_io_and_jo | 31 |
| active_mo_invalid_jo_format | 1 |

### Dashboard Internal Order Traceability

`vw_dashboard_internal_order_traceability` was applied successfully.

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
| Tests | `46 passed` |

Focused tests run:

```text
.\venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py tests/test_startup_validation.py tests/test_transform_path_resolver.py -q
```

Summary:

| Metric | Count |
| --- | ---: |
| approval_request synced rows | 2,947 |
| approval_product_line rows with `approval_request_numeric_id` | 42,902 |
| internal_order_count | 116 |
| line_count | 1,024 |
| linked_mo_count | 1,205 |
| linked_so_count | 222 |
| linked_so_line_count | 1,079 |
| total_so_amount | 81,070,144,484.01 |
| total_so_ordered_qty | 82,767 |
| total_so_delivered_qty | 80,137 |
| total_so_invoiced_qty | 80,161 |
| so_delivery_progress_ratio | 96.82% |
| so_invoice_progress_ratio | 96.85% |
| internal_orders_with_delivered_so | 81 |
| internal_orders_with_invoiced_so | 82 |
| linked_po_line_count | 3,023 |
| total_po_ordered_qty | 3,101,397.42 |
| total_po_received_qty | 2,993,590.72 |
| total_po_invoiced_qty | 3,020,218.42 |
| po_receipt_progress_ratio | 96.52% |
| po_invoice_progress_ratio | 97.38% |
| accounting_line_count | 3,449 |
| manufacturing_movement_count | 589,133 |
| finished_goods_store_count | 0, diagnostic only |
| delivery_movement_count | 0, diagnostic only |
| sale_order_internal_order_bridge_rows | 222 |
| sale_orders_with_internal_order_bridge | 211 |
| distinct parsed Internal Order IDs from SO | 88 |
| internal_orders_with_later_so | 88 |
| internal_orders_without_later_so | 28 |

Traceability status distribution:

| Traceability status | Internal Order count |
| --- | ---: |
| `CANCELLED_RECORD` | 1 |
| `HAS_ACCOUNTING_LINK` | 82 |
| `HAS_DELIVERED_SO` | 1 |
| `HAS_LINKED_SO` | 5 |
| `HAS_MO_NO_SO_YET` | 18 |
| `NEW_OR_TO_SUBMIT_NO_MO` | 9 |

### RKB / ROP / Procurement

| Metric | Count |
| --- | ---: |
| active_rkb_count | 27,375 |
| active_rkb_lines_with_io_or_jo | 26,973 |
| active_rkb_invalid_both_io_and_jo | 0 |
| active_rkb_invalid_jo_format | 0 |
| active_rkb_unlinked | 402 |
| cancelled_rkb_count | 59 |
| active_rop_count | 14,184 |
| active_rop_lines_with_io_or_jo | 10,817 |
| active_po_count | 18,468 |
| cancelled_po_count | 2,488 |
| active_po_lines_with_io_or_jo | 10,836 |
| active_po_invalid_both_io_and_jo | 11 |
| active_po_invalid_jo_format | 0 |
| active_po_unlinked | 7,632 |

### Stock / Accounting

| Metric | Count |
| --- | ---: |
| active_stock_move_line_count | 225,420 |
| cancelled_stock_move_line_count | 340 |
| stock_movement_type_manufacturing | 163,635 |
| stock_movement_type_delivery | 8,584 |
| stock_movement_type_finished_goods_store | 8,110 |
| stock_movement_type_receipt | 17,705 |
| stock_movement_type_internal_transfer | 3,865 |
| stock_movement_type_unknown_movement_type | 23,521 |
| active_accounting_line_count | 417,947 |
| cancelled_accounting_line_count | 3,698 |
| active_accounting_lines_linked_to_so | 28,956 |
| accounting_lines_x_studio_sales_order_new | 390,172 |
| active_accounting_lines_unmatched_non_new_so_number | 26 |

## 5. Data Quality Exceptions

Verification:

- Targeted full sync completed for `approval.product.line` and `approval.request`.
- `pytest tests/test_transform_path_resolver.py tests/test_startup_validation.py -q` passed: 44 tests passed.
- Database validation confirmed `approval_request` has 2,947 rows and `approval_product_line.approval_request_numeric_id` is populated on 42,902 rows.

Important detectable exceptions now include:

| Exception area | Current count / status |
| --- | ---: |
| unknown approval category | 24 |
| other approval category | 0 |
| active Internal Order lines not linked to MO | 206, now treated as status/follow-up, not invalid data |
| active Internal Order lines with IO number | 1,023 |
| active Internal Order lines with valid JO | 0 |
| active MO has both SO and IO | 0 |
| active MO has both IO and JO | 31 |
| active MO invalid JO format | 1 |
| active RKB unlinked | 402 |
| active PO line has both IO and JO | 11 |
| active PO line unlinked | 7,632 |
| active SO mixed source | 797 |
| active SO unknown source | 80 |
| active SO line unknown source | 2,567 |
| active SO line needs movement classification | 0 |
| active accounting line unmatched non-New SO number | 26 |

Important interpretation:

- `MANUFACTURE` is no longer an exception. It is Internal Order.
- `INTERNAL USE` is not an exception. It is out of current dashboard scope.
- RKB is now RKB-only because `vw_rkb_planning_lines` filters `is_rkb`.
- The corrected `approval_request_id` bridge reduced unlinked Internal Order lines from 1,000 to 206.
- Fauzan confirmed remaining Internal Orders without MO are acceptable for v1 and should appear as traceability statuses, not data errors.
- Fauzan confirmed later SO linkage should use parsed `sale_order.x_studio_io_1`, not MO-derived SO inference.
- The parser found 222 SO-to-IO bridge rows across 211 SOs.
- After syncing `approval_request_numeric_id`, the dashboard now links 88 Internal Orders to later SOs.
- Dashboard `later_so_count` improved from 0 to 222.
- Dashboard `accounting_line_count` improved from 0 to 3,449.
- Dashboard delivery/invoice progress now comes from linked SO lines, not stock movement proof.
- Dashboard procurement receipt/billing progress now comes from linked PO lines, not stock movement proof.
- The view now finds 81 Internal Orders with delivered SO line quantity and 82 Internal Orders with invoiced SO line quantity.
- The view now finds 3,023 linked PO lines by Internal Order number.
- `x_studio_sales_order = 'New'` is treated as no SO reference, not an error by itself.

## 6. Ambiguities / Questions for Fauzan

1. Should dashboard SO delivery/invoice progress ratios and PO receipt/invoice progress ratios be quantity-based as implemented, amount-based, or both?
2. Should `sale_order.delivery_status` and `sale_order.invoice_status` override quantity-based flags when they disagree?
3. Should `purchase_order_line.state` be enough for PO readiness, or should purchase header status be synced later?
4. 28 dashboard Internal Orders still have no later SO after the numeric bridge fix. Are these expected old/new/abandoned records, or should some have SO links?
5. Why do active Internal Order lines have zero valid JO values? Is JO not used for this flow, or is another JO field needed?
6. Should `approval_product_line.x_studio_nomor_io` still be used for any MANUFACTURE logic, or only displayed as secondary/raw context?
7. Should `Store Finished Product` / delivery stock movement diagnostics be investigated later as advanced traceability, or ignored for v1?
8. Should `Pick Components` be classified as manufacturing movement or material issue/subcomponent consumption in a future version?
9. Is `approval_product_line.x_studio_status = approved` enough for ROP readiness, or do we need `approval_request.state`?
10. Which accounting accounts should count as revenue, AR, COGS, or other profitability components later?

## 7. Suggestions for ChatGPT

ChatGPT should review:

- Whether `MANUFACTURE` as Internal Order fully replaces the missing master-table assumption for v1.
- Whether `approval_request_id` as Internal Order number fully solves the v1 Internal Order bridge.
- Whether the new dashboard traceability status labels are useful for operations.
- Whether SO-line delivered/invoiced quantities are sufficient as the v1 proof for delivery and invoicing.
- Whether PO-line received/invoiced quantities are sufficient as the v1 proof for procurement receipt and billing.
- Whether `Store Finished Product` should remain its own movement type.
- Whether the remaining 28 dashboard Internal Orders without later SO are expected for v1.

Risk areas:

- Internal Order -> MO link is inferred by `approval_request_id = mrp_production.x_studio_nomor_io` for MANUFACTURE approval lines. Coverage improved to 817 of 1,023 active Internal Order lines.
- A single Internal Order line can link to multiple MOs, which may be correct or may overstate linkage if IO numbers are broad.
- The dashboard view currently treats stock movement counts as optional diagnostics only. Delivery/invoicing status is driven by linked SO lines and procurement receipt/billing progress is driven by linked PO lines for v1.
- Later SO linkage now uses a parsed many-to-many bridge from `sale_order.x_studio_io_1` matched to `approval_request_numeric_id`.
- Accounting line mapping is corrected to SO name, but accounting category meaning still needs account/header classification.
- Profitability is not ready until estimator cost, actual valuation, labor, overhead, and accounting categories are defined.

Frontend readiness:

- A read-only Internal Order traceability dashboard can start from `vw_dashboard_internal_order_traceability`. It now has linked SO amount, SO ordered/delivered/invoiced quantities, SO delivery/invoice progress ratios, PO ordered/received/invoiced quantities, PO receipt/invoice progress ratios, and accounting link counts.
- A profitability dashboard is not ready.
- The safest first page is an Internal Order / Manufacturing Traceability review page, with clear status labels and no profitability.

## 8. Suggested Next Codex Task

Recommended next prompt:

```text
Read docs/CHATGPT_HANDOFF_REPORT.md first.

Review and refine the first read-only Internal Order Traceability Dashboard page after business-user feedback.

Read:
- docs/CHATGPT_HANDOFF_REPORT.md
- docs/DASHBOARD_DATA_CONTRACT.md
- docs/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md

Task:
- Review the working dashboard page with business feedback.
- Remove unused or confusing columns from the main table.
- Keep removed fields available only in diagnostics if still useful.
- Add the first drill-down only after the column set is confirmed.
- Do not calculate profitability.
- Do not overwrite raw tables.

Rules:
- Use only existing Data Truth Layer views.
- Do not overwrite raw Odoo tables.
- Do not calculate profitability.
- Do not create new business relationships.
- Mark optional diagnostic fields clearly.
- Exclude cancelled rows from active metrics but keep cancelled status visible.

Also update:
- docs/CHATGPT_HANDOFF_REPORT.md

After the dashboard is reviewed, only then start the profitability phase.
```
