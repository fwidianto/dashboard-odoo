# ChatGPT Handoff Report

## 1. Task Summary

Fauzan clarified the approval-module business roles for the Odoo manufacturing dashboard:

- `approval_product_line.x_studio_category = RKB` means material planning / PPIC comparison.
- `PEMBELIAN` means ROP / Request of Purchase.
- `ROP` and `PEMBELIAN` have the same business meaning.
- `MANUFACTURE` means Internal Order.
- `INTERNAL USE` is out of current dashboard scope.

Fauzan also clarified JO terminology:

- JO means Job Order.
- Every JO is an SO.
- Not every SO is a JO.
- JO is factory terminology for a Sales Order that requires production.
- If an SO uses finished goods already produced from Internal Order, then it is not treated as JO.
- If an SO requires new production, factory users call it JO.

Glossary:

| Term | Meaning |
| --- | --- |
| SO | Sales Order. Customer demand and revenue document. |
| JO | Job Order. Production-required SO. |
| IO | Internal Order. Internal make-to-stock production before customer SO exists. |
| RKB | PPIC material planning. |
| ROP / PEMBELIAN | Procurement request / Request of Purchase. |

SO source interpretation:

| SO source | Meaning |
| --- | --- |
| FROM_INTERNAL_ORDER | SO linked to IO, no new MO should be needed. |
| MAKE_TO_ORDER / JO | SO requires production and creates or links to MO. |
| FROM_STOCK | SO delivered from available stock without IO/MO. |

The Data Truth Layer was updated so Internal Order is no longer treated as a missing master table for v1. Instead, Internal Order is represented by `approval_product_line` rows where `x_studio_category = MANUFACTURE`.

Correction applied after validation: for MANUFACTURE approval lines, `approval_request_id` displays the Internal Order number. The primary bridge to Manufacturing Order is now:

```text
approval_product_line.approval_request_id = mrp_production.x_studio_nomor_io
```

`approval_product_line.x_studio_nomor_io` remains visible as secondary/raw context but is not the primary Internal Order bridge.

New traceability views were added to connect:

Internal Order approval lines -> Manufacturing Orders -> stock movements -> later Sales Order if inferable -> accounting if linked.

Frontend Page 1 was later built as a read-only Internal Order Traceability Dashboard. No profitability calculation was added. Raw Odoo tables were not overwritten.

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
- Confirmed Page 1 should use `vw_dashboard_internal_order_traceability`.
- Page 1 remains traceability-only. No profitability calculation was added.

V1 milestone closeout completed:

- Updated `README.md` with the current project status.
- Created `docs/MILESTONE_V1_TRACEABILITY_COMPLETE.md`.
- Confirmed the V1 checkpoint is Internal Order Traceability only.
- Recommended repository tag: `v1-traceability`.

Business usability review completed:

- Created `docs/DASHBOARD_BUSINESS_REVIEW.md`.
- Reviewed the dashboard from VP Operations, PPIC Manager, and Procurement Manager perspectives.
- Recommended keeping KPI cards and filters, but simplifying the default table.
- Recommended moving raw SO/PO quantities, accounting line count, and stock movement counts into diagnostics.
- Confirmed profitability should still wait until the traceability page is reviewed and accepted by business users.

Internal Order dashboard UI simplification completed:

- KPI cards were left unchanged.
- Filters were left unchanged.
- The default main table now keeps only IO Number, Status, Product Count, MO Count, SO Count, Delivery %, Invoice %, Receipt %, Billing %, and Traceability Status.
- Requester, Need Date, Accounting Lines, raw SO quantities, raw PO quantities, line counts, status summaries, and stock movement counts are now shown in expandable diagnostics.
- No SQL views, API endpoints, Data Truth Layer logic, business relationships, or traceability logic were changed.

Phase 2A Sales Order Traceability architecture started:

- Created `docs/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`.
- Confirmed Sales Order is now the primary management dashboard entity.
- Documented business questions, data sources, SO source classification, KPIs, main table, drill-down design, follow-up statuses, and readiness.
- Confirmed the Sales Order dashboard can be built as a traceability-only Phase 2A using current data.
- No SQL, API, frontend, Data Truth Layer, business relationship, or profitability changes were made.

Phase 2A Sales Order Traceability implementation completed:

- Created `sql/05_sales_order_dashboard_views.sql`.
- Added `vw_dashboard_sales_order_traceability`.
- Added `/dashboard/sales-orders`.
- Added `/api/dashboard/sales-orders`.
- Added Sales Order dashboard static files under `src/static/dashboard/`.
- Added quantity and amount progress metrics.
- Delay logic uses `sale_order.commitment_date`.
- Accounting / AR remains out of scope for status; accounting line count is diagnostic only.
- Profitability was not calculated.

Latest Phase 2A scope update:

- Sales Order Traceability Dashboard is now scoped to PT Nobi Putra Angkasa only.
- PT Nobi Elektrika Sejahtera is excluded at SQL view level.
- The filter is applied using the extracted `sale_order.company_id` field.
- In the current PostgreSQL extraction, `sale_order.company_id` stores display text, not a numeric company ID. The value used is `Nobi Putra Angkasa, PT`.
- `sale_order.x_studio_product_type` exists and is now exposed as `product_type_raw` and normalized `product_type_label`.
- Product Type is visible in the Sales Order dashboard as a filter, main table column, and count chip strip.

Phase 2A validation snapshot:

| Metric | Count / Value |
| --- | ---: |
| SO count before company filter | 1,201 |
| SO count after company filter | 1,114 |
| active_sales_orders after company filter | 1,090 |
| excluded PT Nobi Elektrika Sejahtera rows | 87 |
| API row_count | 1,114 |
| API company values returned | `Nobi Putra Angkasa, PT` only |
| product_type_filter_available | Yes |

Product type validation snapshot:

| Product type | SO count |
| --- | ---: |
| Empty Panel | 571 |
| Cable Tray | 330 |
| Electrical Panel | 173 |
| Pole/Structure | 17 |
| Lamp | 16 |
| Unknown Product Type | 6 |
| Scaffolding | 1 |
| Other Product Type | 0 |

Important Phase 2A data note:

- Quantity invoice progress is extremely high because current `sale_order_line.qty_invoiced` totals exceed ordered quantity totals by a large amount. The dashboard follows the approved formula and does not reinterpret the source data.

Documentation cleanup completed:

- Created the numbered documentation folder structure under `docs/`.
- Moved architecture, data model, business rules, dashboard, investigation, and deliverable documents into the new folders.
- Added root `INDEX.md` listing current documentation locations.
- Added root `CHANGELOG.md` with the cleanup entry.
- Updated root `README.md` with the documentation structure.
- Kept this handoff file at `docs/CHATGPT_HANDOFF_REPORT.md` by project convention.

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
| `src/static/dashboard/internal-orders.html` | Added the first read-only dashboard page structure and later simplified the default table columns for operational review. |
| `src/static/dashboard/internal-orders.css` | Added dashboard styling for KPI cards, filters, status chips, table, progress bars, and responsive layout. |
| `src/static/dashboard/internal-orders.js` | Added client-side data loading, filters, KPI recalculation, table rendering, expandable diagnostics, and later moved requester, need date, accounting, and raw quantity proof fields into diagnostics. |
| `src/static/dashboard/sales-orders.html` | Added Phase 2A Sales Order Traceability Dashboard page. |
| `src/static/dashboard/sales-orders.css` | Added Sales Order dashboard styling that reuses the existing dashboard design system. |
| `src/static/dashboard/sales-orders.js` | Added Sales Order dashboard data loading, KPI recalculation, filters, table rendering, and drill-down diagnostics. |
| `src/static/dashboard/sales-orders.html` | Updated Sales Order dashboard with Product Type filter, Product Type column, and Product Type count strip. |
| `src/static/dashboard/sales-orders.css` | Widened Sales Order table and styled Product Type chips. |
| `src/static/dashboard/sales-orders.js` | Added Product Type filtering, count chips, table display, and diagnostics. |
| `src/api.py` | Added Product Type filter options and selected `company_id`, `product_type_raw`, and `product_type_label` from the SO dashboard view. |
| `requirements.txt` | Enabled FastAPI dashboard/API runtime dependencies: `fastapi`, `uvicorn`, and `python-multipart`. |
| `tests/test_dashboard_api.py` | Added KPI summary tests for cancelled-record exclusion and zero-denominator ratios. |
| `sql/01_base_views.sql` | Added `vw_approval_product_line_context`, changed `vw_rkb_planning_lines` to an RKB-only compatibility view, added `vw_internal_order_context`, added `vw_manufacturing_flow_context`, added `vw_sale_order_internal_order_bridge`, added finished-goods store movement classification, and corrected Internal Order/SO linkage to use numeric approval request IDs. |
| `sql/02_traceability_views.sql` | Updated data-quality exceptions to use all approval categories, added Internal Order exceptions, kept RKB-specific checks RKB-only. |
| `sql/03_validation_queries.sql` | Added validation counts for approval categories, Internal Order lines, IO-to-MO coverage, MO without IO/SO, manufacturing movements, finished-goods store movements, delivery movements, out-of-scope Internal Use, SO-line dashboard delivery/invoice metrics, and PO-line receipt/billing metrics. |
| `sql/04_dashboard_traceability_views.sql` | Added dashboard-ready `vw_dashboard_internal_order_traceability`, one row per Internal Order number, updated SO linkage to use the parsed many-to-many bridge, changed v1 delivery/invoice readiness to use linked SO line quantities, and added linked PO line receipt/billing progress. |
| `sql/05_sales_order_dashboard_views.sql` | Added Phase 2A `vw_dashboard_sales_order_traceability` for SO-first traceability, quantity/amount progress, source classification, follow-up status, and drill-down JSON. Later updated to filter PT Nobi Putra Angkasa only and expose normalized Product Type. |
| `sql/README.md` | Documented the new approval category mapping, new views, Internal Order v1 source, SO-line delivery/invoice rule, PO-line receipt/billing rule, and updated caveats. |
| `docs/BUSINESS_FLOW.md` | Updated business flow to define Internal Order as `approval_product_line` category `MANUFACTURE` for v1 and clarified RKB vs ROP/PEMBELIAN. |
| `docs/DATA_TRUTH_LAYER_REVIEW.md` | Updated implemented rules, view list, validation snapshot, missing-field assessment, and JO-as-production-required-SO glossary. |
| `docs/DATA_QUALITY_INVESTIGATION.md` | Documented why `MANUFACTURE` is no longer `OTHER_APPROVAL_CATEGORY` and added current Internal Order / movement counts. |
| `docs/INTERNAL_ORDER_TRACEABILITY_INVESTIGATION.md` | Documents Odoo metadata, extractor behavior, sync changes, bridge fix, recalculated counts, and remaining notes. |
| `docs/DASHBOARD_DATA_CONTRACT.md` | Defines the V1 dashboard data contract, separating required V1 fields, optional diagnostics, future profitability fields, and dashboard-facing SO/JO/IO glossary. |
| `docs/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md` | Defines Page 1 layout, table columns, KPI cards, filters, follow-up logic, and frontend readiness. |
| `docs/DASHBOARD_BUSINESS_REVIEW.md` | Reviews Page 1 from VP Operations, PPIC Manager, and Procurement Manager perspectives, with recommended KPI cards, main-table columns, diagnostic-only fields, layout, follow-up actions, and the implemented table simplification. |
| `docs/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md` | Phase 2A blueprint and implementation summary for the Sales Order Traceability Dashboard, covering business questions, source data, source classification, KPIs, table design, drill-downs, follow-up logic, readiness, routes, formulas, validation counts, PT Nobi Putra Angkasa company scope, and Product Type normalization. |
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

Business meaning:

- JO means Job Order.
- JO is a production-required Sales Order, not a separate demand object outside SO.
- Valid JO fields should be interpreted as SO/job-order references.
- IO remains separate from JO.

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

### SQL Naming Review After JO Clarification

No SQL was changed in this documentation pass.

Recommended future SQL/label cleanup before expanding the frontend:

| Current SQL name/label | Suggested clearer meaning | Recommendation |
| --- | --- | --- |
| `job_order_number` | Production-required SO / JO reference | Keep for compatibility, consider adding alias `production_so_number` or `job_order_sales_order_number` in future views. |
| `has_job_order` | Has valid production-required SO reference | Keep for now, consider alias `has_production_so_reference`. |
| `JO_BASED_MO` | MO linked by production-required SO/job-order field | Keep status value for now, document as SO/JO-based production demand. |
| `JO_BASED_RKB` | RKB linked to production-required SO/job-order field | Keep status value for now, document as SO/JO planning context. |
| `JO_BASED_PO` | PO line linked to production-required SO/job-order field | Keep status value for now, document as SO/JO procurement context. |
| `INVALID_BOTH_IO_AND_JO` | Record has both Internal Order and production-required SO reference | Keep exception logic because IO and JO/SO production paths should remain separate. |
| `MISSING_IO_AND_JO` | Missing Internal Order and missing production-required SO reference | Keep for internal validation, consider UI label "Missing IO/SO production reference." |

Frontend label guidance:

- Show `JO` only as "JO / Production SO" or "Job Order (production SO)" in drill-downs.
- Do not add a top-level JO dashboard entity separate from SO.
- Keep current V1 dashboard focused on Internal Order traceability.

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

Frontend status

Page 1 is implemented as the first read-only Internal Order Traceability Dashboard. No backend changes are required for the V1 review. Profitability and product-level drill-down remain later milestones.

Frontend Page 1 is working locally.

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
5. Active Internal Order lines have zero valid JO values. This may be correct because JO is a production-required SO path, while IO is the make-to-stock path; confirm no IO dashboard field needs to show JO by default.
6. Should `approval_product_line.x_studio_nomor_io` still be used for any MANUFACTURE logic, or only displayed as secondary/raw context?
7. Should `Store Finished Product` / delivery stock movement diagnostics be investigated later as advanced traceability, or ignored for v1?
8. Should `Pick Components` be classified as manufacturing movement or material issue/subcomponent consumption in a future version?
9. Is `approval_product_line.x_studio_status = approved` enough for ROP readiness, or do we need `approval_request.state`?
10. Which accounting accounts should count as revenue, AR, COGS, or other profitability components later?
11. Phase 2A quantity invoice progress is extremely high because `qty_invoiced` greatly exceeds ordered quantity in current data. Should this be treated as valid business meaning, a unit-of-measure issue, or an Odoo data-quality issue?
12. Should the Sales Order dashboard keep both raw quantities and raw amounts in the main table, or move one of them into drill-down after business review?

## 7. Suggestions for ChatGPT

ChatGPT should review:

- Whether `MANUFACTURE` as Internal Order fully replaces the missing master-table assumption for v1.
- Whether `approval_request_id` as Internal Order number fully solves the v1 Internal Order bridge.
- Whether the new dashboard traceability status labels are useful for operations.
- Whether SO-line delivered/invoiced quantities are sufficient as the v1 proof for delivery and invoicing.
- Whether PO-line received/invoiced quantities are sufficient as the v1 proof for procurement receipt and billing.
- Whether `Store Finished Product` should remain its own movement type.
- Whether the remaining 28 dashboard Internal Orders without later SO are expected for v1.
- Whether the implemented simplified main table is enough for daily operational review.
- Whether the implemented Phase 2A Sales Order dashboard is usable for management review.

Risk areas:

- Internal Order -> MO link is inferred by `approval_request_id = mrp_production.x_studio_nomor_io` for MANUFACTURE approval lines. Coverage improved to 817 of 1,023 active Internal Order lines.
- A single Internal Order line can link to multiple MOs, which may be correct or may overstate linkage if IO numbers are broad.
- The dashboard view currently treats stock movement counts as optional diagnostics only. Delivery/invoicing status is driven by linked SO lines and procurement receipt/billing progress is driven by linked PO lines for v1.
- Later SO linkage now uses a parsed many-to-many bridge from `sale_order.x_studio_io_1` matched to `approval_request_numeric_id`.
- Accounting line mapping is corrected to SO name, but accounting category meaning still needs account/header classification.
- Profitability is not ready until estimator cost, actual valuation, labor, overhead, and accounting categories are defined.
- Sales Order delayed-status logic is implemented using `sale_order.commitment_date`, but the business should confirm whether commitment date is the right promise-date field.
- Quantity invoice progress can exceed 100% by a large amount because the approved formula uses raw `qty_invoiced / product_uom_qty`.

Frontend readiness:

- The read-only Internal Order traceability dashboard is implemented from `vw_dashboard_internal_order_traceability`. It now has linked SO amount, SO ordered/delivered/invoiced quantities, SO delivery/invoice progress ratios, PO ordered/received/invoiced quantities, PO receipt/invoice progress ratios, and accounting link counts.
- A profitability dashboard is not ready.
- Page 1 is implemented and the default table has been simplified. The safest next step is business-user review of the simplified table before adding drill-downs or profitability.
- Phase 2A Sales Order Traceability is implemented as a traceability-only dashboard at `/dashboard/sales-orders`.

## 8. Suggested Next Codex Task

Recommended next prompt:

```text
Read docs/CHATGPT_HANDOFF_REPORT.md first.

Review the implemented Sales Order Traceability Dashboard with business users.

Read:
- docs/CHATGPT_HANDOFF_REPORT.md
- docs/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md
- docs/SALES_ORDER_DASHBOARD_CONCEPT.md
- docs/DATA_TRUTH_LAYER_REVIEW.md

Task:
- Review whether the implemented SO KPIs, filters, main table columns, drill-down sections, and follow-up statuses are acceptable for Phase 2A.
- Confirm whether `sale_order.commitment_date` is the correct delayed-delivery promise-date field.
- Review the high quantity invoice progress and confirm whether it is valid, unit-related, or data-quality-related.
- Confirm whether both raw quantities and raw amounts should stay in the main table.
- Do not calculate profitability.
- Do not revisit solved IO/MO/SO relationships.
- Do not overwrite raw tables.

Rules:
- Use only existing Data Truth Layer views.
- Do not overwrite raw Odoo tables.
- Do not calculate profitability.
- Do not create new business relationships.
- Keep Sales Order as the primary business entity.
- Keep Internal Order as supporting production traceability.

Also update:
- docs/CHATGPT_HANDOFF_REPORT.md

After the Sales Order dashboard is accepted, decide whether to refine columns/drill-downs or move to the next approved phase.
```
