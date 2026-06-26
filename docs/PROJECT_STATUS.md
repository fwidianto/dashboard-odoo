# Project Status

Last updated: 2026-06-24

Purpose: give a new developer enough context to understand the Odoo Analytics project in about 30 minutes.

This summary uses only documents marked `AUTHORITATIVE` in `docs/DOCUMENT_AUTHORITY_MATRIX.md`:

- `docs/CHATGPT_HANDOFF_REPORT.md`
- `docs/02_Architecture/FINAL_ARCHITECTURE.md`
- `docs/03_Data_Model/data_catalog.md`
- `docs/04_Business_Rules/BUSINESS_FLOW.md`
- `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md`
- `docs/05_Dashboards/DASHBOARD_DATA_CONTRACT.md`
- `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`

## 1. Current Architecture

The project syncs Odoo data into PostgreSQL, builds SQL views as a Data Truth Layer, and serves dashboard pages/API endpoints from the local web app.

Main runtime architecture:

| Area | Current Role |
| --- | --- |
| Odoo source | Operational ERP source data. |
| Sync engine | Extracts configured Odoo models and writes them into PostgreSQL. |
| PostgreSQL raw tables | Store synced Odoo model data without overwriting Odoo. |
| SQL Data Truth Layer | Converts raw Odoo data into business-facing traceability views. |
| FastAPI app | Serves dashboard pages and JSON APIs. |
| Static dashboard assets | Browser UI for operational traceability dashboards. |

Core extraction/sync components:

| Component | Responsibility |
| --- | --- |
| `SyncEngine` | Coordinates model sync from Odoo to PostgreSQL. |
| `OdooClient` | Reads Odoo metadata and records. |
| `PostgresClient` | Creates/upserts PostgreSQL tables. |
| `ErrorReporter` | Tracks sync errors, failures, and data profiles. |
| `SchemaRecommender` | Analyzes sync issues and recommends schema changes. |

Current dashboard/API routes:

| Route | Purpose | Status |
| --- | --- | --- |
| `/dashboard/internal-orders` | Internal Order Traceability Dashboard. | Implemented |
| `/api/dashboard/internal-orders` | JSON API for Internal Order dashboard. | Implemented |
| `/dashboard/sales-orders` | Sales Order Traceability Dashboard. | Implemented |
| `/api/dashboard/sales-orders` | JSON API for Sales Order dashboard. | Implemented |

Important boundary:

- Current dashboards are traceability dashboards only.
- Profitability, margin, COGS, estimator variance, and cost variance are not implemented.
- Stock movement data exists but is diagnostic only for V1/Phase 2A readiness.

## 2. Current Business Rules

### Glossary

| Term | Meaning |
| --- | --- |
| SO | Sales Order. Customer demand and revenue document. |
| JO | Job Order. Factory terminology for a Sales Order that requires production. Every JO is an SO, but not every SO is a JO. |
| IO | Internal Order. Internal make-to-stock demand used to produce finished goods before a customer SO exists. |
| MO | Manufacturing Order. Production execution document. |
| RKB | PPIC material planning for comparison. Does not directly trigger purchasing. |
| ROP / PEMBELIAN | Procurement request / Request of Purchase. |

### Confirmed Flows

Make-to-order / JO flow:

```text
Sales Order
-> Manufacturing Order
-> Delivery
-> Invoice
```

Internal Order make-to-stock flow:

```text
Internal Order
-> Manufacturing Order
-> Finished Goods Stock
-> later Sales Order
-> Delivery
-> Invoice
```

Stock fulfillment flow:

```text
Sales Order
-> Delivery
-> Invoice
```

### Approval Category Mapping

`approval_product_line.x_studio_category` defines the approval line business role:

| Raw Category | Business Type | Meaning |
| --- | --- | --- |
| `RKB` | `RKB_PLANNING` | PPIC material planning and comparison. |
| `ROP` | `ROP_PROCUREMENT_REQUEST` | Procurement request. |
| `PEMBELIAN` | `ROP_PROCUREMENT_REQUEST` | Same business meaning as ROP. |
| `MANUFACTURE` | `INTERNAL_ORDER` | Internal Order for make-to-stock manufacturing. |
| `INTERNAL USE` | `OUT_OF_SCOPE_INTERNAL_USE` | Outside current dashboard scope. |
| null, empty, `{}`, `New` | `UNKNOWN_APPROVAL_CATEGORY` | Needs data review. |
| other value | `OTHER_APPROVAL_CATEGORY` | Needs business confirmation. |

### Internal Order Rules

For V1, Internal Order is not a separate missing master table. It is represented by:

```text
approval_product_line
where x_studio_category = 'MANUFACTURE'
```

Primary Internal Order number:

```text
approval_product_line.approval_request_id
```

Primary IO to MO bridge:

```text
approval_product_line.approval_request_id = mrp_production.x_studio_nomor_io
```

Primary IO to SO bridge:

```text
sale_order.x_studio_io_1
-> parsed approval_request numeric IDs
-> approval_request.id
-> approval_product_line.approval_request_numeric_id
```

Rules:

- One SO may reference multiple IOs.
- One IO may be referenced by multiple SOs.
- Do not infer Internal Order to Sales Order directly from MO.
- Internal Orders without MO are follow-up statuses, not invalid data.

### Sales Order Source Classification

Sales Order source classification is line-first where possible, then rolled up to SO header.

| Source Type | Meaning |
| --- | --- |
| `FROM_INTERNAL_ORDER` | SO is linked to IO and uses finished goods produced earlier. |
| `MAKE_TO_ORDER` / `JO` | SO requires new production and creates or links to MO. |
| `FROM_STOCK` | SO is fulfilled from available stock without IO/MO evidence. |
| `MIXED_SOURCE` | SO lines have different source types. |
| `UNKNOWN_SOURCE` | Current data cannot safely determine source. |

### Status Rules

Cancelled records are excluded from active operational metrics, traceability metrics, and future profitability inputs.

Cancelled records remain visible in audit/data-quality views with `CANCELLED_RECORD`.

Status fields currently used:

| Module | Status Field |
| --- | --- |
| Sales | `sale_order.state` |
| Sales lines | inherit `sale_order.state` |
| Manufacturing | `mrp_production.state` |
| Approval/RKB/IO | `approval_product_line.x_studio_status` |
| Procurement | `purchase_order_line.state` |
| Stock | `stock_move_line.state` |
| Accounting | `account_move_line.parent_state` |

### JO Normalization

Valid JO means:

- not null
- not empty
- not `New`
- exactly 7 digits
- no text

`New` is a placeholder and is treated as null.

### Accounting-to-SO Mapping

Accounting linkage uses SO number, not SO numeric ID:

```text
normalized account_move_line.x_studio_sales_order = sale_order.name::text
```

`x_studio_sales_order = 'New'` is treated as null.

Accounting linkage is traceability only. It is not yet revenue, AR, COGS, margin, or payment classification.

## 3. Current Data Model

The project synchronizes Odoo operational models into PostgreSQL, then builds dashboard-ready SQL views.

### Important Raw Tables

| Area | Tables |
| --- | --- |
| Sales | `sale_order`, `sale_order_line` |
| Manufacturing | `mrp_production` |
| Approval / IO / RKB / ROP | `approval_request`, `approval_product_line` |
| Procurement | `purchase_order`, `purchase_order_line` |
| Inventory / Stock | `stock_move`, `stock_move_line`, `stock_quant` |
| Accounting | `account_move`, `account_move_line`, `account_payment` |
| Master Data | `res_partner`, `product_product`, `product_template` |

### Important Data Truth Layer Views

| View | Purpose |
| --- | --- |
| `vw_sales_order_revenue` | Sales order revenue context. |
| `vw_sales_order_line_source_context` | SO line-level source classification. |
| `vw_sales_order_source_summary` | SO header source rollup. |
| `vw_sale_order_internal_order_bridge` | Many-to-many parser bridge from SO to IO. |
| `vw_mrp_order_context` | MO source classification and IO/SO/JO context. |
| `vw_approval_product_line_context` | Approval category mapping for RKB, ROP, IO, and out-of-scope lines. |
| `vw_rkb_planning_lines` | RKB-only compatibility view. |
| `vw_internal_order_context` | Internal Order approval-line context. |
| `vw_manufacturing_flow_context` | IO to MO traceability context. |
| `vw_procurement_lines` | PO line classification and IO/JO context. |
| `vw_accounting_sales_lines` | Accounting line linkage to SO number. |
| `vw_so_traceability` | SO-level traceability summary. |
| `vw_data_quality_exceptions` | Audit/data-quality exceptions. |
| `vw_dashboard_internal_order_traceability` | Internal Order dashboard source, one row per IO number. |
| `vw_dashboard_sales_order_traceability` | Sales Order dashboard source, one row per SO. |

### Current Validation Snapshot

Internal Order dashboard:

| Metric | Value |
| --- | ---: |
| Dashboard IO rows | 116 |
| Active IO | 115 |
| IO with MO | 101 |
| IO with SO | 88 |
| SO-to-IO bridge rows | 222 |
| Linked SO lines | 1,079 |
| SO delivery progress | 96.82% |
| SO invoice progress | 96.85% |
| Linked PO lines | 3,023 |
| PO receipt progress | 96.52% |
| PO billing progress | 97.38% |

Sales Order dashboard:

| Metric | Value |
| --- | ---: |
| Total SO rows | 1,201 |
| Active SO | 1,175 |
| Delivered SO | 1,034 |
| Invoiced SO | 1,072 |
| Delayed delivery SO | 61 |
| Waiting invoice SO | 18 |
| Waiting delivery SO | 82 |
| Completed SO | 938 |
| Quantity delivery progress | 75.7% |
| Quantity invoice progress | 16,264.2% |
| Amount delivery progress | 82.0% |
| Amount invoice progress | 127.7% |
| SO from Internal Order | 211 |
| SO make-to-order / JO | 16 |
| SO from stock | 73 |
| Unknown source SO | 76 |

Important data note:

- Quantity invoice progress is extremely high because current `sale_order_line.qty_invoiced` totals exceed ordered quantity totals by a large amount.
- The Phase 2A dashboard follows the approved formula and does not reinterpret the source data.

## 4. Current Dashboard Status

### Internal Order Traceability Dashboard

Status: implemented and working.

Routes:

| Route | Purpose |
| --- | --- |
| `/dashboard/internal-orders` | Browser dashboard page. |
| `/api/dashboard/internal-orders` | JSON API. |

Primary view:

```text
vw_dashboard_internal_order_traceability
```

Purpose:

- Show which Internal Orders exist.
- Show which Internal Orders have MO.
- Show which Internal Orders have SO.
- Show delivery/invoice progress from SO line quantities.
- Show procurement receipt/billing progress from PO line quantities.
- Show traceability follow-up status.

Main-table focus:

- IO Number
- Status
- Product Count
- MO Count
- SO Count
- Delivery %
- Invoice %
- Receipt %
- Billing %
- Traceability Status

Diagnostics include requester, need date, accounting lines, raw quantities, PO/SO line proof, and stock movement counts.

### Sales Order Traceability Dashboard

Status: Phase 2A implemented.

Routes:

| Route | Purpose |
| --- | --- |
| `/dashboard/sales-orders` | Browser dashboard page. |
| `/api/dashboard/sales-orders` | JSON API. |

Primary view:

```text
vw_dashboard_sales_order_traceability
```

Purpose:

- Monitor customer orders.
- Monitor delivery progress.
- Monitor invoice progress.
- Monitor production requirements.
- Monitor fulfillment source.
- Monitor process bottlenecks.

KPI cards:

- Active SO
- Delivered SO
- Invoiced SO
- Delayed Delivery SO
- Waiting Invoice SO
- Quantity Delivery Progress %
- Quantity Invoice Progress %
- Amount Delivery Progress %
- Amount Invoice Progress %
- SO From Internal Order
- SO Make To Order / JO
- SO From Stock
- Unknown Source SO

Sales Order amount formulas:

| Metric | Formula |
| --- | --- |
| Ordered amount | `product_uom_qty * price_unit` |
| Delivered amount | `qty_delivered * price_unit` |
| Invoiced amount | `qty_invoiced * price_unit` |
| Quantity delivery progress | `qty_delivered / product_uom_qty` |
| Quantity invoice progress | `qty_invoiced / product_uom_qty` |
| Amount delivery progress | `delivered_amount / ordered_amount` |
| Amount invoice progress | `invoiced_amount / ordered_amount` |

Delay rule:

```text
commitment_date < today
and quantity delivery progress < 100%
=> DELAYED_DELIVERY
```

Follow-up status priority:

1. `CANCELLED_RECORD`
2. `UNKNOWN_SOURCE`
3. `DELAYED_DELIVERY`
4. `WAITING_PRODUCTION`
5. `WAITING_DELIVERY`
6. `WAITING_INVOICE`
7. `COMPLETED`

## 5. Current Open Questions

1. Should `sale_order.commitment_date` be the official promise-date field for delayed-delivery logic?
2. Why does `sale_order_line.qty_invoiced` greatly exceed ordered quantity in Phase 2A totals?
3. Should high invoice progress be treated as valid business meaning, a unit-of-measure issue, or an Odoo data-quality issue?
4. Should the Sales Order dashboard keep both raw quantities and raw amounts in the main table, or move one set into drill-down after business review?
5. Should `sale_order.delivery_status` and `sale_order.invoice_status` override quantity-based flags when they disagree?
6. Should `purchase_order_line.state` be enough for PO readiness, or should purchase header status be synced later?
7. Should `approval_product_line.x_studio_nomor_io` be used for any MANUFACTURE logic, or only displayed as raw/secondary context?
8. Should stock movement diagnostics such as finished-goods and delivery movement counts be investigated later, or ignored for V1?
9. Is `approval_product_line.x_studio_status = approved` enough for ROP readiness, or is `approval_request.state` required?
10. Which accounting accounts should count as revenue, AR, COGS, and other profitability components later?

## 6. Current Next Steps

Recommended immediate next step:

```text
Review the implemented Sales Order Traceability Dashboard with business users.
```

Focus of the review:

1. Confirm KPI cards are understandable and useful.
2. Confirm table columns are the right level of detail.
3. Confirm both quantity and amount progress should remain visible.
4. Confirm `commitment_date` is the correct delay field.
5. Investigate or business-confirm the very high quantity invoice progress.
6. Decide whether any SO dashboard columns should move into drill-down diagnostics.

After Sales Order dashboard review:

1. Refine columns and drill-downs only if business users request it.
2. Keep Internal Order dashboard as supporting traceability.
3. Do not start profitability until traceability dashboards are accepted.

Next phase after traceability acceptance:

```text
Profitability Engine

Estimator
-> RKB
-> Procurement Actual
-> Manufacturing
-> Revenue
-> Margin
```

Profitability blockers:

- Estimator cost import source is not implemented.
- RKB cost rules are not finalized.
- Actual material cost / valuation source is not finalized.
- Labor and overhead allocation rules are not defined.
- Accounting account mapping for revenue, AR, COGS, and cost categories is not defined.
- Profitability must not be calculated until those rules are confirmed.

