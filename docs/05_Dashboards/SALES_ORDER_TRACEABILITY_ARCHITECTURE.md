# Sales Order Traceability Architecture

## 1. Business Questions

Sales Order is the primary business entity for Phase 2A.

The Sales Order Traceability Dashboard should answer:

- Which Sales Orders are active?
- Which Sales Orders are delivered?
- Which Sales Orders are invoiced?
- Which Sales Orders are delayed?
- Which Sales Orders require production?
- Which Sales Orders are fulfilled from Internal Orders?
- Which Sales Orders are fulfilled from stock?
- Which Sales Orders have accounting linkage?

This dashboard is traceability-only. Profitability, margin, COGS, estimator cost, and cost variance are out of scope.

## 2. Data Sources

| Source | Purpose | Key Fields | Readiness |
| --- | --- | --- | --- |
| `sale_order` | Sales Order header, customer-facing demand, commercial status, company scope, and product type. | `id`, `name`, `partner_id`, `date_order`, `state`, `delivery_status`, `invoice_status`, `company_id`, `x_studio_io_1`, `x_studio_product_type` | Ready |
| `sale_order_line` | SO line quantities for ordered, delivered, and invoiced progress. | `id`, `order_id`, `product_id`, `product_uom_qty`, `qty_delivered`, `qty_invoiced`, `price_subtotal` | Ready |
| `vw_sales_order_line_source_context` | Line-level source classification. | SO number/id, product, ordered/delivered/invoiced quantities, line source type, source evidence flags | Ready |
| `vw_sales_order_source_summary` | SO header rollup of line source classification. | SO id/number, source type, line counts, source counts, status validity | Ready |
| `vw_sale_order_internal_order_bridge` | Many-to-many bridge from SO to Internal Order. | `so_id`, `so_number`, `internal_order_id`, `raw_x_studio_io_1` | Ready |
| `vw_mrp_order_context` | Manufacturing Order context for SO/JO production requirements. | MO number, origin SO, IO number, JO number, MO status, source classification | Ready |
| `vw_so_traceability` | Existing SO-level traceability summary. | SO identity, MO linkage, stock movement evidence, accounting linkage, source summary | Partially Ready |
| `vw_accounting_sales_lines` | Accounting line linkage to SO. | normalized SO number, account fields, parent status, accounting line id | Ready for linkage only |
| `account_move_line` | Raw accounting line source. | `x_studio_sales_order`, `parent_state`, account fields, debit/credit/balance | Ready for traceability only |
| `vw_dashboard_internal_order_traceability` | Existing IO dashboard summary for navigation from SO to IO. | internal order number, linked SO count, linked MO count, SO progress, accounting count | Ready as linked drill-down target |

Important note:

- SO delivery and invoice progress should use `sale_order_line.qty_delivered` and `sale_order_line.qty_invoiced`.
- Stock movement remains optional diagnostic traceability only.
- Accounting linkage proves traceability, not revenue classification, AR collection, COGS, or margin.

## 3. SO Source Classification

| Source Type | Business Meaning |
| --- | --- |
| `FROM_STOCK` | SO is fulfilled from available stock without IO/MO evidence. |
| `FROM_INTERNAL_ORDER` | SO is linked to Internal Order through `sale_order.x_studio_io_1`; this means the SO consumes stock produced earlier through IO. |
| `MAKE_TO_ORDER (JO)` | SO requires new production. JO means Job Order, factory terminology for a production-required SO. Every JO is an SO, but not every SO is a JO. |
| `MIXED_SOURCE` | Different SO lines have different source types, such as some stock and some make-to-order. |
| `UNKNOWN_SOURCE` | The current data cannot safely determine whether the SO is stock, IO-backed, or make-to-order. |

Source classification should remain line-first where possible, then roll up to SO header:

- If all lines share one source type, the SO uses that source type.
- If multiple source types exist, the SO is `MIXED_SOURCE`.
- If no source evidence is clear, use `UNKNOWN_SOURCE`.

## 4. Dashboard KPIs

Recommended KPI cards:

| KPI Card | Business Meaning | Why It Matters |
| --- | --- | --- |
| Active SO | Count of active Sales Orders. | Shows current customer-order workload. |
| Delivered SO | Count of SOs with delivered quantity. | Shows fulfillment progress. |
| Invoiced SO | Count of SOs with invoiced quantity. | Shows commercial completion after delivery. |
| Delivery Progress % | Total delivered quantity / total ordered quantity. | Best high-level delivery health metric. |
| Invoice Progress % | Total invoiced quantity / total ordered quantity. | Best high-level billing progress metric. |
| SO From Internal Order | Count of SOs classified as `FROM_INTERNAL_ORDER`. | Shows demand served by IO-produced stock. |
| SO Make To Order / JO | Count of SOs classified as `MAKE_TO_ORDER (JO)`. | Shows production-required demand. |
| SO From Stock | Count of SOs classified as `FROM_STOCK`. | Shows stock-fulfilled demand. |
| SO With Accounting Link | Count of SOs with accounting line linkage. | Shows traceability into accounting. |
| Unknown Source SO | Count of SOs with unclear source. | Focuses data/operations follow-up. |

KPI cards should exclude cancelled SOs from active metrics.

## 5. Main Table Design

Keep the main table compact and business-facing.

| Column | Why It Matters |
| --- | --- |
| SO Number | Primary business document and user entry point. |
| Customer | Lets management and operations identify the account/order owner. |
| SO Date | Supports aging and delay review. |
| Source Type | Explains whether the order is stock, IO-backed, make-to-order/JO, mixed, or unknown. |
| Delivery % | Shows fulfillment progress without forcing users to inspect raw quantities. |
| Invoice % | Shows billing progress without accounting detail. |
| Status | Shows SO operational state. |
| Follow-up Status | Converts traceability into an operational action. |

Optional main-table fields only if users ask for them:

- Ordered quantity
- Delivered quantity
- Invoiced quantity
- IO count
- MO count
- Accounting link yes/no

These are useful, but should not make the default table too wide.

## 6. Drill-Down Design

Each Sales Order row should open a detail view with business sections first and diagnostics second.

### SO Lines

- Product
- Ordered quantity
- Delivered quantity
- Invoiced quantity
- Delivery %
- Invoice %
- Line source classification

### Internal Orders

Show when source includes `FROM_INTERNAL_ORDER`.

- Internal Order number
- IO status
- IO requester
- IO needed date
- Linked MO count
- Link to Internal Order Traceability Dashboard

### Manufacturing Orders

Show when source includes `MAKE_TO_ORDER (JO)` or when MO evidence exists.

- MO number
- MO status
- Product
- Planned/produced quantity
- Origin / JO reference

### Delivery Progress

- SO delivery status
- Ordered quantity
- Delivered quantity
- Remaining delivery quantity
- Optional stock movement diagnostics, clearly marked as diagnostic

### Invoice Progress

- SO invoice status
- Ordered quantity
- Invoiced quantity
- Remaining invoice quantity

### Accounting Link Status

- Accounting link yes/no
- Accounting line count
- Normalized SO number used for accounting linkage
- No revenue, AR, COGS, or margin classification in Phase 2A

### Diagnostics

Keep these separate from the business view:

- Raw stock movement counts
- Inferred link flags
- Match confidence fields
- Data-quality flags
- Raw source values such as `x_studio_io_1`

## 7. Follow-Up Logic

Recommended actionable SO statuses:

| Follow-Up Status | Meaning | Suggested Action |
| --- | --- | --- |
| `WAITING_PRODUCTION` | SO requires production / JO and MO is missing or not complete. | PPIC/manufacturing checks MO status. |
| `WAITING_DELIVERY` | SO has ordered quantity but delivered quantity is incomplete. | Operations checks delivery blocker. |
| `WAITING_INVOICE` | SO has delivered quantity but invoiced quantity is incomplete. | Sales admin/finance checks invoice creation. |
| `WAITING_ACCOUNTING_LINK` | SO has invoicing/accounting expectation but no accounting line linkage. | Finance checks accounting posting/linkage. |
| `COMPLETED` | SO has delivery, invoice, and accounting linkage according to Phase 2A traceability. | No immediate operational follow-up. |
| `FROM_IO_NO_DELIVERY` | SO is linked to IO but not delivered. | Operations checks stock allocation/delivery. |
| `UNKNOWN_SOURCE` | SO source cannot be determined. | Operations/data owner reviews source classification. |
| `CANCELLED_RECORD` | SO is cancelled. | Exclude from active KPI cards and show only when needed. |

Status priority should be business-action-first:

1. `CANCELLED_RECORD`
2. `UNKNOWN_SOURCE`
3. `WAITING_PRODUCTION`
4. `WAITING_DELIVERY`
5. `WAITING_INVOICE`
6. `WAITING_ACCOUNTING_LINK`
7. `COMPLETED`

## 8. Readiness Assessment

Can the Sales Order Dashboard be built immediately using current data?

Answer:

```text
YES, for a traceability-only Phase 2A dashboard.
```

### Ready

- Active/cancelled SO status from `sale_order.state`.
- SO delivery and invoice progress from `sale_order_line.qty_delivered` and `sale_order_line.qty_invoiced`.
- SO source classification from `vw_sales_order_line_source_context` and `vw_sales_order_source_summary`.
- IO-backed SO linkage through `vw_sale_order_internal_order_bridge`.
- Make-to-order / JO context through existing MO context and source classification.
- Accounting linkage through `vw_accounting_sales_lines`.
- Existing Internal Order dashboard can be used as the drill-down target for IO-backed SOs.

### Partially Ready

- Delay detection is only partially ready. SO date and progress are available, but business SLA/due-date rules are not yet defined.
- Accounting is traceability-ready, but not finance-classification-ready.
- Product/customer display quality depends on existing extracted display names.
- SO-level dashboard may need a dedicated view for clean UI performance and simpler API consumption, but the underlying fields already exist.

### Missing / Not In Scope

- Profitability, margin, COGS, estimator cost, and cost variance.
- Payment/AR collection status.
- Approved business rule for what counts as delayed.
- Final UI choice on whether raw quantities stay in main table or diagnostics.
- Any new frontend implementation.

## 9. Phase 2A Implementation

Phase 2A has been implemented as the first Sales Order Traceability Dashboard.

Phase 2A company scope:

```text
PT Nobi Putra Angkasa only
```

The SQL view filters at the `sale_order.company_id` level. In the current extracted PostgreSQL data, `sale_order.company_id` stores the Odoo display value `Nobi Putra Angkasa, PT`, not a numeric company ID. The filter is still applied to the `company_id` field in SQL, not in the frontend.

Routes:

| Route | Purpose |
| --- | --- |
| `/dashboard/sales-orders` | Sales Order Traceability Dashboard page. |
| `/api/dashboard/sales-orders` | JSON API for the Sales Order dashboard. |

SQL view:

```text
vw_dashboard_sales_order_traceability
```

SQL file:

```text
sql/05_sales_order_dashboard_views.sql
```

Product type source:

```text
sale_order.x_studio_product_type
```

Product type normalization:

| Raw value | Product type label |
| --- | --- |
| `1` | Cable Tray |
| `2` | Empty Panel |
| `3` | Pole/Structure |
| `4` | Electrical Panel |
| `5` | Lamp |
| `6` | Scaffolding |
| `Electrical Service` | Electrical Service |
| null, empty, `{}`, `New` | Unknown Product Type |
| anything else | Other Product Type |

Implemented progress formulas:

| Metric | Formula |
| --- | --- |
| `ordered_amount` | `product_uom_qty * price_unit` |
| `delivered_amount` | `qty_delivered * price_unit` |
| `invoiced_amount` | `qty_invoiced * price_unit` |
| `qty_delivery_progress_ratio` | `qty_delivered / product_uom_qty` |
| `qty_invoice_progress_ratio` | `qty_invoiced / product_uom_qty` |
| `amount_delivery_progress_ratio` | `delivered_amount / ordered_amount` |
| `amount_invoice_progress_ratio` | `invoiced_amount / ordered_amount` |

Implemented follow-up priority:

1. `CANCELLED_RECORD`
2. `UNKNOWN_SOURCE`
3. `DELAYED_DELIVERY`
4. `WAITING_PRODUCTION`
5. `WAITING_DELIVERY`
6. `WAITING_INVOICE`
7. `COMPLETED`

Delay rule:

```text
commitment_date < today
and quantity delivery progress < 100%
=> DELAYED_DELIVERY
```

Accounting / AR remains out of scope for Phase 2A. Accounting line count is retained only as a diagnostic field.

Validation snapshot:

| Metric | Count |
| --- | ---: |
| SO count before company filter | 1,201 |
| SO count after company filter | 1,114 |
| active_so | 1,090 |
| excluded PT Nobi Elektrika Sejahtera rows | 87 |

Product type validation:

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

Dashboard API summary snapshot:

| Metric | Value |
| --- | ---: |
| row_count | 1,114 |
| active_sales_orders | 1,090 |
| company values returned | `Nobi Putra Angkasa, PT` only |
| product_type_filter_available | Yes |

Important data note:

- Quantity invoice progress is extremely high because current `sale_order_line.qty_invoiced` totals exceed ordered quantity totals by a large amount. The dashboard intentionally follows the approved Phase 2A formula and does not correct or reinterpret the source data.

## 10. Phase 2A Boundary

Phase 2A implementation is traceability-only.

Do not revisit solved IO/MO/SO relationships.

Do not calculate profitability.

Do not use accounting / AR for Phase 2A status.

Keep stock movement diagnostic only.

The safest next step is business review of the Sales Order dashboard, especially the high invoice quantity progress caused by current source data.
